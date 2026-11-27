"""Security regression tests for director rejection bypass and directory laundering (HIGH-1)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.i18n import t
from app.prod import payments_service, policy
from app.prod.app import create_prod_app
from app.prod.audit_db import list_audit, verify_chain
from app.prod.company_settings import CompanySettingsState
from app.prod.db import connect, tx
from app.prod.deps import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.prod.security import utc_now
from app.schemas import CheckResult, Evidence, HistorySummary, NextAction, Signal, Verdict
from app.settings import Settings
from app.store import DEFAULT_DATA_DIR
from tests.prod.conftest import TEST_SEED_PW, TEST_TODAY, build_sign_payload

CSRF: dict[str, str] = {CSRF_HEADER_NAME: CSRF_HEADER_VALUE}


def _load_queue_by_id() -> dict[str, dict[str, Any]]:
    raw = json.loads((DEFAULT_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
    return {item["id"]: item for item in raw}


def _to_payment_input(item: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "recipient_name": item["recipient_name"],
        "recipient_bin": item["recipient_bin"],
        "recipient_iik": item["recipient_iik"],
        "recipient_bik": item["recipient_bik"],
        "amount_kzt": item["amount_kzt"],
        "purpose": item.get("purpose", ""),
        "kbe": item.get("kbe", ""),
        "knp": item.get("knp", ""),
        "doc_number": item.get("id", ""),
        "doc_date": TEST_TODAY.isoformat(),
    }
    payload.update(overrides)
    return payload


def _login(client: TestClient, login: str, password: str = TEST_SEED_PW) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"login": login, "password": password},
        headers=CSRF,
    )
    assert resp.status_code == 200, resp.text


def _dummy_check(verdict: Verdict, signals: list[Signal] | None = None) -> CheckResult:
    return CheckResult(
        check_id="chk-sec-r2",
        verdict=verdict,
        score=35 if verdict == "yellow" else 0,
        headline_ru="Заголовок",
        signals=signals or [],
        comparison=[],
        next_action=NextAction(text_ru="Совет", primary="sign"),
        history=HistorySummary(payments_count=1),
    )


def _dummy_signal(rule_id: str) -> Signal:
    return Signal(
        rule_id=rule_id,
        points=35,
        severity="primary",
        reason_ru="Причина",
        evidence=Evidence(field="iik"),
    )


@pytest.fixture
def sec_r2_env(
    seeded_db: Path,
) -> Iterator[tuple[FastAPI, Path, TestClient, TestClient]]:
    cfg = Settings(
        app_mode="prod",
        db_path=seeded_db,
        today_override=TEST_TODAY,
        cookie_secure=False,
    )
    prod_app = create_prod_app(db_path=seeded_db, settings_override=cfg)
    with TestClient(prod_app) as acc_client, TestClient(prod_app) as dir_client:
        _login(acc_client, "accountant")
        _login(dir_client, "director")
        yield prod_app, seeded_db, acc_client, dir_client


class TestPolicyRejectionGuardsUnit:
    @pytest.mark.parametrize("verdict", ["green", "yellow", "grey", "red"])
    @pytest.mark.parametrize("role", ["accountant", "director"])
    @pytest.mark.parametrize("ack", [False, True])
    def test_prior_rejection_blocks_all_non_invalid_verdicts_without_new_approval(
        self, verdict: Verdict, role: str, ack: bool
    ) -> None:
        decision = policy.sign_decision(
            role=role,  # type: ignore[arg-type]
            status="checked",
            previous_verdict=verdict,
            fresh_verdict=verdict,
            payment_request_sha256="sha-1",
            approval_status=None,
            approval_request_sha256=None,
            accountant_ack=ack,
            prior_rejection=True,
        )
        assert decision.allowed is False
        assert decision.block_code == "approval_required_after_rejection"

        perms = policy.permissions_for(
            role=role,  # type: ignore[arg-type]
            status="checked",
            verdict=verdict,
            payment_request_sha256="sha-1",
            prior_rejection=True,
        )
        assert perms.can_sign is False
        assert perms.sign_requires_ack is False
        assert perms.sign_block_code == "approval_required_after_rejection"

    def test_matching_new_approval_unlocks_prior_rejection(self) -> None:
        decision = policy.sign_decision(
            role="accountant",
            status="approved",
            previous_verdict="yellow",
            fresh_verdict="yellow",
            payment_request_sha256="sha-2",
            approval_status="approved",
            approval_request_sha256="sha-2",
            accountant_ack=False,
            prior_rejection=True,
            prior_rejected_requisites=True,
        )
        assert decision.allowed is True

    def test_validate_director_decision_forbids_trust_on_previously_rejected_requisites(
        self,
    ) -> None:
        chk = _dummy_check("yellow", [_dummy_signal("iik_changed")])
        assert (
            policy.validate_director_decision(
                decision="approved",
                check=chk,
                director_comment="Подтвердили по телефону из договора",
                trust_account=True,
                requisites_previously_rejected=False,
            )
            is None
        )
        assert (
            policy.validate_director_decision(
                decision="approved",
                check=chk,
                director_comment="Подтвердили по телефону из договора",
                trust_account=True,
                requisites_previously_rejected=True,
            )
            == "trust_not_allowed"
        )


class TestRejectionBypassAndDirectoryProtectionAPI:
    def test_empty_edit_of_rejected_payment_cannot_be_signed_even_with_ack(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sec_r2_env
        queue = _load_queue_by_id()
        q2 = queue["Q-002"]

        # 1. Create yellow payment (new IIK + new BIK), send to director, director rejects
        p = acc.post("/api/v1/payments", json=_to_payment_input(q2), headers=CSRF).json()
        assert p["check"]["verdict"] == "yellow"
        apr_id = acc.post(
            f"/api/v1/payments/{p['id']}/send-to-director",
            json={"accountant_note": "Проверка нового счёта"},
            headers=CSRF,
        ).json()["approval"]["id"]
        rej = director.post(
            f"/api/v1/approvals/{apr_id}/decision",
            json={
                "decision": "rejected",
                "director_comment": "Подозрительные реквизиты, отказ",
            },
            headers=CSRF,
        )
        assert rej.status_code == 200
        assert rej.json()["status"] == "rejected"

        # 2. Rejected + accountant_ack -> 409 approval_rejected
        r_still_rejected = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json=build_sign_payload(acc, p["id"], accountant_ack=True),
            headers=CSRF,
        )
        assert r_still_rejected.status_code == 409
        assert r_still_rejected.json()["code"] == "approval_rejected"

        # 3. Empty edit (identical requisites and amount) MUST NOT make payment signable
        edited = acc.put(
            f"/api/v1/payments/{p['id']}",
            json=_to_payment_input(q2),
            headers=CSRF,
        )
        assert edited.status_code == 200
        e_body = edited.json()
        assert e_body["status"] == "checked"
        assert e_body["accountant_ack"] is False
        assert e_body["permissions"]["can_sign"] is False
        assert e_body["permissions"]["sign_requires_ack"] is False
        assert e_body["permissions"]["sign_block_code"] == "approval_required_after_rejection"
        assert e_body["permissions"]["can_send_to_director"] is True

        # 4. Sign with or without accountant_ack (by accountant or director) -> 409 approval_required_after_rejection
        for lang in ("ru", "kk", "en"):
            denied = acc.post(
                f"/api/v1/payments/{p['id']}/sign?lang={lang}",
                json=build_sign_payload(acc, p["id"], accountant_ack=True),
                headers=CSRF,
            )
            assert denied.status_code == 409
            assert denied.json() == {
                "code": "approval_required_after_rejection",
                "detail": t("error.prod.approval_required_after_rejection", lang),
            }

        dir_denied = director.post(
            f"/api/v1/payments/{p['id']}/sign",
            json=build_sign_payload(director, p["id"]),
            headers=CSRF,
        )
        assert dir_denied.status_code == 409
        assert dir_denied.json()["code"] == "approval_required_after_rejection"

        # 5. Rejected IIK must NOT appear in supplier directory or trusted_accounts, audit intact
        conn = connect(db_path)
        try:
            acc_row = conn.execute(
                "SELECT 1 FROM supplier_accounts WHERE iik = ?",
                (q2["recipient_iik"],),
            ).fetchone()
            assert acc_row is None
            trust_row = conn.execute(
                "SELECT 1 FROM trusted_accounts WHERE recipient_iik = ?",
                (q2["recipient_iik"],),
            ).fetchone()
            assert trust_row is None
            rejected_aprs = conn.execute(
                "SELECT id FROM approvals WHERE payment_id = ? AND status = 'rejected'",
                (p["id"],),
            ).fetchall()
            assert len(rejected_aprs) == 1
            denied_entries = list_audit(conn, payment_id=p["id"], action="sign_denied", limit=10)
            assert any(
                e.details.get("code") == "approval_required_after_rejection"
                for e in denied_entries
            )
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_edit_rejected_payment_to_green_still_requires_new_approval_and_blocks_batch_sign(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sec_r2_env
        queue = _load_queue_by_id()

        # 1. Create yellow payment, send to director, director rejects
        p = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-002"]),
            headers=CSRF,
        ).json()
        apr_1 = acc.post(
            f"/api/v1/payments/{p['id']}/send-to-director",
            json={"accountant_note": "На проверку"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_1}/decision",
                json={"decision": "rejected", "director_comment": "Отказ по первому счёту"},
                headers=CSRF,
            ).status_code
            == 200
        )

        # 2. Edit payment to completely green requisites (Q-001)
        edited = acc.put(
            f"/api/v1/payments/{p['id']}",
            json=_to_payment_input(queue["Q-001"]),
            headers=CSRF,
        )
        assert edited.status_code == 200
        e_body = edited.json()
        assert e_body["check"]["verdict"] == "green"
        assert e_body["permissions"]["can_sign"] is False
        assert e_body["permissions"]["sign_block_code"] == "approval_required_after_rejection"

        # Direct sign blocked even though verdict is green
        r_direct = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json=build_sign_payload(acc, p["id"]),
            headers=CSRF,
        )
        assert r_direct.status_code == 409
        assert r_direct.json()["code"] == "approval_required_after_rejection"

        # Batch sign-green MUST skip it with approval_required_after_rejection
        batch_res = acc.post(
            "/api/v1/payments/batch/sign-green",
            json={"payment_ids": [p["id"]]},
            headers=CSRF,
        )
        assert batch_res.status_code == 200
        assert batch_res.json()["done"] == []
        assert batch_res.json()["skipped"][0]["id"] == p["id"]
        assert batch_res.json()["skipped"][0]["code"] == "approval_required_after_rejection"

        # 3. Send edited payment for a NEW director approval (batch send also accepts green after rejection)
        sent = acc.post(
            "/api/v1/payments/batch/send-to-director",
            json={"payment_ids": [p["id"]], "accountant_note": "Исправлены реквизиты"},
            headers=CSRF,
        )
        assert sent.status_code == 200
        assert [item["id"] for item in sent.json()["done"]] == [p["id"]]
        apr_2 = sent.json()["done"][0]["approval"]["id"]
        assert apr_2 != apr_1

        # 4. Director approves new request -> signing now succeeds!
        assert (
            director.post(
                f"/api/v1/approvals/{apr_2}/decision",
                json={"decision": "approved", "director_comment": "Исправленные реквизиты верны"},
                headers=CSRF,
            ).status_code
            == 200
        )
        signed = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json=build_sign_payload(acc, p["id"]),
            headers=CSRF,
        )
        assert signed.status_code == 200
        assert signed.json()["status"] == "signed"

        conn = connect(db_path)
        try:
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_rejected_requisites_never_enter_directory_or_trusted_accounts(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sec_r2_env
        queue = _load_queue_by_id()
        q2 = queue["Q-002"]

        # 1. Create yellow payment P1 to (BIN, new IIK) and reject it
        p1 = acc.post("/api/v1/payments", json=_to_payment_input(q2), headers=CSRF).json()
        apr_1 = acc.post(
            f"/api/v1/payments/{p1['id']}/send-to-director",
            json={"accountant_note": "Новый счёт поставщика"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_1}/decision",
                json={"decision": "rejected", "director_comment": "Счёт не подтверждён"},
                headers=CSRF,
            ).status_code
            == 200
        )

        # Even if P1 is later edited to another account, the rejected (BIN, IIK) stays remembered
        assert (
            acc.put(
                f"/api/v1/payments/{p1['id']}",
                json=_to_payment_input(queue["Q-001"]),
                headers=CSRF,
            ).status_code
            == 200
        )

        # 2. Brand-new payment P2 with the same rejected (BIN, IIK) cannot bypass via accountant_ack
        p2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q2, purpose="Оплата по новому договору № 505"),
            headers=CSRF,
        ).json()
        assert p2["permissions"]["can_sign"] is False
        assert p2["permissions"]["sign_block_code"] == "approval_required_after_rejection"

        r_ack = acc.post(
            f"/api/v1/payments/{p2['id']}/sign",
            json=build_sign_payload(acc, p2["id"], accountant_ack=True),
            headers=CSRF,
        )
        assert r_ack.status_code == 409
        assert r_ack.json()["code"] == "approval_required_after_rejection"

        # 3. Sending P2 to director: trust_account is forbidden for previously rejected (BIN, IIK)
        apr_2 = acc.post(
            f"/api/v1/payments/{p2['id']}/send-to-director",
            json={"accountant_note": "Повторный запрос"},
            headers=CSRF,
        ).json()["approval"]["id"]
        aprs = {item["id"]: item for item in director.get("/api/v1/approvals").json()}
        assert aprs[apr_2]["can_trust"] is False

        r_trust = director.post(
            f"/api/v1/approvals/{apr_2}/decision",
            json={
                "decision": "approved",
                "director_comment": "Попытка добавить отклонённый счёт в доверенные",
                "trust_account": True,
            },
            headers=CSRF,
        )
        assert r_trust.status_code == 422
        assert r_trust.json()["code"] == "trust_not_allowed"

        # 4. Even if director explicitly approves one-time payment without trust and it is signed,
        #    the rejected (BIN, IIK) must NEVER be written into supplier_accounts or trusted_accounts!
        assert (
            director.post(
                f"/api/v1/approvals/{apr_2}/decision",
                json={
                    "decision": "approved",
                    "director_comment": "Разовое разрешение без добавления в справочник",
                    "trust_account": False,
                },
                headers=CSRF,
            ).status_code
            == 200
        )
        signed_p2 = acc.post(
            f"/api/v1/payments/{p2['id']}/sign",
            json=build_sign_payload(acc, p2["id"]),
            headers=CSRF,
        )
        assert signed_p2.status_code == 200
        assert signed_p2.json()["status"] == "signed"

        conn = connect(db_path)
        try:
            acc_row = conn.execute(
                "SELECT 1 FROM supplier_accounts WHERE iik = ?",
                (q2["recipient_iik"],),
            ).fetchone()
            assert acc_row is None
            trust_row = conn.execute(
                "SELECT 1 FROM trusted_accounts WHERE recipient_iik = ?",
                (q2["recipient_iik"],),
            ).fetchone()
            assert trust_row is None
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_normal_non_rejected_payment_flow_and_directory_update_remain_intact(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sec_r2_env
        queue = _load_queue_by_id()

        # 1. Normal green payment signs cleanly
        p_green = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-001"]),
            headers=CSRF,
        ).json()
        assert p_green["permissions"]["can_sign"] is True
        r_green = acc.post(
            f"/api/v1/payments/{p_green['id']}/sign",
            json=build_sign_payload(acc, p_green["id"]),
            headers=CSRF,
        )
        assert r_green.status_code == 200
        assert r_green.json()["status"] == "signed"

        # 2. Normal never-rejected yellow payment (Q-002) can be approved WITH trust by director
        p_yellow = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-002"]),
            headers=CSRF,
        ).json()
        assert p_yellow["permissions"]["can_sign"] is True
        assert p_yellow["permissions"]["sign_requires_ack"] is True
        apr_id = acc.post(
            f"/api/v1/payments/{p_yellow['id']}/send-to-director",
            json={"accountant_note": "Проверка нового счёта"},
            headers=CSRF,
        ).json()["approval"]["id"]
        dec = director.post(
            f"/api/v1/approvals/{apr_id}/decision",
            json={
                "decision": "approved",
                "director_comment": "Подтвердили реквизиты по договору",
                "trust_account": True,
            },
            headers=CSRF,
        )
        assert dec.status_code == 200
        assert dec.json()["trust_account"] is True

        r_yellow = acc.post(
            f"/api/v1/payments/{p_yellow['id']}/sign",
            json=build_sign_payload(acc, p_yellow["id"]),
            headers=CSRF,
        )
        assert r_yellow.status_code == 200
        assert r_yellow.json()["status"] == "signed"
        assert r_yellow.json()["supplier"]["account_known"] is True

        # 3. Normal never-rejected grey payment (Q-004) signs with accountant_ack and updates directory
        p_grey = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-004"]),
            headers=CSRF,
        ).json()
        assert p_grey["permissions"]["can_sign"] is True
        assert p_grey["permissions"]["sign_requires_ack"] is True
        r_grey = acc.post(
            f"/api/v1/payments/{p_grey['id']}/sign",
            json=build_sign_payload(acc, p_grey["id"], accountant_ack=True),
            headers=CSRF,
        )
        assert r_grey.status_code == 200
        assert r_grey.json()["status"] == "signed"

        conn = connect(db_path)
        try:
            acc_row = conn.execute(
                "SELECT 1 FROM supplier_accounts WHERE iik = ?",
                (queue["Q-002"]["recipient_iik"],),
            ).fetchone()
            assert acc_row is not None
            grey_row = conn.execute(
                "SELECT 1 FROM supplier_accounts WHERE iik = ?",
                (queue["Q-004"]["recipient_iik"],),
            ).fetchone()
            assert grey_row is not None
            trust_row = conn.execute(
                "SELECT 1 FROM trusted_accounts WHERE recipient_iik = ? AND revoked_at IS NULL",
                (queue["Q-002"]["recipient_iik"],),
            ).fetchone()
            assert trust_row is not None
            assert verify_chain(conn).ok is True
        finally:
            conn.close()


class TestAggregateThresholdPolicyUnit:
    def test_single_threshold_preserves_none_reason_while_aggregate_sets_reason(self) -> None:
        single = policy.sign_decision(
            role="accountant",
            status="checked",
            previous_verdict="green",
            fresh_verdict="green",
            payment_request_sha256="sha-1",
            approval_status=None,
            approval_request_sha256=None,
            accountant_ack=False,
            amount_tiyn=100_000_000,
            approval_threshold_tiyn=100_000_000,
            aggregate_72h_tiyn=50_000_000,
        )
        assert single.allowed is False
        assert single.block_code == "threshold_requires_approval"
        assert single.block_reason is None

        agg = policy.sign_decision(
            role="accountant",
            status="checked",
            previous_verdict="green",
            fresh_verdict="green",
            payment_request_sha256="sha-2",
            approval_status=None,
            approval_request_sha256=None,
            accountant_ack=True,
            amount_tiyn=40_000_000,
            approval_threshold_tiyn=100_000_000,
            aggregate_72h_tiyn=60_000_000,
        )
        assert agg.allowed is False
        assert agg.block_code == "threshold_requires_approval"
        assert agg.block_reason == "threshold_aggregate"

    @pytest.mark.parametrize("threshold", [None, 0])
    def test_missing_or_zero_threshold_does_not_block_aggregate(
        self, threshold: int | None
    ) -> None:
        res = policy.sign_decision(
            role="accountant",
            status="checked",
            previous_verdict="green",
            fresh_verdict="green",
            payment_request_sha256="sha-1",
            approval_status=None,
            approval_request_sha256=None,
            accountant_ack=False,
            amount_tiyn=40_000_000,
            approval_threshold_tiyn=threshold,
            aggregate_72h_tiyn=900_000_000,
        )
        assert res.allowed is True

    def test_matching_approval_unlocks_aggregate_threshold_and_ack_does_not(self) -> None:
        for role in ("accountant", "director"):
            blocked = policy.sign_decision(
                role=role,  # type: ignore[arg-type]
                status="checked",
                previous_verdict="yellow",
                fresh_verdict="yellow",
                payment_request_sha256="sha-agg",
                approval_status=None,
                approval_request_sha256=None,
                accountant_ack=True,
                amount_tiyn=40_000_000,
                approval_threshold_tiyn=100_000_000,
                aggregate_72h_tiyn=70_000_000,
            )
            assert blocked.allowed is False
            assert blocked.block_code == "threshold_requires_approval"
            assert blocked.block_reason == "threshold_aggregate"

        perms = policy.permissions_for(
            role="accountant",
            status="checked",
            verdict="yellow",
            payment_request_sha256="sha-agg",
            amount_tiyn=40_000_000,
            approval_threshold_tiyn=100_000_000,
            aggregate_72h_tiyn=70_000_000,
        )
        assert perms.can_sign is False
        assert perms.sign_requires_ack is False
        assert perms.sign_block_code == "threshold_requires_approval"

        approved = policy.sign_decision(
            role="accountant",
            status="approved",
            previous_verdict="yellow",
            fresh_verdict="yellow",
            payment_request_sha256="sha-agg",
            approval_status="approved",
            approval_request_sha256="sha-agg",
            accountant_ack=False,
            amount_tiyn=40_000_000,
            approval_threshold_tiyn=100_000_000,
            aggregate_72h_tiyn=70_000_000,
        )
        assert approved.allowed is True


class TestAggregateThreshold72hAPI:
    def test_split_payments_same_bin_blocks_when_aggregate_exceeds_threshold_and_unlocks_with_approval(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sec_r2_env
        queue = _load_queue_by_id()
        q1 = queue["Q-001"]

        # Configure threshold = 1,000,000 KZT
        cfg_resp = director.put(
            "/api/v1/company/settings",
            json={"approval_threshold_kzt": 1_000_000},
            headers=CSRF,
        )
        assert cfg_resp.status_code == 200

        # Split into 3 x 400,000 KZT to the same BIN (each below threshold and below supplier median)
        p1 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=400_000, purpose="Оплата часть 1 по договору 14"),
            headers=CSRF,
        ).json()
        assert p1["check"]["verdict"] == "green"
        assert p1["permissions"]["can_sign"] is True
        assert (
            acc.post(
                f"/api/v1/payments/{p1['id']}/sign",
                json=build_sign_payload(acc, p1["id"]),
                headers=CSRF,
            ).status_code
            == 200
        )

        p2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=400_000, purpose="Оплата часть 2 по договору 14"),
            headers=CSRF,
        ).json()
        assert p2["check"]["verdict"] == "green"
        assert p2["permissions"]["can_sign"] is True
        assert (
            acc.post(
                f"/api/v1/payments/{p2['id']}/sign",
                json=build_sign_payload(acc, p2["id"]),
                headers=CSRF,
            ).status_code
            == 200
        )

        # Third payment brings 72h aggregate to 1,200,000 >= 1,000,000 -> blocked!
        p3 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=400_000, purpose="Оплата часть 3 по договору 14"),
            headers=CSRF,
        ).json()
        assert p3["check"]["verdict"] == "green"
        assert p3["permissions"]["can_sign"] is False
        assert p3["permissions"]["sign_requires_ack"] is False
        assert p3["permissions"]["sign_block_code"] == "threshold_requires_approval"
        assert p3["permissions"]["can_send_to_director"] is True

        for lang in ("ru", "kk", "en"):
            denied = acc.post(
                f"/api/v1/payments/{p3['id']}/sign?lang={lang}",
                json=build_sign_payload(acc, p3["id"], accountant_ack=True),
                headers=CSRF,
            )
            assert denied.status_code == 409
            body = denied.json()
            assert body["code"] == "threshold_requires_approval"
            assert body["reason"] == "threshold_aggregate"
            assert body["detail"] == t("error.prod.threshold_aggregate", lang)

        # Audit log contains reason='threshold_aggregate' and intact hash chain
        conn = connect(db_path)
        try:
            denied_logs = list_audit(conn, payment_id=p3["id"], action="sign_denied", limit=5)
            assert len(denied_logs) == 3
            assert all(e.details.get("code") == "threshold_requires_approval" for e in denied_logs)
            assert all(e.details.get("reason") == "threshold_aggregate" for e in denied_logs)
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

        # Director approval unlocks signing of p3
        apr_id = acc.post(
            f"/api/v1/payments/{p3['id']}/send-to-director",
            json={"accountant_note": "Согласование третьего транша"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_id}/decision",
                json={"decision": "approved", "director_comment": "Согласовано по графику"},
                headers=CSRF,
            ).status_code
            == 200
        )
        signed_p3 = acc.post(
            f"/api/v1/payments/{p3['id']}/sign",
            json=build_sign_payload(acc, p3["id"]),
            headers=CSRF,
        )
        assert signed_p3.status_code == 200
        assert signed_p3.json()["status"] == "signed"

    def test_split_3x_threshold_minus_1_blocks_on_aggregate(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, _, acc, director = sec_r2_env
        queue = _load_queue_by_id()
        q1 = queue["Q-001"]

        threshold = 500_000
        assert (
            director.put(
                "/api/v1/company/settings",
                json={"approval_threshold_kzt": threshold},
                headers=CSRF,
            ).status_code
            == 200
        )

        # Part 1: threshold - 1 -> below threshold, signs cleanly
        p1 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=threshold - 1, purpose="Транш A"),
            headers=CSRF,
        ).json()
        assert (
            acc.post(
                f"/api/v1/payments/{p1['id']}/sign",
                json=build_sign_payload(acc, p1["id"]),
                headers=CSRF,
            ).status_code
            == 200
        )

        # Part 2: threshold - 1 -> aggregate 999,998 >= 500,000 -> blocked with threshold_aggregate
        p2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=threshold - 1, purpose="Транш B"),
            headers=CSRF,
        ).json()
        r2 = acc.post(
            f"/api/v1/payments/{p2['id']}/sign",
            json=build_sign_payload(acc, p2["id"], accountant_ack=True),
            headers=CSRF,
        )
        assert r2.status_code == 409
        assert r2.json()["code"] == "threshold_requires_approval"
        assert r2.json()["reason"] == "threshold_aggregate"

    def test_same_iik_different_bin_aggregates_and_ack_does_not_bypass(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sec_r2_env
        queue = _load_queue_by_id()
        q4 = queue["Q-004"]  # New supplier BIN 210844188013, IIK KZ327220003914781165

        assert (
            director.put(
                "/api/v1/company/settings",
                json={"approval_threshold_kzt": 500_000},
                headers=CSRF,
            ).status_code
            == 200
        )

        # Pending payment P1 with BIN_A and IIK_X = 300,000 KZT
        p1 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q4, amount_kzt=300_000, purpose="Оплата 1"),
            headers=CSRF,
        ).json()
        assert p1["status"] == "checked"

        # Payment P2 with DIFFERENT BIN (valid BIN from Q-002) but SAME IIK_X = 250,000 KZT
        # Aggregate by IIK_X = 550,000 >= 500,000 -> blocked even with accountant_ack=True!
        p2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(
                q4,
                recipient_name=queue["Q-002"]["recipient_name"],
                recipient_bin=queue["Q-002"]["recipient_bin"],
                amount_kzt=250_000,
                purpose="Оплата 2 на тот же ИИК",
            ),
            headers=CSRF,
        ).json()
        assert p2["check"]["verdict"] == "yellow"
        assert p2["permissions"]["can_sign"] is False
        assert p2["permissions"]["sign_block_code"] == "threshold_requires_approval"

        r_ack = acc.post(
            f"/api/v1/payments/{p2['id']}/sign",
            json=build_sign_payload(acc, p2["id"], accountant_ack=True),
            headers=CSRF,
        )
        assert r_ack.status_code == 409
        assert r_ack.json()["code"] == "threshold_requires_approval"
        assert r_ack.json()["reason"] == "threshold_aggregate"

        # Direct SQL helper verification
        conn = connect(db_path)
        try:
            agg = payments_service.sum_supplier_payments_window_tiyn(
                conn,
                company_id=p2["company_id"],
                recipient_bin=queue["Q-002"]["recipient_bin"],
                recipient_iik=q4["recipient_iik"],
                exclude_payment_id=p2["id"],
            )
            assert agg == 300_000 * 100
        finally:
            conn.close()

    def test_different_suppliers_and_payments_older_than_72h_do_not_aggregate(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sec_r2_env
        queue = _load_queue_by_id()
        q1 = queue["Q-001"]
        q8 = queue["Q-008"]

        assert (
            director.put(
                "/api/v1/company/settings",
                json={"approval_threshold_kzt": 700_000},
                headers=CSRF,
            ).status_code
            == 200
        )

        # 1. Sign 600,000 KZT to supplier Q-001
        p_sup1 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=600_000, purpose="Поставщик 1"),
            headers=CSRF,
        ).json()
        assert (
            acc.post(
                f"/api/v1/payments/{p_sup1['id']}/sign",
                json=build_sign_payload(acc, p_sup1["id"]),
                headers=CSRF,
            ).status_code
            == 200
        )

        # 2. Different supplier Q-008 (190,000 KZT; 600k + 190k = 790k >= 700k) MUST NOT sum with Q-001
        p_sup2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q8, amount_kzt=190_000, purpose="Поставщик 2"),
            headers=CSRF,
        ).json()
        assert p_sup2["permissions"]["can_sign"] is True
        r_sup2 = acc.post(
            f"/api/v1/payments/{p_sup2['id']}/sign",
            json=build_sign_payload(acc, p_sup2["id"]),
            headers=CSRF,
        )
        assert r_sup2.status_code == 200
        assert r_sup2.json()["status"] == "signed"

        # 3. Cancelled / rejected payments to Q-001 do NOT count towards aggregate
        p_cancelled = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=600_000, purpose="Отменённый"),
            headers=CSRF,
        ).json()
        assert acc.post(f"/api/v1/payments/{p_cancelled['id']}/cancel", headers=CSRF).status_code == 200

        # 4. Move p_sup1 timestamp older than 72 hours (73h ago) -> excluded from rolling window!
        old_ts = (utc_now() - timedelta(hours=73)).isoformat()
        conn = connect(db_path)
        try:
            with tx(conn):
                conn.execute(
                    "UPDATE payments SET signed_at = ?, created_at = ?, updated_at = ? WHERE id = ?",
                    (old_ts, old_ts, old_ts, p_sup1["id"]),
                )
            agg_after_73h = payments_service.sum_supplier_payments_window_tiyn(
                conn,
                company_id=p_sup1["company_id"],
                recipient_bin=q1["recipient_bin"],
                recipient_iik=q1["recipient_iik"],
            )
            assert agg_after_73h == 0
        finally:
            conn.close()

        # New 600,000 KZT payment to Q-001 now signs cleanly (p_sup1 is >72h old, p_cancelled excluded)
        p_fresh = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=600_000, purpose="После окна 72ч"),
            headers=CSRF,
        ).json()
        assert p_fresh["permissions"]["can_sign"] is True
        r_fresh = acc.post(
            f"/api/v1/payments/{p_fresh['id']}/sign",
            json=build_sign_payload(acc, p_fresh["id"]),
            headers=CSRF,
        )
        assert r_fresh.status_code == 200
        assert r_fresh.json()["status"] == "signed"

        # Inside 72h window (71h ago) MUST be included
        within_ts = (utc_now() - timedelta(hours=71)).isoformat()
        conn = connect(db_path)
        try:
            with tx(conn):
                conn.execute(
                    "UPDATE payments SET signed_at = ?, created_at = ?, updated_at = ? WHERE id = ?",
                    (within_ts, within_ts, within_ts, p_sup1["id"]),
                )
            agg_within_71h = payments_service.sum_supplier_payments_window_tiyn(
                conn,
                company_id=p_sup1["company_id"],
                recipient_bin=q1["recipient_bin"],
                recipient_iik=q1["recipient_iik"],
                exclude_payment_id=p_fresh["id"],
            )
            assert agg_within_71h == 600_000 * 100
        finally:
            conn.close()

    def test_batch_sign_green_skips_payments_exceeding_72h_aggregate_threshold(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, _, acc, director = sec_r2_env
        queue = _load_queue_by_id()
        q1 = queue["Q-001"]
        q8 = queue["Q-008"]

        assert (
            director.put(
                "/api/v1/company/settings",
                json={"approval_threshold_kzt": 1_000_000},
                headers=CSRF,
            ).status_code
            == 200
        )

        # Create 3 green payments of 400,000 to Q-001 (aggregate 1,200,000 >= 1M) + 1 green to Q-008 (190,000)
        p_a1 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=400_000, purpose="Пакет 1"),
            headers=CSRF,
        ).json()
        p_a2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=400_000, purpose="Пакет 2"),
            headers=CSRF,
        ).json()
        p_a3 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=400_000, purpose="Пакет 3"),
            headers=CSRF,
        ).json()
        p_other = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q8, amount_kzt=190_000, purpose="Другой поставщик"),
            headers=CSRF,
        ).json()

        batch_resp = acc.post(
            "/api/v1/payments/batch/sign-green",
            json={"payment_ids": [p_a1["id"], p_a2["id"], p_a3["id"], p_other["id"]]},
            headers=CSRF,
        )
        assert batch_resp.status_code == 200
        body = batch_resp.json()
        assert [item["id"] for item in body["done"]] == [p_other["id"]]

        skipped_map = {item["id"]: item for item in body["skipped"]}
        assert set(skipped_map.keys()) == {p_a1["id"], p_a2["id"], p_a3["id"]}
        for pid in (p_a1["id"], p_a2["id"], p_a3["id"]):
            assert skipped_map[pid]["code"] == "threshold_requires_approval"
            assert skipped_map[pid]["detail"] == t("error.prod.threshold_aggregate", "ru")
            assert acc.get(f"/api/v1/payments/{pid}").json()["status"] == "checked"

        # batch/send-to-director accepts aggregate-blocked green payments
        send_resp = acc.post(
            "/api/v1/payments/batch/send-to-director",
            json={
                "payment_ids": [p_a1["id"]],
                "accountant_note": "Превышен 72-часовой агрегат",
            },
            headers=CSRF,
        )
        assert send_resp.status_code == 200
        assert [item["id"] for item in send_resp.json()["done"]] == [p_a1["id"]]

    def test_no_threshold_none_or_zero_keeps_previous_behavior(
        self,
        sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, _, acc, director = sec_r2_env
        queue = _load_queue_by_id()
        q1 = queue["Q-001"]

        # Default approval_threshold_kzt is None -> multiple payments to same supplier sign freely
        for idx in range(3):
            p = acc.post(
                "/api/v1/payments",
                json=_to_payment_input(q1, amount_kzt=400_000, purpose=f"Без порога {idx}"),
                headers=CSRF,
            ).json()
            r = acc.post(
                f"/api/v1/payments/{p['id']}/sign",
                json=build_sign_payload(acc, p["id"]),
                headers=CSRF,
            )
            assert r.status_code == 200
            assert r.json()["status"] == "signed"

        # Set a threshold then clear it back to None -> signing remains allowed
        assert (
            director.put(
                "/api/v1/company/settings",
                json={"approval_threshold_kzt": 1_000_000},
                headers=CSRF,
            ).status_code
            == 200
        )
        assert (
            director.put(
                "/api/v1/company/settings",
                json={"approval_threshold_kzt": None},
                headers=CSRF,
            ).status_code
            == 200
        )
        p_cleared = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=400_000, purpose="После сброса порога"),
            headers=CSRF,
        ).json()
        assert (
            acc.post(
                f"/api/v1/payments/{p_cleared['id']}/sign",
                json=build_sign_payload(acc, p_cleared["id"]),
                headers=CSRF,
            ).status_code
            == 200
        )

        # Zero threshold returned by settings layer -> treated as no threshold
        monkeypatch.setattr(
            payments_service,
            "get_company_settings",
            lambda _conn, _cid: CompanySettingsState(
                notify_on="red_yellow",
                approval_threshold_tiyn=0,
                updated_at=None,
            ),
        )
        p_zero = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q1, amount_kzt=400_000, purpose="Нулевой порог"),
            headers=CSRF,
        ).json()
        r_zero = acc.post(
            f"/api/v1/payments/{p_zero['id']}/sign",
            json=build_sign_payload(acc, p_zero["id"]),
            headers=CSRF,
        )
        assert r_zero.status_code == 200
        assert r_zero.json()["status"] == "signed"


class TestDuplicateRequiresApprovalAPI:
    def test_duplicate_of_pending_and_signed_blocked_without_approval_and_unlocks_with_approval(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sec_r2_env
        queue = _load_queue_by_id()
        payload = _to_payment_input(queue["Q-001"], purpose="Оплата по договору № 881")

        # 1. Create original payment P1 (pending/checked) -> not a duplicate, can sign
        p1 = acc.post("/api/v1/payments", json=payload, headers=CSRF).json()
        assert p1["duplicate_of"] is None
        assert p1["permissions"]["can_sign"] is True

        # 2. Create exact duplicate P2 while P1 is pending -> duplicate_of points to P1, signing blocked
        p2 = acc.post("/api/v1/payments", json=payload, headers=CSRF).json()
        assert p2["duplicate_of"] == p1["id"]
        assert p2["permissions"]["can_sign"] is False
        assert p2["permissions"]["sign_requires_ack"] is False
        assert p2["permissions"]["sign_block_code"] == "duplicate_requires_approval"
        assert p2["permissions"]["can_send_to_director"] is True

        # Accountant (with or without ack) and director (without approval) cannot sign duplicate P2
        for lang in ("ru", "kk", "en"):
            r_acc = acc.post(
                f"/api/v1/payments/{p2['id']}/sign?lang={lang}",
                json=build_sign_payload(acc, p2["id"], accountant_ack=True),
                headers=CSRF,
            )
            assert r_acc.status_code == 409
            assert r_acc.json() == {
                "code": "duplicate_requires_approval",
                "detail": t("error.prod.duplicate_requires_approval", lang),
            }

        r_dir = director.post(
            f"/api/v1/payments/{p2['id']}/sign",
            json=build_sign_payload(director, p2["id"]),
            headers=CSRF,
        )
        assert r_dir.status_code == 409
        assert r_dir.json()["code"] == "duplicate_requires_approval"

        # 3. Sign original P1 -> P1 becomes signed; P2 MUST STILL be blocked as duplicate of signed P1!
        s1 = acc.post(
            f"/api/v1/payments/{p1['id']}/sign",
            json=build_sign_payload(acc, p1["id"]),
            headers=CSRF,
        )
        assert s1.status_code == 200
        assert s1.json()["status"] == "signed"

        p2_after_s1 = acc.get(f"/api/v1/payments/{p2['id']}").json()
        assert p2_after_s1["duplicate_of"] == p1["id"]
        assert p2_after_s1["permissions"]["can_sign"] is False
        assert p2_after_s1["permissions"]["sign_block_code"] == "duplicate_requires_approval"

        r_after_s1 = acc.post(
            f"/api/v1/payments/{p2['id']}/sign",
            json=build_sign_payload(acc, p2["id"], accountant_ack=True),
            headers=CSRF,
        )
        assert r_after_s1.status_code == 409
        assert r_after_s1.json()["code"] == "duplicate_requires_approval"

        # 4. Brand-new duplicate P3 created AFTER P1 is signed -> also blocked as duplicate of P1
        p3 = acc.post("/api/v1/payments", json=payload, headers=CSRF).json()
        assert p3["duplicate_of"] == p1["id"]
        assert p3["permissions"]["sign_block_code"] == "duplicate_requires_approval"
        r_p3 = director.post(
            f"/api/v1/payments/{p3['id']}/sign",
            json=build_sign_payload(director, p3["id"]),
            headers=CSRF,
        )
        assert r_p3.status_code == 409
        assert r_p3.json()["code"] == "duplicate_requires_approval"

        # 5. Director approval on P2 unlocks signing of P2
        apr_id = acc.post(
            f"/api/v1/payments/{p2['id']}/send-to-director",
            json={"accountant_note": "Подтвердите повторный платёж"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_id}/decision",
                json={"decision": "approved", "director_comment": "Повторная поставка по тому же счёту"},
                headers=CSRF,
            ).status_code
            == 200
        )
        s2 = acc.post(
            f"/api/v1/payments/{p2['id']}/sign",
            json=build_sign_payload(acc, p2["id"]),
            headers=CSRF,
        )
        assert s2.status_code == 200
        assert s2.json()["status"] == "signed"

        conn = connect(db_path)
        try:
            denied = list_audit(conn, payment_id=p2["id"], action="sign_denied", limit=10)
            assert any(
                e.details.get("code") == "duplicate_requires_approval"
                and e.details.get("duplicate_of") == p1["id"]
                for e in denied
            )
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_duplicate_yellow_ack_cannot_bypass_and_cancelled_or_rejected_original_unblocks(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, _, acc, director = sec_r2_env
        queue = _load_queue_by_id()

        # 1. Yellow duplicate cannot bypass with accountant_ack=True
        y_payload = _to_payment_input(queue["Q-002"], purpose="Услуги перевозки по акту № 11")
        y1 = acc.post("/api/v1/payments", json=y_payload, headers=CSRF).json()
        y2 = acc.post("/api/v1/payments", json=y_payload, headers=CSRF).json()
        assert y2["duplicate_of"] == y1["id"]
        r_y2 = acc.post(
            f"/api/v1/payments/{y2['id']}/sign",
            json=build_sign_payload(acc, y2["id"], accountant_ack=True),
            headers=CSRF,
        )
        assert r_y2.status_code == 409
        assert r_y2.json()["code"] == "duplicate_requires_approval"

        # 2. Cancelling original unblocks duplicate
        g_payload = _to_payment_input(queue["Q-001"], purpose="Дубль для проверки отмены № 12")
        g1 = acc.post("/api/v1/payments", json=g_payload, headers=CSRF).json()
        g2 = acc.post("/api/v1/payments", json=g_payload, headers=CSRF).json()
        assert g2["duplicate_of"] == g1["id"]
        assert acc.post(f"/api/v1/payments/{g1['id']}/cancel", headers=CSRF).status_code == 200

        g2_after = acc.get(f"/api/v1/payments/{g2['id']}").json()
        assert g2_after["duplicate_of"] is None
        assert g2_after["permissions"]["can_sign"] is True
        s_g2 = acc.post(
            f"/api/v1/payments/{g2['id']}/sign",
            json=build_sign_payload(acc, g2["id"]),
            headers=CSRF,
        )
        assert s_g2.status_code == 200
        assert s_g2.json()["status"] == "signed"

        # 3. Postponing original also clears active duplicate block
        p_payload = _to_payment_input(queue["Q-008"], purpose="Дубль для проверки отложения № 13")
        p1 = acc.post("/api/v1/payments", json=p_payload, headers=CSRF).json()
        p2 = acc.post("/api/v1/payments", json=p_payload, headers=CSRF).json()
        assert p2["duplicate_of"] == p1["id"]
        assert acc.post(f"/api/v1/payments/{p1['id']}/postpone", headers=CSRF).status_code == 200

        p2_after = acc.get(f"/api/v1/payments/{p2['id']}").json()
        assert p2_after["duplicate_of"] is None
        assert p2_after["permissions"]["can_sign"] is True
        assert (
            acc.post(
                f"/api/v1/payments/{p2['id']}/sign",
                json=build_sign_payload(acc, p2["id"]),
                headers=CSRF,
            ).status_code
            == 200
        )

        # 4. Rejecting original clears duplicate_of (no duplicate_requires_approval block)
        apr_y1 = acc.post(
            f"/api/v1/payments/{y1['id']}/send-to-director",
            json={"accountant_note": "Проверить"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_y1}/decision",
                json={"decision": "rejected", "director_comment": "Отклоняем оригинал"},
                headers=CSRF,
            ).status_code
            == 200
        )
        y2_after_rej = acc.get(f"/api/v1/payments/{y2['id']}").json()
        assert y2_after_rej["duplicate_of"] is None
        assert y2_after_rej["permissions"]["sign_block_code"] != "duplicate_requires_approval"

    def test_batch_sign_green_signs_original_and_skips_duplicate(
        self, sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, _, acc, _ = sec_r2_env
        queue = _load_queue_by_id()
        payload = _to_payment_input(queue["Q-001"], purpose="Пакетный дубль № 99")

        p1 = acc.post("/api/v1/payments", json=payload, headers=CSRF).json()
        p2 = acc.post("/api/v1/payments", json=payload, headers=CSRF).json()
        assert p1["duplicate_of"] is None
        assert p2["duplicate_of"] == p1["id"]

        batch_res = acc.post(
            "/api/v1/payments/batch/sign-green",
            json={"payment_ids": [p1["id"], p2["id"]]},
            headers=CSRF,
        )
        assert batch_res.status_code == 200
        body = batch_res.json()
        assert [item["id"] for item in body["done"]] == [p1["id"]]
        assert len(body["skipped"]) == 1
        assert body["skipped"][0]["id"] == p2["id"]
        assert body["skipped"][0]["code"] == "duplicate_requires_approval"
        assert body["skipped"][0]["detail"] == t("error.prod.duplicate_requires_approval", "ru")

        # Duplicate remains unsigned (with refreshed check) and can be batch-sent to director
        p2_after = acc.get(f"/api/v1/payments/{p2['id']}").json()
        assert p2_after["status"] == "checked"
        assert p2_after["duplicate_of"] == p1["id"]
        assert p2_after["check"]["verdict"] == "yellow"
        send_dup = acc.post(
            "/api/v1/payments/batch/send-to-director",
            json={"payment_ids": [p2["id"]], "accountant_note": "Дубль на согласование"},
            headers=CSRF,
        )
        assert send_dup.status_code == 200
        assert [item["id"] for item in send_dup.json()["done"]] == [p2["id"]]


class TestNewCriticalSignalsPolicyUnit:
    def test_find_new_critical_signals_detects_only_new_identity_and_block_signals(self) -> None:
        prev = ["iik_changed", "bank_changed", "lookalike_supplier"]

        # Unchanged signals + new non-critical info/amplifier/primary signals -> empty
        benign = [
            ("iik_changed", "primary"),
            ("lookalike_supplier", "primary"),
            ("trusted_account", "info"),
            ("urgent_wording", "amplifier"),
            ("amount_anomaly", "primary"),
        ]
        assert policy.find_new_critical_signals(prev, benign) == []

        # New identity signal (primary) + new block signal (not in IDENTITY_SIGNAL_IDS) -> both detected
        fresh = [
            ("iik_changed", "primary"),
            ("lookalike_supplier", "primary"),  # already present at approval time
            ("iik_reported_by_clients", "primary"),  # NEW identity signal
            ("iik_on_watchlist", "block"),  # NEW block-severity signal
            ("urgent_wording", "amplifier"),  # ignored
        ]
        assert policy.find_new_critical_signals(prev, fresh) == [
            "iik_on_watchlist",
            "iik_reported_by_clients",
        ]

        # Also works directly with Signal Pydantic objects
        sig_objs = [
            Signal(
                rule_id="bcc_account_other_owner",
                points=100,
                severity="block",
                reason_ru="Чужой владелец",
                evidence=Evidence(field="iik"),
            ),
            Signal(
                rule_id="bin_name_mismatch",
                points=40,
                severity="primary",
                reason_ru="Несовпадение названия",
                evidence=Evidence(field="name"),
            ),
        ]
        assert policy.find_new_critical_signals(["iik_changed"], sig_objs) == [
            "bcc_account_other_owner",
            "bin_name_mismatch",
        ]

    def test_sign_decision_supersedes_approved_approval_on_new_critical_signal_same_verdict(
        self,
    ) -> None:
        # Same verdict (red -> red), same signals -> allowed
        ok = policy.sign_decision(
            role="accountant",
            status="approved",
            previous_verdict="red",
            fresh_verdict="red",
            payment_request_sha256="sha-1",
            approval_status="approved",
            approval_request_sha256="sha-1",
            accountant_ack=False,
            previous_signal_ids=["iik_changed", "bank_changed"],
            fresh_signals=[("iik_changed", "primary"), ("bank_changed", "primary")],
        )
        assert ok.allowed is True

        # Same verdict (red -> red), NEW identity signal -> superseded with block_reason='new_signals'
        sup_id = policy.sign_decision(
            role="accountant",
            status="approved",
            previous_verdict="red",
            fresh_verdict="red",
            payment_request_sha256="sha-1",
            approval_status="approved",
            approval_request_sha256="sha-1",
            accountant_ack=False,
            previous_signal_ids=["iik_changed", "bank_changed"],
            fresh_signals=[
                ("iik_changed", "primary"),
                ("bank_changed", "primary"),
                ("iik_reported_by_clients", "primary"),
            ],
        )
        assert sup_id.allowed is False
        assert sup_id.block_code == "verdict_changed"
        assert sup_id.supersede_approval is True
        assert sup_id.block_reason == "new_signals"

        # Same verdict (yellow -> yellow), NEW block signal -> superseded with block_reason='new_signals'
        sup_blk = policy.sign_decision(
            role="accountant",
            status="approved",
            previous_verdict="yellow",
            fresh_verdict="yellow",
            payment_request_sha256="sha-1",
            approval_status="approved",
            approval_request_sha256="sha-1",
            accountant_ack=False,
            previous_signal_ids=["iik_changed"],
            fresh_signals=[("iik_changed", "primary"), ("iik_on_watchlist", "block")],
        )
        assert sup_blk.allowed is False
        assert sup_blk.block_code == "verdict_changed"
        assert sup_blk.supersede_approval is True
        assert sup_blk.block_reason == "new_signals"


class TestNewCriticalSignalsSupersedeApprovalAPI:
    @pytest.mark.parametrize(
        ("new_rule_id", "new_severity"),
        [
            ("iik_reported_by_clients", "primary"),
            ("iik_on_watchlist", "block"),
        ],
    )
    def test_new_identity_or_block_signal_at_sign_time_supersedes_approval_with_same_verdict(
        self,
        sec_r2_env: tuple[FastAPI, Path, TestClient, TestClient],
        monkeypatch: pytest.MonkeyPatch,
        new_rule_id: str,
        new_severity: str,
    ) -> None:
        _, db_path, acc, director = sec_r2_env
        queue = _load_queue_by_id()

        # 1. Create red payment (Q-002 at 850k -> red with iik_changed + bank_changed)
        p = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(
                queue["Q-002"],
                amount_kzt=850_000,
                purpose="Оплата по счёту № 701",
            ),
            headers=CSRF,
        ).json()
        assert p["check"]["verdict"] == "red"
        orig_check_id = p["check"]["check_id"]
        orig_signal_ids = {s["rule_id"] for s in p["check"]["signals"]}
        assert new_rule_id not in orig_signal_ids

        # 2. Send to director and approve
        apr_1 = acc.post(
            f"/api/v1/payments/{p['id']}/send-to-director",
            json={"accountant_note": "Смена банка поставщика"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_1}/decision",
                json={
                    "decision": "approved",
                    "director_comment": "Подтверждено по договору до появления новых сигналов",
                },
                headers=CSRF,
            ).status_code
            == 200
        )

        # 3. Simulate fresh re-check at signing time returning SAME red verdict,
        #    but with a NEW identity or block signal!
        real_check_payment = payments_service.check_payment

        def _check_with_new_signal(*args: Any, **kwargs: Any) -> CheckResult:
            res = real_check_payment(*args, **kwargs)
            injected = Signal(
                rule_id=new_rule_id,
                points=50,
                severity=new_severity,  # type: ignore[arg-type]
                reason_ru="Новый критический сигнал",
                evidence=Evidence(field="iik"),
            )
            return res.model_copy(
                update={
                    "check_id": f"chk-new-{uuid.uuid4().hex[:10]}",
                    "verdict": "red",
                    "signals": [*res.signals, injected],
                }
            )

        monkeypatch.setattr(payments_service, "check_payment", _check_with_new_signal)

        # 4. Signing must fail with 409 verdict_changed, supersede old approval, and reset to checked
        denied = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json=build_sign_payload(acc, p["id"]),
            headers=CSRF,
        )
        assert denied.status_code == 409
        body = denied.json()
        assert body["code"] == "verdict_changed"
        assert body["reason"] == "new_signals"
        assert body["new_signal_ids"] == [new_rule_id]
        assert body["payment"]["status"] == "checked"
        assert body["payment"]["approval"] is None
        assert body["payment"]["accountant_ack"] is False
        assert body["payment"]["check"]["check_id"] != orig_check_id

        # Verify DB approval status + audit_log (approval_superseded with reason='new_signals' & new_signal_ids)
        conn = connect(db_path)
        try:
            apr_row = conn.execute(
                "SELECT status FROM approvals WHERE id = ?",
                (apr_1,),
            ).fetchone()
            assert apr_row is not None and apr_row["status"] == "superseded"

            sup_logs = list_audit(
                conn,
                payment_id=p["id"],
                action="approval_superseded",
                limit=5,
            )
            assert len(sup_logs) == 1
            assert sup_logs[0].details["reason"] == "new_signals"
            assert sup_logs[0].details["new_signal_ids"] == [new_rule_id]

            denied_logs = list_audit(conn, payment_id=p["id"], action="sign_denied", limit=5)
            assert len(denied_logs) == 1
            assert denied_logs[0].details["code"] == "verdict_changed"
            assert denied_logs[0].details["reason"] == "new_signals"
            assert denied_logs[0].details["new_signal_ids"] == [new_rule_id]
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

        # 5. Direct sign without new approval is now blocked (red_requires_approval)
        retry_no_apr = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json=build_sign_payload(acc, p["id"]),
            headers=CSRF,
        )
        assert retry_no_apr.status_code == 409
        assert retry_no_apr.json()["code"] == "red_requires_approval"

        # 6. Re-submit to director (now ref_check includes new_rule_id) and approve -> signing succeeds!
        apr_2 = acc.post(
            f"/api/v1/payments/{p['id']}/send-to-director",
            json={"accountant_note": "Повторное согласование с учётом нового сигнала"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_2}/decision",
                json={
                    "decision": "approved",
                    "director_comment": "Ознакомлен с новым сигналом и подтверждаю оплату",
                },
                headers=CSRF,
            ).status_code
            == 200
        )
        signed = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json=build_sign_payload(acc, p["id"]),
            headers=CSRF,
        )
        assert signed.status_code == 200
        assert signed.json()["status"] == "signed"
