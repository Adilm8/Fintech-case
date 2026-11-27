"""Account warm-up (H1) and one trust rule for yellow and red (H2).

H1: a new IIK of a known supplier becomes known history only after confirmation — the director
approved a payment to it, the director trusted it, or there are >= 2 signed payments to it at
least 14 days apart. One small yellow payment signed by the accountant alone must not turn the
next usual-size payment green.

H2: ``can_trust_check`` uses one rule for yellow and red: weighted signals are a subset of
{iik_changed, bank_changed} and contain iik_changed; identity signals and urgent_wording forbid
trust; zero-weight info signals are allowed; any block signal forbids trust.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app.prod.db import connect, migrate, tx
from app.prod.prod_store import ProdStore
from app.risk.config import (
    ACCOUNT_CONFIRM_MIN_SPAN_DAYS,
    DEMO_TODAY,
    IDENTITY_SIGNAL_IDS,
    can_trust_check,
)
from app.risk.engine import check_payment
from app.risk.profiles import (
    DIRECTOR_APPROVED_KEY,
    DISABLE_PROFILES_ENV,
    confirm_supplier_accounts,
)
from app.schemas import CheckRequest, CheckResult
from app.store import Store
from app.validators.kz import make_iik

PAYER = "client-technostroy"
SUPPLIER_NAME = "ТОО «Алатау Снаб»"
SUPPLIER_BIN = "160542439625"
SUPPLIER_IIK = "KZ246010005016525808"
SUPPLIER_BIK = "HSBKKZKX"
USUAL_AMOUNT = 1_360_000
SMALL_AMOUNT = 300_000
PURPOSE = "Оплата по счёту № 977 за строительные материалы по договору № 14-А"

# The attacker's account: same supplier BIN and name, another bank (Kaspi), not in BCC.
WARM_IIK = make_iik("722", "0009876543210")
WARM_BIK = "CASPKZKA"


def _req(iik: str, bik: str, amount: float) -> CheckRequest:
    return CheckRequest(
        payer_id=PAYER,
        recipient_name=SUPPLIER_NAME,
        recipient_bin=SUPPLIER_BIN,
        recipient_iik=iik,
        recipient_bik=bik,
        amount_kzt=amount,
        purpose=PURPOSE,
    )


def _history_record(
    idx: int,
    paid_at: str,
    *,
    iik: str = WARM_IIK,
    bik: str = WARM_BIK,
    amount: float = SMALL_AMOUNT,
    director_approved: bool | None = False,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": f"warm-{idx}",
        "payer_id": PAYER,
        "paid_at": paid_at,
        "recipient_name": SUPPLIER_NAME,
        "recipient_bin": SUPPLIER_BIN,
        "recipient_iik": iik,
        "recipient_bik": bik,
        "amount_kzt": float(amount),
        "purpose": f"Оплата по счёту № 96{idx} за строительные материалы по договору № 14-А",
        "knp": "710",
    }
    if director_approved is not None:
        record[DIRECTOR_APPROVED_KEY] = director_approved
    return record


def _store_with(*records: dict[str, Any]) -> Store:
    st = Store()
    st.history.extend(records)
    st.history.sort(key=lambda p: (p.get("paid_at", ""), p.get("id", "")))
    st.invalidate_profiles_cache()
    return st


def _check(st: Store, iik: str = WARM_IIK, bik: str = WARM_BIK, amount: float = USUAL_AMOUNT):
    return check_payment(
        _req(iik, bik, amount),
        st,
        today=DEMO_TODAY,
        include_recent_memory=False,
        record_in_memory=False,
    )


def _ids(result: CheckResult) -> set[str]:
    return {s.rule_id for s in result.signals}


def _days_ago(days: int) -> str:
    return (DEMO_TODAY - timedelta(days=days)).isoformat()


@pytest.fixture(params=["profiles", "no_profiles"])
def profile_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    if request.param == "no_profiles":
        monkeypatch.setenv(DISABLE_PROFILES_ENV, "1")
    else:
        monkeypatch.delenv(DISABLE_PROFILES_ENV, raising=False)
    return str(request.param)


# --------------------------------------------------------------------------- H1: engine


def test_warmup_small_payment_is_yellow_without_director() -> None:
    """Step 1 of the attack: a small payment to a new IIK in another bank is yellow."""
    result = _check(Store(), amount=SMALL_AMOUNT)
    assert result.verdict == "yellow"
    assert {"iik_changed", "bank_changed"} <= _ids(result)
    assert not (_ids(result) & IDENTITY_SIGNAL_IDS)


def test_legacy_history_without_metadata_still_counts_as_known(profile_mode: str) -> None:
    """Old behaviour is kept for history without signing metadata (demo, seed, legacy)."""
    st = _store_with(_history_record(1, _days_ago(7), director_approved=None))
    result = _check(st)
    assert "iik_changed" not in _ids(result)
    assert result.verdict == "green"


def test_accountant_only_warmup_does_not_make_next_payment_green(profile_mode: str) -> None:
    """H1: one small accountant-signed payment does not turn the usual-size payment green."""
    st = _store_with(_history_record(1, _days_ago(7), director_approved=False))
    result = _check(st)
    assert result.verdict != "green", result.signals
    assert {"iik_changed", "bank_changed"} <= _ids(result)

    iik_sig = next(s for s in result.signals if s.rule_id == "iik_changed")
    assert iik_sig.evidence.expected == SUPPLIER_IIK
    assert iik_sig.evidence.actual == WARM_IIK

    rows = {row.field: row for row in result.comparison}
    assert rows["iik"].in_history == SUPPLIER_IIK
    assert rows["iik"].differs is True
    assert rows["bik"].in_history == SUPPLIER_BIK
    assert rows["bank"].differs is True


def test_two_accountant_payments_close_together_do_not_confirm(profile_mode: str) -> None:
    span = ACCOUNT_CONFIRM_MIN_SPAN_DAYS - 1
    st = _store_with(
        _history_record(1, _days_ago(3 + span), director_approved=False),
        _history_record(2, _days_ago(3), director_approved=False),
    )
    result = _check(st)
    assert "iik_changed" in _ids(result)
    assert result.verdict != "green"


def test_two_payments_fourteen_days_apart_confirm_the_account(profile_mode: str) -> None:
    st = _store_with(
        _history_record(1, _days_ago(3 + ACCOUNT_CONFIRM_MIN_SPAN_DAYS), director_approved=False),
        _history_record(2, _days_ago(3), director_approved=False),
    )
    result = _check(st)
    assert "iik_changed" not in _ids(result)
    assert "bank_changed" not in _ids(result)


def test_director_approved_payment_confirms_the_account(profile_mode: str) -> None:
    st = _store_with(_history_record(1, _days_ago(7), director_approved=True))
    result = _check(st)
    assert "iik_changed" not in _ids(result)
    assert result.verdict == "green"


def test_director_trust_confirms_the_account(profile_mode: str) -> None:
    st = _store_with(_history_record(1, _days_ago(7), director_approved=False))
    st.trust_account(SUPPLIER_BIN, WARM_IIK, payer_id=PAYER, director_comment="Проверено звонком")
    result = _check(st)
    assert "iik_changed" not in _ids(result)
    assert result.verdict == "green"


def test_original_account_after_warmup_payment_is_still_known(profile_mode: str) -> None:
    """Returning to the long-known account after an unconfirmed one stays green."""
    st = _store_with(_history_record(1, _days_ago(7), director_approved=False))
    result = _check(st, iik=SUPPLIER_IIK, bik=SUPPLIER_BIK)
    assert "iik_changed" not in _ids(result)
    assert result.verdict == "green"


def test_new_supplier_first_account_is_known_without_director() -> None:
    """The first account of a supplier is its baseline, even if signed by the accountant."""
    payments = [
        _history_record(1, _days_ago(30), iik="A", bik="X", director_approved=False),
        _history_record(2, _days_ago(20), iik="B", bik="Y", director_approved=False),
    ]
    conf = confirm_supplier_accounts(payments)
    assert conf.known_iiks == frozenset({"A"})
    assert conf.known_biks == frozenset({"X"})
    assert conf.last_known_index == 0


def test_profile_and_scan_paths_agree(monkeypatch: pytest.MonkeyPatch) -> None:
    records = (_history_record(1, _days_ago(7), director_approved=False),)
    monkeypatch.delenv(DISABLE_PROFILES_ENV, raising=False)
    with_profiles = _check(_store_with(*records))
    monkeypatch.setenv(DISABLE_PROFILES_ENV, "1")
    without_profiles = _check(_store_with(*records))
    assert with_profiles.verdict == without_profiles.verdict
    assert with_profiles.score == without_profiles.score
    assert _ids(with_profiles) == _ids(without_profiles)
    assert [r.model_dump() for r in with_profiles.comparison] == [
        r.model_dump() for r in without_profiles.comparison
    ]


# --------------------------------------------------------------------------- H1: prod store


def _prod_conn(tmp_path: Path):
    conn = connect(tmp_path / "warmup.sqlite3")
    migrate(conn)
    now = "2026-11-01T09:00:00+00:00"
    with tx(conn):
        conn.execute(
            "INSERT INTO companies (id, name, bin, iik, bik, created_at) "
            "VALUES ('comp-w', 'ТОО Тест', '200140001234', 'KZ86125KZT5004100100', "
            "'KCJBKZKX', ?)",
            (now,),
        )
        conn.execute(
            "INSERT INTO users (id, company_id, login, full_name, role, password_hash, "
            "is_active, created_at) VALUES (1, 'comp-w', 'acc', 'Бухгалтер', 'accountant', "
            "'x', 1, ?), (2, 'comp-w', 'dir', 'Директор', 'director', 'x', 1, ?)",
            (now, now),
        )
    return conn


def _insert_signed(conn, pid: str, source: str, paid_at: str, iik: str, bik: str) -> None:
    ts = f"{paid_at}T09:00:00+00:00"
    conn.execute(
        """
        INSERT INTO payments (
            id, company_id, source, recipient_name, recipient_bin, recipient_iik,
            recipient_bik, amount_tiyn, purpose, knp, request_sha256, status,
            created_by, created_at, updated_at, signed_by, signed_at, paid_at
        ) VALUES (?, 'comp-w', ?, ?, ?, ?, ?, ?, ?, '710', ?, 'signed', 1, ?, ?, 1, ?, ?)
        """,
        (
            pid,
            source,
            SUPPLIER_NAME,
            SUPPLIER_BIN,
            iik,
            bik,
            USUAL_AMOUNT * 100,
            PURPOSE,
            f"sha-{pid}",
            ts,
            ts,
            ts,
            paid_at,
        ),
    )


def test_prod_store_marks_director_approval(tmp_path: Path) -> None:
    conn = _prod_conn(tmp_path)
    try:
        with tx(conn):
            _insert_signed(conn, "p-seed", "seed", "2026-09-01", SUPPLIER_IIK, SUPPLIER_BIK)
            _insert_signed(conn, "p-acc", "manual", "2026-10-01", WARM_IIK, WARM_BIK)
            _insert_signed(conn, "p-dir", "manual", "2026-10-05", WARM_IIK, WARM_BIK)
            conn.execute(
                "INSERT INTO checks (id, payment_id, request_sha256, ruleset_version, verdict, "
                "score, signal_ids_json, result_json, trigger, created_by, created_at) "
                "VALUES ('c-dir', 'p-dir', 'sha-p-dir', 'test', 'yellow', 50, '[]', '{}', "
                "'create', 1, '2026-10-05T08:00:00+00:00')"
            )
            conn.execute(
                "INSERT INTO approvals (id, payment_id, check_id, request_sha256, status, "
                "created_by, created_at, decided_by, decided_at) VALUES ('a-dir', 'p-dir', "
                "'c-dir', 'sha-p-dir', 'approved', 1, '2026-10-05T08:00:00+00:00', 2, "
                "'2026-10-05T08:30:00+00:00')"
            )
        st = ProdStore(conn, {"id": "comp-w", "name": "ТОО Тест", "bin": "200140001234",
                              "iik": "KZ86125KZT5004100100", "bik": "KCJBKZKX"})
        by_id = {p["id"]: p for p in st.get_client_history()}
        assert DIRECTOR_APPROVED_KEY not in by_id["p-seed"]
        assert by_id["p-acc"][DIRECTOR_APPROVED_KEY] is False
        assert by_id["p-dir"][DIRECTOR_APPROVED_KEY] is True
    finally:
        conn.close()


def test_prod_store_accountant_only_warmup_stays_unknown(tmp_path: Path) -> None:
    conn = _prod_conn(tmp_path)
    try:
        with tx(conn):
            _insert_signed(conn, "p-seed", "seed", "2026-09-01", SUPPLIER_IIK, SUPPLIER_BIK)
            _insert_signed(conn, "p-acc", "manual", "2026-11-20", WARM_IIK, WARM_BIK)
        st = ProdStore(
            conn,
            {"id": "comp-w", "name": "ТОО Тест", "bin": "200140001234",
             "iik": "KZ86125KZT5004100100", "bik": "KCJBKZKX"},
            today=DEMO_TODAY,
        )
        sup = st.get_profiles().get_supplier(SUPPLIER_BIN)
        assert sup is not None
        assert WARM_IIK in sup.seen_iiks
        assert WARM_IIK not in sup.known_iiks
        assert sup.last_known_iik == SUPPLIER_IIK
    finally:
        conn.close()


# --------------------------------------------------------------------------- H2


@dataclass(frozen=True)
class _Sig:
    rule_id: str
    severity: str
    points: int


IIK = _Sig("iik_changed", "primary", 35)
BANK = _Sig("bank_changed", "amplifier", 30)
URGENT = _Sig("urgent_wording", "amplifier", 25)
ENTITY = _Sig("entity_type_mismatch", "primary", 25)
AMOUNT = _Sig("amount_anomaly", "primary", 35)
INFO_FIRST = _Sig("first_payment_to_recipient", "info", 0)
INFO_NAME = _Sig("bin_name_mismatch", "info", 0)
BLOCK = _Sig("iik_reported_by_clients", "block", 100)

# One shared table: the same cases must hold for canTrustApproval in frontend/src/lib/approvals.ts.
TRUST_CASES: list[tuple[str, str, list[_Sig], bool]] = [
    ("yellow_iik_only", "yellow", [IIK], True),
    ("yellow_iik_bank", "yellow", [IIK, BANK], True),
    ("red_iik_bank", "red", [IIK, BANK], True),
    ("yellow_iik_info", "yellow", [IIK, INFO_FIRST], True),
    ("red_iik_bank_info_identity", "red", [IIK, BANK, INFO_NAME], True),
    ("yellow_iik_urgent", "yellow", [IIK, URGENT], False),
    ("red_iik_bank_urgent", "red", [IIK, BANK, URGENT], False),
    ("yellow_iik_entity", "yellow", [IIK, ENTITY], False),
    ("yellow_iik_amount", "yellow", [IIK, AMOUNT], False),
    ("yellow_bank_only", "yellow", [BANK], False),
    ("red_block", "red", [IIK, BANK, BLOCK], False),
    ("green_iik", "green", [IIK], False),
    ("grey_iik", "grey", [IIK], False),
    ("yellow_no_signals", "yellow", [], False),
]


@pytest.mark.parametrize(
    ("verdict", "signals", "expected"),
    [case[1:] for case in TRUST_CASES],
    ids=[case[0] for case in TRUST_CASES],
)
def test_can_trust_check_table(verdict: str, signals: list[_Sig], expected: bool) -> None:
    assert can_trust_check(verdict, signals) is expected


@pytest.mark.parametrize("identity_id", sorted(IDENTITY_SIGNAL_IDS))
def test_any_weighted_identity_signal_forbids_trust(identity_id: str) -> None:
    sig = _Sig(identity_id, "primary", 25)
    assert can_trust_check("yellow", [IIK, sig]) is False
    assert can_trust_check("red", [IIK, BANK, sig]) is False


def test_yellow_urgent_new_iik_below_median_cannot_be_trusted() -> None:
    """H2 attack from the review: «Срочно, новые реквизиты» below the median is yellow."""
    req = _req(WARM_IIK, WARM_BIK, SMALL_AMOUNT).model_copy(
        update={"purpose": "Срочно! Новые реквизиты. " + PURPOSE}
    )
    result = check_payment(
        req, Store(), today=DEMO_TODAY, include_recent_memory=False, record_in_memory=False
    )
    assert result.verdict in ("yellow", "red")
    assert "urgent_wording" in _ids(result)
    assert can_trust_check(result.verdict, result.signals) is False


def test_plain_bank_change_remains_trustable() -> None:
    """The legitimate path stays: a known supplier moved to another bank, nothing else."""
    result = _check(Store())
    assert _ids(result) - {"first_payment_to_recipient"} <= {"iik_changed", "bank_changed"} | {
        s.rule_id for s in result.signals if s.severity == "info" and s.points == 0
    }
    assert can_trust_check(result.verdict, result.signals) is True
