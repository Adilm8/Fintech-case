"""In-memory data store loaded from synthetic JSON files in backend/data/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas import Approval
from app.validators.kz import BankRecord

DEFAULT_DATA_DIR: Path = Path(__file__).resolve().parents[1] / "data"


class Store:
    """In-memory repository for banks, registry, BCC accounts, history, queue, and approvals."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir: Path = (data_dir or DEFAULT_DATA_DIR).resolve()
        self.banks_path: Path = self.data_dir / "banks.json"

        self.banks: list[BankRecord] = []
        self.banks_by_bik: dict[str, BankRecord] = {}
        self.banks_by_code: dict[str, BankRecord] = {}
        self.registry: dict[str, str] = {}
        self.bcc_accounts: dict[str, dict[str, str]] = {}
        self.client: dict[str, str] = {}
        self.history: list[dict[str, Any]] = []
        self.queue: list[dict[str, Any]] = []

        self.approvals: list[Approval] = []
        self.trusted_accounts: set[tuple[str, str]] = set()

        self.reload()

    def _read_json(self, filename: str) -> Any:
        return json.loads((self.data_dir / filename).read_text(encoding="utf-8"))

    def reload(self) -> None:
        """Load static synthetic JSON files into memory."""
        raw_banks = self._read_json("banks.json")
        bank_items = raw_banks["banks"] if isinstance(raw_banks, dict) else raw_banks
        self.banks = [
            BankRecord(code=str(b["code"]), bik=str(b["bik"]), name=str(b["name"]))
            for b in bank_items
        ]
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
        self.reload()

    def is_trusted(self, recipient_bin: str, recipient_iik: str) -> bool:
        """Return True if the (BIN, IIK) pair has been explicitly trusted by the director."""
        return (recipient_bin, recipient_iik) in self.trusted_accounts

    def trust_account(self, recipient_bin: str, recipient_iik: str) -> None:
        """Mark a (BIN, IIK) pair as trusted."""
        self.trusted_accounts.add((recipient_bin, recipient_iik))

    def get_bank_name_by_bik(self, bik: str) -> str | None:
        """Return the Russian bank name for a BIK, or None if unknown."""
        bank = self.banks_by_bik.get(bik)
        return bank["name"] if bank is not None else None

    def get_bank_name_by_code(self, code: str) -> str | None:
        """Return the Russian bank name for a 3-digit bank code, or None if unknown."""
        bank = self.banks_by_code.get(code)
        return bank["name"] if bank is not None else None

    def get_client_history(self, payer_id: str | None = None) -> list[dict[str, Any]]:
        """Return all historical payments for the given payer_id (or all if omitted)."""
        if not payer_id:
            return list(self.history)
        return [p for p in self.history if p.get("payer_id") == payer_id]

    def get_supplier_history(
        self,
        recipient_bin: str,
        payer_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return chronological historical payments to a specific supplier BIN."""
        return [
            p for p in self.get_client_history(payer_id) if p.get("recipient_bin") == recipient_bin
        ]

    def get_approval(self, approval_id: str) -> Approval | None:
        """Find an approval record by id."""
        for item in self.approvals:
            if item.id == approval_id:
                return item
        return None


store = Store()
