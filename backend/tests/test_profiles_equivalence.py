"""End-to-end equivalence tests proving zero behaviour change with vs without SupplierProfiles."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.risk.config import DEMO_TODAY
from app.risk.engine import check_payment
from app.risk.evaluation import DEFAULT_EVAL_FILENAME, run_history_replay
from app.risk.profiles import DISABLE_PROFILES_ENV, profiles_enabled
from app.risk.rules import extract_invoice_number
from app.schemas import CheckRequest, CheckResult
from app.store import DEFAULT_DATA_DIR, Store


def _assert_results_equivalent(with_profiles: CheckResult, without_profiles: CheckResult, label: str) -> None:
    """Assert identical verdict, score, signals, comparison, history, and guidance."""
    assert with_profiles.verdict == without_profiles.verdict, f"{label}: verdict mismatch"
    assert with_profiles.score == without_profiles.score, f"{label}: score mismatch"
    assert [s.rule_id for s in with_profiles.signals] == [
        s.rule_id for s in without_profiles.signals
    ], f"{label}: signal_ids mismatch"
    assert [(s.rule_id, s.points, s.severity, s.reason_ru, s.evidence) for s in with_profiles.signals] == [
        (s.rule_id, s.points, s.severity, s.reason_ru, s.evidence) for s in without_profiles.signals
    ], f"{label}: signal details mismatch"
    assert with_profiles.headline_ru == without_profiles.headline_ru, f"{label}: headline mismatch"
    assert with_profiles.history == without_profiles.history, f"{label}: history mismatch"
    assert with_profiles.comparison == without_profiles.comparison, f"{label}: comparison mismatch"
    assert with_profiles.next_action == without_profiles.next_action, f"{label}: next_action mismatch"
    assert with_profiles.trusted == without_profiles.trusted, f"{label}: trusted mismatch"


def _queue_request(item: dict[str, Any]) -> CheckRequest:
    return CheckRequest(
        payer_id=item.get("payer_id"),
        recipient_name=item["recipient_name"],
        recipient_bin=item["recipient_bin"],
        recipient_iik=item["recipient_iik"],
        recipient_bik=item["recipient_bik"],
        amount_kzt=item["amount_kzt"],
        purpose=item.get("purpose", ""),
        kbe=item.get("kbe", ""),
        knp=item.get("knp", ""),
    )


def _run_eval_case(store: Store, case: dict[str, Any]) -> CheckResult:
    """Evaluate a single eval_set.json case with identical trust/prior_checks setup."""
    base_dt = datetime(DEMO_TODAY.year, DEMO_TODAY.month, DEMO_TODAY.day, 12, 0, tzinfo=UTC)
    req = CheckRequest(**case["request"])
    is_pre_trusted = bool(case.get("trusted", False))
    prior_checks: list[dict[str, Any]] = list(case.get("prior_checks", []))
    payer_id = store.resolve_payer_id(req.payer_id)
    trust_key = (payer_id, req.recipient_bin, req.recipient_iik)

    if is_pre_trusted:
        store.trust_account(
            req.recipient_bin,
            req.recipient_iik,
            payer_id=payer_id,
            decided_at=f"{DEMO_TODAY.isoformat()}T09:00:00+00:00",
            director_comment="Подтверждено директором по телефону из договора.",
        )
    for prior in prior_checks:
        prior_req = CheckRequest(**prior["request"])
        hours_ago = float(prior.get("hours_ago", 12))
        store.record_check(
            prior_req,
            invoice_no=extract_invoice_number(prior_req.purpose),
            checked_at=base_dt - timedelta(hours=hours_ago),
            today=DEMO_TODAY,
        )
    try:
        return check_payment(
            req,
            store,
            today=DEMO_TODAY,
            include_recent_memory=bool(prior_checks),
            record_in_memory=False,
        )
    finally:
        if is_pre_trusted:
            store.trusted_accounts.pop(trust_key, None)
        if prior_checks:
            store.recent_checks.clear()


class TestProfilesSwitch:
    def test_disable_profiles_env_var_controls_profiles_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(DISABLE_PROFILES_ENV, raising=False)
        assert profiles_enabled() is True

        for truthy in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv(DISABLE_PROFILES_ENV, truthy)
            assert profiles_enabled() is False

        for falsy in ("0", "false", "", "no"):
            monkeypatch.setenv(DISABLE_PROFILES_ENV, falsy)
            assert profiles_enabled() is True

    def test_disabled_switch_bypasses_store_get_profiles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = Store()
        req = _queue_request(store.queue[0])

        def _forbid_get_profiles(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("store.get_profiles must not be called when profiles are disabled")

        monkeypatch.setenv(DISABLE_PROFILES_ENV, "1")
        monkeypatch.setattr(store, "get_profiles", _forbid_get_profiles)
        res = check_payment(req, store, include_recent_memory=False, record_in_memory=False)
        assert res.verdict == "green"


class TestProfilesEquivalence:
    def test_demo_queue_equivalence_with_and_without_profiles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store_with = Store()
        store_without = Store()
        assert len(store_with.queue) == 10

        monkeypatch.delenv(DISABLE_PROFILES_ENV, raising=False)
        with_results = [
            check_payment(
                _queue_request(item),
                store_with,
                include_recent_memory=False,
                record_in_memory=False,
            )
            for item in store_with.queue
        ]

        monkeypatch.setenv(DISABLE_PROFILES_ENV, "1")
        without_results = [
            check_payment(
                _queue_request(item),
                store_without,
                include_recent_memory=False,
                record_in_memory=False,
            )
            for item in store_without.queue
        ]

        for item, res_with, res_without in zip(
            store_with.queue, with_results, without_results, strict=True
        ):
            _assert_results_equivalent(res_with, res_without, f"queue:{item['id']}")

    def test_eval_set_equivalence_with_and_without_profiles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        eval_path = DEFAULT_DATA_DIR / DEFAULT_EVAL_FILENAME
        payload = json.loads(eval_path.read_text(encoding="utf-8"))
        cases: list[dict[str, Any]] = list(payload["cases"])
        assert len(cases) > 0

        store_with = Store()
        store_without = Store()

        monkeypatch.delenv(DISABLE_PROFILES_ENV, raising=False)
        with_results = [_run_eval_case(store_with, case) for case in cases]

        monkeypatch.setenv(DISABLE_PROFILES_ENV, "1")
        without_results = [_run_eval_case(store_without, case) for case in cases]

        for case, res_with, res_without in zip(cases, with_results, without_results, strict=True):
            label = f"{case.get('id', '?')}:{case.get('kind', '?')}"
            _assert_results_equivalent(res_with, res_without, label)

    def test_history_replay_equivalence_with_and_without_profiles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(DISABLE_PROFILES_ENV, raising=False)
        replay_with = run_history_replay()

        monkeypatch.setenv(DISABLE_PROFILES_ENV, "1")
        replay_without = run_history_replay()

        assert replay_with == replay_without
