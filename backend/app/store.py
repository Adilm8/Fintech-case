"""In-memory data store loaded from synthetic JSON files in backend/data/."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.risk.config import DEMO_TODAY
from app.schemas import Approval, CheckRequest, TrustedInfo, compute_request_sha256
from app.validators.kz import BankRecord

DEFAULT_DATA_DIR: Path = Path(__file__).resolve().parents[1] / "data"


def demo_now_iso() -> str:
    """Return an ISO 8601 UTC timestamp combining DEMO_TODAY with the current wall-clock time."""
    now_time = datetime.now(UTC).time().replace(microsecond=0)
    return datetime.combine(DEMO_TODAY, now_time, tzinfo=UTC).isoformat()


class Store:
    """In-memory repository for banks, registry, BCC accounts, history, queue, and approvals."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir: Path = (data_dir or DEFAULT_DATA_DIR).resolve()
        self.banks_path: Path = self.data_dir / "banks.json"
        self.audit_log_path: Path = self.data_dir / "audit.jsonl"

        self.banks: list[BankRecord] = []
        self.banks_by_bik: dict[str, BankRecord] = {}
        self.banks_by_code: dict[str, BankRecord] = {}
        self.registry: dict[str, str] = {}
        self.bcc_accounts: dict[str, dict[str, str]] = {}
        self.client: dict[str, str] = {}
        self.history: list[dict[str, Any]] = []
        self.queue: list[dict[str, Any]] = []

        self.approvals: list[Approval] = []
        self.trusted_accounts: dict[tuple[str, str, str], TrustedInfo] = {}
        self.recent_checks: list[dict[str, Any]] = []

        self.reload()

    def _read_json(self, filename: str) -> Any:
        return json.loads((self.data_dir / filename).read_text(encoding="utf-8"))

    def reload(self) -> None:
        """Load static synthetic JSON files into memory."""
        raw_banks = self._read_json("banks.json")
        bank_items = raw_banks["banks"] if isinstance(raw_banks, dict) else raw_banks
        self.banks = []
        for b in bank_items:
            rec = BankRecord(code=str(b["code"]), bik=str(b["bik"]), name=str(b["name"]))
            if b.get("budget"):
                rec["budget"] = True
            self.banks.append(rec)
        self.banks_by_bik = {b["bik"]: b for b in self.banks}
        self.banks_by_code = {b["code"]: b for b in self.banks}

        self.registry = dict(self._read_json("registry.json"))
        self.bcc_accounts = dict(self._read_json("bcc_accounts.json"))

        raw_history = self._read_json("history.json")
        self.client = dict(raw_history.get("client", {}))
        self.history = list(raw_history.get("payments", []))
        self.history.sort(key=lambda p: (p.get("paid_at", ""), p.get("id", "")))

        self.queue = list(self._read_json("queue.json"))

    def reset(self) -> None:
        """Reset mutable workflow state and reload JSON datasets."""
        self.approvals.clear()
        self.trusted_accounts.clear()
        self.recent_checks.clear()
        self.reload()

    @property
    def default_payer_id(self) -> str:
        """Return the default SME client payer_id loaded from history.json."""
        return str(self.client.get("payer_id", ""))

    @property
    def known_payer_ids(self) -> set[str]:
        """Return all payer_ids known to the store (client profile, history, queue)."""
        payers: set[str] = set()
        if self.default_payer_id:
            payers.add(self.default_payer_id)
        for item in self.history:
            if item.get("payer_id"):
                payers.add(str(item["payer_id"]))
        for item in self.queue:
            if item.get("payer_id"):
                payers.add(str(item["payer_id"]))
        return payers

    def resolve_payer_id(self, payer_id: str | None) -> str:
        """Return payer_id if provided, otherwise fall back to the default client payer_id."""
        return payer_id if payer_id else self.default_payer_id

    def is_known_payer(self, payer_id: str) -> bool:
        """Return True if payer_id belongs to a known client in the store."""
        return payer_id in self.known_payer_ids

    def get_trusted_info(
        self,
        payer_id: str | None,
        recipient_bin: str,
        recipient_iik: str,
    ) -> TrustedInfo | None:
        """Look up director trust metadata for (payer_id, BIN, IIK)."""
        key = (self.resolve_payer_id(payer_id), recipient_bin, recipient_iik)
        return self.trusted_accounts.get(key)

    def is_trusted(
        self,
        recipient_bin: str,
        recipient_iik: str,
        *,
        payer_id: str | None = None,
    ) -> bool:
        """Return True if (payer_id, BIN, IIK) has been explicitly trusted by the director."""
        return self.get_trusted_info(payer_id, recipient_bin, recipient_iik) is not None

    def is_bin_trusted(self, recipient_bin: str, *, payer_id: str | None = None) -> bool:
        """Return True if the payer has any trusted account registered for recipient_bin."""
        resolved_payer = self.resolve_payer_id(payer_id)
        return any(
            key_payer == resolved_payer and key_bin == recipient_bin
            for key_payer, key_bin, _ in self.trusted_accounts
        )

    def get_trusted_entries_for_payer(
        self, payer_id: str | None = None
    ) -> list[tuple[str, str, TrustedInfo]]:
        """Return all (bin, iik, TrustedInfo) entries trusted by the given payer."""
        resolved_payer = self.resolve_payer_id(payer_id)
        return [
            (key_bin, key_iik, info)
            for (key_payer, key_bin, key_iik), info in self.trusted_accounts.items()
            if key_payer == resolved_payer
        ]

    def trust_account(
        self,
        recipient_bin: str,
        recipient_iik: str,
        *,
        payer_id: str | None = None,
        decided_at: str | None = None,
        director_comment: str = "",
    ) -> TrustedInfo:
        """Mark (payer_id, BIN, IIK) as trusted with audit metadata."""
        resolved_payer = self.resolve_payer_id(payer_id)
        info = TrustedInfo(
            decided_at=decided_at or demo_now_iso(),
            director_comment=director_comment,
        )
        self.trusted_accounts[(resolved_payer, recipient_bin, recipient_iik)] = info
        return info

    def get_bank_name_by_bik(self, bik: str) -> str | None:
        """Return the Russian bank name for a BIK, or None if unknown."""
        bank = self.banks_by_bik.get(bik)
        return bank["name"] if bank is not None else None

    def get_bank_name_by_code(self, code: str) -> str | None:
        """Return the Russian bank name for a 3-digit bank code, or None if unknown."""
        bank = self.banks_by_code.get(code)
        return bank["name"] if bank is not None else None

    def is_budget_bank(self, bik: str) -> bool:
        """Return True if the bank for bik is flagged as a state/budget treasury entity."""
        bank = self.banks_by_bik.get(bik)
        return bool(bank is not None and bank.get("budget", False))

    def get_client_history(self, payer_id: str | None = None) -> list[dict[str, Any]]:
        """Return all historical payments for the given payer_id (or default client)."""
        resolved = self.resolve_payer_id(payer_id)
        if not resolved:
            return list(self.history)
        return [p for p in self.history if p.get("payer_id") == resolved]

    def get_supplier_history(
        self,
        recipient_bin: str,
        payer_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return chronological historical payments to a specific supplier BIN."""
        return [
            p for p in self.get_client_history(payer_id) if p.get("recipient_bin") == recipient_bin
        ]

    def record_check(
        self,
        req: CheckRequest,
        *,
        invoice_no: str | None = None,
        checked_at: datetime | None = None,
        today: date = DEMO_TODAY,
        request_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Store a payment check in short-term in-memory history, deduplicated by request SHA-256."""
        resolved_payer = self.resolve_payer_id(req.payer_id)
        req_hash = request_sha256 or compute_request_sha256(req, resolved_payer_id=resolved_payer)
        for existing in self.recent_checks:
            if existing.get("request_sha256") == req_hash:
                return existing

        ts = checked_at or datetime.combine(
            today,
            datetime.now(UTC).time().replace(microsecond=0),
            tzinfo=UTC,
        )
        entry = {
            "payer_id": resolved_payer,
            "recipient_bin": req.recipient_bin,
            "recipient_iik": req.recipient_iik,
            "recipient_name": req.recipient_name,
            "amount_kzt": float(req.amount_kzt),
            "purpose": req.purpose,
            "invoice_no": invoice_no,
            "request_sha256": req_hash,
            "checked_at": ts.isoformat(),
        }
        self.recent_checks.append(entry)
        return entry

    def clear_recent_draft(
        self,
        *,
        payer_id: str | None,
        recipient_bin: str,
        recipient_iik: str,
        amount_kzt: float,
    ) -> None:
        """Remove a matching pre-approval draft entry after director decision."""
        resolved = self.resolve_payer_id(payer_id)
        for idx in range(len(self.recent_checks) - 1, -1, -1):
            entry = self.recent_checks[idx]
            if (
                entry["payer_id"] == resolved
                and entry["recipient_bin"] == recipient_bin
                and entry["recipient_iik"] == recipient_iik
                and entry["amount_kzt"] == float(amount_kzt)
            ):
                self.recent_checks.pop(idx)
                return

    def get_recent_checks(
        self,
        recipient_bin: str,
        payer_id: str | None = None,
        *,
        within_days: int | None = None,
        within_hours: float | None = None,
        now: datetime | None = None,
        today: date = DEMO_TODAY,
        exclude_request_sha256: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recorded in-memory checks for (payer_id, recipient_bin) within a time window."""
        resolved = self.resolve_payer_id(payer_id)
        ref_dt = now or datetime.combine(
            today,
            datetime.now(UTC).time().replace(microsecond=0),
            tzinfo=UTC,
        )
        results: list[dict[str, Any]] = []
        for entry in self.recent_checks:
            if entry["payer_id"] != resolved or entry["recipient_bin"] != recipient_bin:
                continue
            if (
                exclude_request_sha256 is not None
                and entry.get("request_sha256") == exclude_request_sha256
            ):
                continue
            try:
                entry_dt = datetime.fromisoformat(entry["checked_at"])
            except ValueError:
                continue
            delta = max(ref_dt - entry_dt, timedelta(0))
            if within_hours is not None and delta > timedelta(hours=within_hours):
                continue
            if within_days is not None and delta > timedelta(days=within_days):
                continue
            results.append(entry)
        return results

    def get_approval(self, approval_id: str) -> Approval | None:
        """Find an approval record by id."""
        for item in self.approvals:
            if item.id == approval_id:
                return item
        return None

    def find_pending_approval(
        self,
        payer_id: str,
        recipient_bin: str,
        recipient_iik: str,
        amount_kzt: float,
    ) -> Approval | None:
        """Return an existing pending approval matching (payer_id, BIN, IIK, amount), if any."""
        for item in self.approvals:
            if (
                item.status == "pending"
                and self.resolve_payer_id(item.request.payer_id) == payer_id
                and item.request.recipient_bin == recipient_bin
                and item.request.recipient_iik == recipient_iik
                and item.request.amount_kzt == amount_kzt
            ):
                return item
        return None


store = Store()
