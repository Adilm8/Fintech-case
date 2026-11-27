"""Per-supplier profile computation and bounded LRU cache for payment risk evaluation.

Computes per-BIN historical statistics (known IIKs/BIKs/banks, amount median/MAD/p90,
known KNPs, first/last payment metadata, normalized/transliterated/skeleton name tokens),
client-wide amount percentiles, and an IIK-to-BIN reverse index once per history revision.
"""

from __future__ import annotations

import os
import statistics
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any

from app.risk.config import (
    ACCOUNT_CONFIRM_MIN_PAYMENTS,
    ACCOUNT_CONFIRM_MIN_SPAN_DAYS,
    CLIENT_P90_MIN_HISTORY,
)
from app.risk.names import (
    confusable_skeleton,
    detect_legal_form_kind,
    extract_ie_initials,
    normalize_company_name,
    normalize_company_name_translated,
    normalize_company_name_translit,
)
from app.validators.kz import bin_kind, load_banks

DEFAULT_CACHE_MAXSIZE: int = 64
DISABLE_PROFILES_ENV: str = "BCC_DISABLE_PROFILES"
_TRUTHY_ENV_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})

ProfileCacheKey = tuple[str, int, str | None]


def profiles_enabled() -> bool:
    """Return False when the BCC_DISABLE_PROFILES env var disables the profile cache path."""
    raw = os.environ.get(DISABLE_PROFILES_ENV, "").strip().lower()
    return raw not in _TRUTHY_ENV_VALUES


_RulesHelpers = tuple[
    Callable[[list[float], float], float],
    Callable[[list[str]], tuple[list[str], list[str]]],
]
_rules_helpers_cache: _RulesHelpers | None = None


def _get_rules_helpers() -> _RulesHelpers:
    """Resolve percentile and distinctive-token helpers directly from app.risk.rules."""
    global _rules_helpers_cache
    if _rules_helpers_cache is None:
        from app.risk.rules import (
            _classify_supplier_distinctive_tokens,
            _compute_percentile,
        )

        _rules_helpers_cache = (_compute_percentile, _classify_supplier_distinctive_tokens)
    return _rules_helpers_cache


# History record key set by the signing flow: True when the payment went through director
# approval, False when it was signed without the director. Records without the key (synthetic
# demo history, seed data, legacy imports) predate the confirmation rule and count as confirmed.
DIRECTOR_APPROVED_KEY: str = "director_approved"


@dataclass(frozen=True, slots=True)
class AccountConfirmation:
    """Which supplier accounts count as known history (H1, protection against account warm-up)."""

    known_iiks: frozenset[str]
    known_biks: frozenset[str]
    last_known_index: int


def _parse_paid_date(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def confirm_supplier_accounts(sup_payments: Sequence[Mapping[str, Any]]) -> AccountConfirmation:
    """Split a supplier's chronological payments into confirmed (known) and unconfirmed IIKs.

    An IIK is confirmed when any of these holds:
    - it is the supplier's first account in history (the relationship was set up with it);
    - a payment to it has no signing metadata (legacy/demo/imported history);
    - a payment to it was approved by the director;
    - there are >= ACCOUNT_CONFIRM_MIN_PAYMENTS payments to it spanning
      >= ACCOUNT_CONFIRM_MIN_SPAN_DAYS days.
    A single payment to a new IIK signed by the accountant alone does not confirm it.
    Director trust is checked separately by the rules (store.is_trusted).
    """
    if not sup_payments:
        return AccountConfirmation(frozenset(), frozenset(), -1)

    by_iik: dict[str, list[Mapping[str, Any]]] = {}
    for p in sup_payments:
        by_iik.setdefault(str(p["recipient_iik"]), []).append(p)

    first_iik = str(sup_payments[0]["recipient_iik"])
    confirmed: set[str] = {first_iik}
    for iik, items in by_iik.items():
        if iik in confirmed:
            continue
        if any(p.get(DIRECTOR_APPROVED_KEY) is not False for p in items):
            confirmed.add(iik)
            continue
        if len(items) >= ACCOUNT_CONFIRM_MIN_PAYMENTS:
            dates = [d for d in (_parse_paid_date(p.get("paid_at")) for p in items) if d]
            if dates and (max(dates) - min(dates)).days >= ACCOUNT_CONFIRM_MIN_SPAN_DAYS:
                confirmed.add(iik)

    known_biks = frozenset(
        str(p["recipient_bik"]) for p in sup_payments if str(p["recipient_iik"]) in confirmed
    )
    last_known_index = max(
        idx for idx, p in enumerate(sup_payments) if str(p["recipient_iik"]) in confirmed
    )
    return AccountConfirmation(frozenset(confirmed), known_biks, last_known_index)


@dataclass(frozen=True, slots=True)
class IikUsage:
    """Last-seen payment metadata for a specific (IIK, recipient BIN) pair in history."""

    recipient_bin: str
    recipient_name: str
    paid_at: str


@dataclass(frozen=True, slots=True)
class SupplierProfile:
    """Immutable per-BIN historical statistics and precomputed name features."""

    recipient_bin: str
    payments_count: int
    first_name: str
    last_name: str
    first_paid_at: str
    last_paid_at: str
    last_iik: str
    last_bik: str
    last_bank: str
    last_amount_kzt: float
    known_iiks: frozenset[str]
    known_biks: frozenset[str]
    known_banks: frozenset[str]
    seen_iiks: frozenset[str]
    last_known_iik: str
    last_known_bik: str
    last_known_bank: str
    last_known_paid_at: str
    known_knps: frozenset[str]
    amount_median: float
    amount_mad: float
    amount_p90: float
    positive_amount_median: float | None
    positive_amount_p90: float | None
    normalized_name: str
    normalized_tokens: tuple[str, ...]
    translit_cyr: str
    translit_lat: str
    translit_cyr_tokens: tuple[str, ...]
    translit_lat_tokens: tuple[str, ...]
    translated_name: str
    skeleton_name: str
    skeleton_tokens: tuple[str, ...]
    base_cyr_tokens: tuple[str, ...]
    distinctive_cyr_tokens: tuple[str, ...]
    distinctive_lat_tokens: tuple[str, ...]
    is_ie: bool
    ie_initials: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClientProfiles:
    """Immutable cacheable summary of a client's payment history revision."""

    suppliers: Mapping[str, SupplierProfile]
    client_p90: float | None
    client_median: float | None
    iik_to_bins: Mapping[str, frozenset[str]]
    iik_usages: Mapping[str, tuple[IikUsage, ...]]
    history_len: int
    last_record_id: str | None

    def get_supplier(self, recipient_bin: str) -> SupplierProfile | None:
        """Return the SupplierProfile for recipient_bin, or None if unseen."""
        return self.suppliers.get(recipient_bin)

    def other_bins_for_iik(self, recipient_iik: str, recipient_bin: str) -> frozenset[str]:
        """Return all historical BINs other than recipient_bin that used recipient_iik."""
        bins = self.iik_to_bins.get(recipient_iik)
        if not bins:
            return frozenset()
        if recipient_bin not in bins:
            return bins
        return bins - {recipient_bin}

    def find_other_counterparty_for_iik(
        self,
        recipient_iik: str,
        recipient_bin: str,
    ) -> IikUsage | None:
        """Return the latest historical usage of recipient_iik under a BIN != recipient_bin."""
        usages = self.iik_usages.get(recipient_iik)
        if not usages:
            return None
        for usage in reversed(usages):
            if usage.recipient_bin != recipient_bin:
                return usage
        return None


def history_cache_key(
    payer_id: str | None,
    history: Sequence[Mapping[str, Any]],
) -> ProfileCacheKey:
    """Build the revision cache key (payer_id, history length, last record id)."""
    payer_key = str(payer_id) if payer_id else ""
    history_len = len(history)
    if history_len == 0:
        return (payer_key, 0, None)
    raw_id = history[-1].get("id")
    last_id = str(raw_id) if raw_id is not None else ""
    return (payer_key, history_len, last_id)


def _resolve_bank_names(
    banks_by_bik: Mapping[str, Any] | None,
    banks_path: Path | None,
) -> dict[str, str]:
    """Build a BIK -> bank name lookup table matching Store.get_bank_name_by_bik."""
    if banks_by_bik is not None:
        resolved: dict[str, str] = {}
        for bik, entry in banks_by_bik.items():
            if isinstance(entry, Mapping):
                name = entry.get("name")
                if name:
                    resolved[str(bik)] = str(name)
            elif entry:
                resolved[str(bik)] = str(entry)
        return resolved
    return {bank["bik"]: bank["name"] for bank in load_banks(banks_path)}


def build_profiles(
    history: Sequence[Mapping[str, Any]],
    *,
    banks_by_bik: Mapping[str, Any] | None = None,
    banks_path: Path | None = None,
) -> ClientProfiles:
    """Build immutable per-supplier profiles, client percentiles, and IIK index from history.

    Expects history in chronological order matching Store.get_client_history / ProdStore.
    Statistic definitions mirror app.risk.rules bit-for-bit.
    """
    compute_percentile, classify_distinctive = _get_rules_helpers()
    history_len = len(history)
    last_record_id: str | None = None
    if history_len > 0:
        raw_id = history[-1].get("id")
        last_record_id = str(raw_id) if raw_id is not None else ""

    if history_len == 0:
        return ClientProfiles(
            suppliers=MappingProxyType({}),
            client_p90=None,
            client_median=None,
            iik_to_bins=MappingProxyType({}),
            iik_usages=MappingProxyType({}),
            history_len=0,
            last_record_id=None,
        )

    bank_names = _resolve_bank_names(banks_by_bik, banks_path)

    positive_client_amounts: list[float] = []
    payments_by_bin: dict[str, list[Mapping[str, Any]]] = {}
    iik_bins_raw: dict[str, set[str]] = {}
    iik_last_by_bin: dict[str, dict[str, tuple[int, IikUsage]]] = {}

    for idx, payment in enumerate(history):
        amount = float(payment["amount_kzt"])
        if amount > 0:
            positive_client_amounts.append(amount)

        sup_bin = str(payment["recipient_bin"])
        sup_iik = str(payment["recipient_iik"])
        sup_name = str(payment["recipient_name"])
        paid_at = str(payment.get("paid_at", ""))

        payments_by_bin.setdefault(sup_bin, []).append(payment)
        iik_bins_raw.setdefault(sup_iik, set()).add(sup_bin)
        iik_last_by_bin.setdefault(sup_iik, {})[sup_bin] = (
            idx,
            IikUsage(recipient_bin=sup_bin, recipient_name=sup_name, paid_at=paid_at),
        )

    if (
        history_len >= CLIENT_P90_MIN_HISTORY
        and len(positive_client_amounts) >= CLIENT_P90_MIN_HISTORY
    ):
        sorted_client_amounts = sorted(positive_client_amounts)
        client_p90: float | None = compute_percentile(sorted_client_amounts, 0.9)
        client_median: float | None = float(statistics.median(positive_client_amounts))
    else:
        client_p90 = None
        client_median = None

    suppliers: dict[str, SupplierProfile] = {}
    for sup_bin, sup_payments in payments_by_bin.items():
        first = sup_payments[0]
        last = sup_payments[-1]

        first_name = str(first["recipient_name"])
        last_name = str(last["recipient_name"])
        first_paid_at = str(first.get("paid_at", ""))
        last_paid_at = str(last.get("paid_at", ""))
        last_iik = str(last["recipient_iik"])
        last_bik = str(last["recipient_bik"])
        last_bank = bank_names.get(last_bik) or last_bik
        last_amount_kzt = float(last["amount_kzt"])

        seen_iiks = frozenset(str(p["recipient_iik"]) for p in sup_payments)
        confirmation = confirm_supplier_accounts(sup_payments)
        known_iiks = confirmation.known_iiks
        known_biks = confirmation.known_biks
        known_banks = frozenset(bank_names.get(bik) or bik for bik in known_biks)
        last_known = sup_payments[confirmation.last_known_index]
        last_known_bik = str(last_known["recipient_bik"])
        known_knps = frozenset(str(p.get("knp", "")).strip() for p in sup_payments if p.get("knp"))

        amounts = [float(p["amount_kzt"]) for p in sup_payments]
        amount_median = float(statistics.median(amounts))
        amount_mad = float(statistics.median([abs(x - amount_median) for x in amounts]))
        sorted_amounts = sorted(amounts)
        amount_p90 = compute_percentile(sorted_amounts, 0.9)

        if sorted_amounts[0] > 0:
            positive_amount_median: float | None = amount_median
            positive_amount_p90: float | None = amount_p90
        else:
            pos_sorted = [x for x in sorted_amounts if x > 0]
            if pos_sorted:
                positive_amount_median = float(statistics.median(pos_sorted))
                positive_amount_p90 = compute_percentile(pos_sorted, 0.9)
            else:
                positive_amount_median = None
                positive_amount_p90 = None

        norm_name = normalize_company_name(first_name)
        cyr_name, lat_name = normalize_company_name_translit(first_name)
        trans_name = normalize_company_name_translated(first_name)
        skel_name = confusable_skeleton(first_name)

        norm_tokens = tuple(norm_name.split())
        cyr_tokens = tuple(cyr_name.split())
        lat_tokens = tuple(lat_name.split())
        skel_tokens = tuple(skel_name.split())
        base_cyr_tokens = norm_tokens or cyr_tokens
        dist_cyr, dist_lat = classify_distinctive(list(base_cyr_tokens))

        is_ie = detect_legal_form_kind(first_name) == "iin" or bin_kind(sup_bin) == "iin"
        ie_initials = extract_ie_initials(first_name) if is_ie else ()

        suppliers[sup_bin] = SupplierProfile(
            recipient_bin=sup_bin,
            payments_count=len(sup_payments),
            first_name=first_name,
            last_name=last_name,
            first_paid_at=first_paid_at,
            last_paid_at=last_paid_at,
            last_iik=last_iik,
            last_bik=last_bik,
            last_bank=last_bank,
            last_amount_kzt=last_amount_kzt,
            known_iiks=known_iiks,
            known_biks=known_biks,
            known_banks=known_banks,
            seen_iiks=seen_iiks,
            last_known_iik=str(last_known["recipient_iik"]),
            last_known_bik=last_known_bik,
            last_known_bank=bank_names.get(last_known_bik) or last_known_bik,
            last_known_paid_at=str(last_known.get("paid_at", "")),
            known_knps=known_knps,
            amount_median=amount_median,
            amount_mad=amount_mad,
            amount_p90=amount_p90,
            positive_amount_median=positive_amount_median,
            positive_amount_p90=positive_amount_p90,
            normalized_name=norm_name,
            normalized_tokens=norm_tokens,
            translit_cyr=cyr_name,
            translit_lat=lat_name,
            translit_cyr_tokens=cyr_tokens,
            translit_lat_tokens=lat_tokens,
            translated_name=trans_name,
            skeleton_name=skel_name,
            skeleton_tokens=skel_tokens,
            base_cyr_tokens=base_cyr_tokens,
            distinctive_cyr_tokens=tuple(dist_cyr),
            distinctive_lat_tokens=tuple(dist_lat),
            is_ie=is_ie,
            ie_initials=ie_initials,
        )

    iik_to_bins = {iik: frozenset(bins) for iik, bins in iik_bins_raw.items()}
    iik_usages = {
        iik: tuple(usage for _, usage in sorted(by_bin.values(), key=lambda pair: pair[0]))
        for iik, by_bin in iik_last_by_bin.items()
    }

    return ClientProfiles(
        suppliers=MappingProxyType(suppliers),
        client_p90=client_p90,
        client_median=client_median,
        iik_to_bins=MappingProxyType(iik_to_bins),
        iik_usages=MappingProxyType(iik_usages),
        history_len=history_len,
        last_record_id=last_record_id,
    )


class ProfileCache:
    """Thread-safe bounded LRU cache of ClientProfiles keyed by history revision."""

    def __init__(self, maxsize: int = DEFAULT_CACHE_MAXSIZE) -> None:
        if maxsize < 1:
            raise ValueError(f"maxsize must be >= 1, got {maxsize}")
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._cache: OrderedDict[ProfileCacheKey, ClientProfiles] = OrderedDict()
        self._hits = 0
        self._misses = 0

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    @property
    def hits(self) -> int:
        with self._lock:
            return self._hits

    @property
    def misses(self) -> int:
        with self._lock:
            return self._misses

    def get(
        self,
        payer_id: str | None,
        history: Sequence[Mapping[str, Any]],
        *,
        banks_by_bik: Mapping[str, Any] | None = None,
        banks_path: Path | None = None,
    ) -> ClientProfiles:
        """Return cached ClientProfiles for (payer_id, len(history), last_id), building on miss."""
        key = history_cache_key(payer_id, history)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                self._hits += 1
                return cached

        built = build_profiles(history, banks_by_bik=banks_by_bik, banks_path=banks_path)

        with self._lock:
            existing = self._cache.get(key)
            if existing is not None:
                self._cache.move_to_end(key)
                self._hits += 1
                return existing
            self._misses += 1
            self._cache[key] = built
            self._cache.move_to_end(key)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)
            return built

    def invalidate(self, payer_id: str | None = None) -> int:
        """Remove cached entries for payer_id (or all entries if payer_id is None)."""
        with self._lock:
            if payer_id is None:
                removed = len(self._cache)
                self._cache.clear()
                return removed
            payer_key = str(payer_id)
            keys = [k for k in self._cache if k[0] == payer_key]
            for k in keys:
                del self._cache[k]
            return len(keys)

    def clear(self) -> None:
        """Clear all cached entries and reset hit/miss counters."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


_default_cache = ProfileCache(maxsize=DEFAULT_CACHE_MAXSIZE)


def get_profiles(
    payer_id: str | None,
    history: Sequence[Mapping[str, Any]],
    *,
    banks_by_bik: Mapping[str, Any] | None = None,
    banks_path: Path | None = None,
) -> ClientProfiles:
    """Return cached ClientProfiles from the default LRU cache for the given history revision."""
    return _default_cache.get(
        payer_id,
        history,
        banks_by_bik=banks_by_bik,
        banks_path=banks_path,
    )


def invalidate_profiles(payer_id: str | None = None) -> int:
    """Evict cached profiles for payer_id (or all payers if payer_id is None)."""
    return _default_cache.invalidate(payer_id)


def clear_profiles_cache() -> None:
    """Clear the default profile LRU cache."""
    _default_cache.clear()
