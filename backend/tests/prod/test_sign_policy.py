"""Tests for B5: §5 server-side signing policy (all 11 rows), approvals, trust, history & audit."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import (
    MIN_DIRECTOR_COMMENT_LEN as DEMO_MIN_DIRECTOR_COMMENT_LEN,
)
from app.main import (
    TRUST_ALLOWED_SIGNAL_IDS as DEMO_TRUST_ALLOWED_SIGNAL_IDS,
)
from app.main import (
    _can_trust_approval as demo_can_trust_approval,
)
from app.prod import payments_service, policy
from app.prod.app import create_prod_app
from app.prod.audit_db import list_audit, verify_chain
from app.prod.db import connect, tx
from app.prod.deps import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.prod.security import hash_password, utc_now_iso
from app.schemas import (
    Approval as DemoApproval,
)
from app.schemas import (
    CheckRequest,
    CheckResult,
    Evidence,
    HistorySummary,
    NextAction,
    Signal,
    Verdict,
)
from app.settings import Settings
from app.store import DEFAULT_DATA_DIR
from tests.prod.conftest import TEST_SEED_PW, TEST_TODAY

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
        check_id="chk-unit-1",
        verdict=verdict,
        score=0,
        headline_ru="Заголовок",
        signals=signals or [],
        comparison=[],
        next_action=NextAction(text_ru="Совет", primary="sign"),
        history=HistorySummary(payments_count=1),
    )


def _dummy_signal(rule_id: str, severity: str = "primary") -> Signal:
    return Signal(
        rule_id=rule_id,
        points=35,
        severity=severity,  # type: ignore[arg-type]
        reason_ru="Причина",
        evidence=Evidence(field="iik"),
    )


@pytest.fixture
def sign_env(seeded_db: Path) -> Iterator[tuple[FastAPI, Path, TestClient, TestClient]]:
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


class TestPolicyUnitAndDemoParity:
    def test_policy_constants_match_demo_main(self) -> None:
        assert policy.MIN_DIRECTOR_COMMENT_LEN == DEMO_MIN_DIRECTOR_COMMENT_LEN
        assert policy.TRUST_ALLOWED_SIGNAL_IDS == DEMO_TRUST_ALLOWED_SIGNAL_IDS

    def test_can_trust_matches_demo_across_verdicts_and_signals(self) -> None:
        req = CheckRequest(
            recipient_name="ТОО Поставщик",
            recipient_bin="180947320524",
            recipient_iik="KZ509650006872032298",
            recipient_bik="IRTYKZKA",
            amount_kzt=700000,
        )
        cases = [
            _dummy_check("yellow", [_dummy_signal("iik_changed")]),
            _dummy_check("yellow", [_dummy_signal("bank_changed")]),
            _dummy_check("yellow", [_dummy_signal("amount_anomaly")]),
            _dummy_check(
                "yellow",
                [_dummy_signal("iik_changed"), _dummy_signal("bcc_account_other_owner", "block")],
            ),
            _dummy_check("red", [_dummy_signal("iik_changed")]),
            _dummy_check("green", []),
            _dummy_check("grey", [_dummy_signal("first_payment", "info")]),
            _dummy_check("invalid", [_dummy_signal("invalid_iik", "block")]),
        ]
        for chk in cases:
            demo_apr = DemoApproval(id="apr-1", request=req, check=chk)
            assert policy.can_trust(chk) == demo_can_trust_approval(demo_apr)

    def test_sign_decision_all_11_rows_unit(self) -> None:
        sha = "sha-current"

        # Row 1: signed -> already_signed
        r1 = policy.sign_decision(
            role="accountant", status="signed", previous_verdict="green", fresh_verdict="green",
            payment_request_sha256=sha, approval_status=None, approval_request_sha256=None,
            accountant_ack=False,
        )
        assert not r1.allowed and r1.block_code == "already_signed"

        # Row 2: postponed / cancelled -> not_signable_status
        for st in ("postponed", "cancelled"):
            r2 = policy.sign_decision(
                role="accountant", status=st, previous_verdict="green", fresh_verdict="green",
                payment_request_sha256=sha, approval_status=None, approval_request_sha256=None,
                accountant_ack=False,
            )
            assert not r2.allowed and r2.block_code == "not_signable_status"

        # Row 3: pending_approval -> approval_pending
        r3 = policy.sign_decision(
            role="accountant", status="pending_approval", previous_verdict="yellow",
            fresh_verdict="yellow", payment_request_sha256=sha, approval_status="pending",
            approval_request_sha256=sha, accountant_ack=True,
        )
        assert not r3.allowed and r3.block_code == "approval_pending"

        # Row 4: rejected -> approval_rejected
        r4 = policy.sign_decision(
            role="director", status="rejected", previous_verdict="red", fresh_verdict="red",
            payment_request_sha256=sha, approval_status="rejected", approval_request_sha256=sha,
            accountant_ack=False,
        )
        assert not r4.allowed and r4.block_code == "approval_rejected"

        # Row 5: verdict worsened (green < grey < yellow < red < invalid) -> verdict_changed
        for prev_v, fresh_v in (
            ("green", "grey"),
            ("grey", "yellow"),
            ("yellow", "red"),
            ("red", "invalid"),
        ):
            r5 = policy.sign_decision(
                role="accountant", status="approved", previous_verdict=prev_v, fresh_verdict=fresh_v,
                payment_request_sha256=sha, approval_status="approved", approval_request_sha256=sha,
                accountant_ack=True,
            )
            assert not r5.allowed and r5.block_code == "verdict_changed" and r5.supersede_approval

        # Row 6: invalid -> invalid_requisites (even if previously invalid)
        r6 = policy.sign_decision(
            role="accountant", status="checked", previous_verdict="invalid",
            fresh_verdict="invalid", payment_request_sha256=sha, approval_status=None,
            approval_request_sha256=None, accountant_ack=True,
        )
        assert not r6.allowed and r6.block_code == "invalid_requisites"

        # Row 7: approved with matching request_sha256 -> allowed; mismatched sha -> denied
        r7_ok = policy.sign_decision(
            role="accountant", status="approved", previous_verdict="red", fresh_verdict="red",
            payment_request_sha256=sha, approval_status="approved", approval_request_sha256=sha,
            accountant_ack=False,
        )
        assert r7_ok.allowed and not r7_ok.set_accountant_ack

        r7_mismatch = policy.sign_decision(
            role="accountant", status="approved", previous_verdict="red", fresh_verdict="red",
            payment_request_sha256=sha, approval_status="approved",
            approval_request_sha256="sha-different", accountant_ack=True,
        )
        assert not r7_mismatch.allowed and r7_mismatch.block_code == "red_requires_approval"

        # Row 8: green -> allowed
        r8 = policy.sign_decision(
            role="director", status="checked", previous_verdict="green", fresh_verdict="green",
            payment_request_sha256=sha, approval_status=None, approval_request_sha256=None,
            accountant_ack=False,
        )
        assert r8.allowed

        # Row 9: red without approval -> red_requires_approval
        r9 = policy.sign_decision(
            role="accountant", status="checked", previous_verdict="red", fresh_verdict="red",
            payment_request_sha256=sha, approval_status=None, approval_request_sha256=None,
            accountant_ack=True,
        )
        assert not r9.allowed and r9.block_code == "red_requires_approval"

        # Row 10: yellow/grey with accountant_ack=True and role=accountant -> allowed
        for v in ("yellow", "grey"):
            r10 = policy.sign_decision(
                role="accountant", status="checked", previous_verdict=v, fresh_verdict=v,
                payment_request_sha256=sha, approval_status=None, approval_request_sha256=None,
                accountant_ack=True,
            )
            assert r10.allowed and r10.set_accountant_ack

        # Row 11: yellow/grey without ack OR with ack from director -> ack_or_approval_required
        for role, ack in (("accountant", False), ("director", False), ("director", True)):
            for v in ("yellow", "grey"):
                r11 = policy.sign_decision(
                    role=role, status="checked", previous_verdict=v, fresh_verdict=v,
                    payment_request_sha256=sha, approval_status=None, approval_request_sha256=None,
                    accountant_ack=ack,
                )
                assert not r11.allowed and r11.block_code == "ack_or_approval_required"


class TestSignRuleTableAPI:
    def _assert_sign_denied_logged(self, db_path: Path, payment_id: str, expected_code: str) -> None:
        conn = connect(db_path)
        try:
            entries = list_audit(conn, payment_id=payment_id, action="sign_denied", limit=5)
            assert entries, f"Expected sign_denied audit entry for {payment_id}"
            assert entries[0].details.get("code") == expected_code
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_row1_double_sign_and_row8_green(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sign_env
        queue = _load_queue_by_id()

        # Row 8: Accountant signs green payment
        p1 = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        s1 = acc.post(f"/api/v1/payments/{p1['id']}/sign", json={}, headers=CSRF)
        assert s1.status_code == 200
        assert s1.json()["status"] == "signed"
        assert s1.json()["signed_by"]["login"] == "accountant"
        assert s1.json()["signed_at"] is not None

        # Row 1: Double sign -> 409 already_signed + sign_denied in audit_log
        s2 = acc.post(f"/api/v1/payments/{p1['id']}/sign", json={}, headers=CSRF)
        assert s2.status_code == 409
        assert s2.json()["code"] == "already_signed"
        self._assert_sign_denied_logged(db_path, p1["id"], "already_signed")

        # Row 8: Director can also sign a green payment directly
        p2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-008"]),
            headers=CSRF,
        ).json()
        d_sign = director.post(f"/api/v1/payments/{p2['id']}/sign", headers=CSRF)
        assert d_sign.status_code == 200
        assert d_sign.json()["status"] == "signed"
        assert d_sign.json()["signed_by"]["login"] == "director"

    def test_row2_postponed_and_cancelled_blocked(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, _ = sign_env
        queue = _load_queue_by_id()

        p_post = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        assert acc.post(f"/api/v1/payments/{p_post['id']}/postpone", headers=CSRF).status_code == 200
        r_post = acc.post(f"/api/v1/payments/{p_post['id']}/sign", headers=CSRF)
        assert r_post.status_code == 409
        assert r_post.json()["code"] == "not_signable_status"
        self._assert_sign_denied_logged(db_path, p_post["id"], "not_signable_status")

        p_canc = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-008"]), headers=CSRF).json()
        assert acc.post(f"/api/v1/payments/{p_canc['id']}/cancel", headers=CSRF).status_code == 200
        r_canc = acc.post(f"/api/v1/payments/{p_canc['id']}/sign", headers=CSRF)
        assert r_canc.status_code == 409
        assert r_canc.json()["code"] == "not_signable_status"
        self._assert_sign_denied_logged(db_path, p_canc["id"], "not_signable_status")

    def test_row3_pending_and_row4_rejected_blocked(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sign_env
        queue = _load_queue_by_id()

        p = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-002"]), headers=CSRF).json()
        sent = acc.post(
            f"/api/v1/payments/{p['id']}/send-to-director",
            json={"accountant_note": "Прошу проверить"},
            headers=CSRF,
        ).json()
        apr_id = sent["approval"]["id"]

        # Row 3: pending_approval -> 409 approval_pending
        r_pend = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json={"accountant_ack": True},
            headers=CSRF,
        )
        assert r_pend.status_code == 409
        assert r_pend.json()["code"] == "approval_pending"
        self._assert_sign_denied_logged(db_path, p["id"], "approval_pending")

        # Director rejects -> Row 4: 409 approval_rejected
        dec = director.post(
            f"/api/v1/approvals/{apr_id}/decision",
            json={"decision": "rejected", "director_comment": "Сомнительный счёт"},
            headers=CSRF,
        )
        assert dec.status_code == 200
        assert dec.json()["status"] == "rejected"

        r_rej = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json={"accountant_ack": True},
            headers=CSRF,
        )
        assert r_rej.status_code == 409
        assert r_rej.json()["code"] == "approval_rejected"
        self._assert_sign_denied_logged(db_path, p["id"], "approval_rejected")

    def test_row5_verdict_changed_on_recheck_at_sign_time(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sign_env
        queue = _load_queue_by_id()

        # Case A: green payment worsens to yellow due to another active payment with same invoice #
        p1 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(
                queue["Q-001"],
                purpose="Оплата по счёту № 901 за стройматериалы",
            ),
            headers=CSRF,
        ).json()
        assert p1["check"]["verdict"] == "green"

        # Second active payment with same supplier and same invoice # 901 (different amount)
        p2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(
                queue["Q-001"],
                amount_kzt=1_400_000,
                purpose="Оплата по счёту № 901 за стройматериалы",
            ),
            headers=CSRF,
        ).json()
        assert p2["check"]["verdict"] == "yellow"

        # Now signing p1 re-runs engine -> duplicate_invoice -> yellow (worse than green) -> 409 verdict_changed
        r_chg = acc.post(f"/api/v1/payments/{p1['id']}/sign", json={}, headers=CSRF)
        assert r_chg.status_code == 409
        body = r_chg.json()
        assert body["code"] == "verdict_changed"
        assert "payment" in body
        assert body["payment"]["id"] == p1["id"]
        assert body["payment"]["status"] == "checked"
        assert body["payment"]["check"]["verdict"] == "yellow"
        assert body["payment"]["accountant_ack"] is False
        self._assert_sign_denied_logged(db_path, p1["id"], "verdict_changed")

        # Case B: approved yellow payment worsens to red before sign -> approval superseded + 409 verdict_changed
        p_y = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(
                queue["Q-002"],
                purpose="Оплата транспортных услуг по счёту № 777",
            ),
            headers=CSRF,
        ).json()
        assert p_y["check"]["verdict"] == "yellow"
        apr_id = acc.post(
            f"/api/v1/payments/{p_y['id']}/send-to-director",
            json={"accountant_note": "Новый счёт"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_id}/decision",
                json={"decision": "approved", "director_comment": "Одобрено без доверия"},
                headers=CSRF,
            ).status_code
            == 200
        )

        # Create another active payment to the same supplier with same invoice № 777 -> triggers duplicate_invoice (+35) on top of iik+bank (+50) = 85 -> red!
        acc.post(
            "/api/v1/payments",
            json=_to_payment_input(
                queue["Q-002"],
                amount_kzt=710_000,
                purpose="Оплата транспортных услуг по счёту № 777",
            ),
            headers=CSRF,
        )

        r_worsened = acc.post(f"/api/v1/payments/{p_y['id']}/sign", json={}, headers=CSRF)
        assert r_worsened.status_code == 409
        w_body = r_worsened.json()
        assert w_body["code"] == "verdict_changed"
        assert w_body["payment"]["status"] == "checked"
        assert w_body["payment"]["check"]["verdict"] == "red"
        assert w_body["payment"]["approval"] is None
        self._assert_sign_denied_logged(db_path, p_y["id"], "verdict_changed")

        conn = connect(db_path)
        try:
            apr_row = conn.execute("SELECT status FROM approvals WHERE id = ?", (apr_id,)).fetchone()
            assert apr_row is not None and apr_row["status"] == "superseded"
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_row6_invalid_and_row9_red_and_row7_approved_red(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sign_env
        queue = _load_queue_by_id()

        # Row 6: invalid -> 409 invalid_requisites
        p_inv = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-007"]), headers=CSRF).json()
        r_inv = acc.post(
            f"/api/v1/payments/{p_inv['id']}/sign",
            json={"accountant_ack": True},
            headers=CSRF,
        )
        assert r_inv.status_code == 409
        assert r_inv.json()["code"] == "invalid_requisites"
        self._assert_sign_denied_logged(db_path, p_inv["id"], "invalid_requisites")

        # Row 9: red without approval -> 409 red_requires_approval (even with ack or by director)
        p_red = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-003"]), headers=CSRF).json()
        assert p_red["check"]["verdict"] == "red"
        r_red_acc = acc.post(
            f"/api/v1/payments/{p_red['id']}/sign",
            json={"accountant_ack": True},
            headers=CSRF,
        )
        assert r_red_acc.status_code == 409
        assert r_red_acc.json()["code"] == "red_requires_approval"
        self._assert_sign_denied_logged(db_path, p_red["id"], "red_requires_approval")

        r_red_dir = director.post(f"/api/v1/payments/{p_red['id']}/sign", json={}, headers=CSRF)
        assert r_red_dir.status_code == 409
        assert r_red_dir.json()["code"] == "red_requires_approval"
        self._assert_sign_denied_logged(db_path, p_red["id"], "red_requires_approval")

        # Row 7: red after director approval with >=10 char comment -> signed
        apr_id = acc.post(
            f"/api/v1/payments/{p_red['id']}/send-to-director",
            json={"accountant_note": "Проверить с руководством"},
            headers=CSRF,
        ).json()["approval"]["id"]
        dec = director.post(
            f"/api/v1/approvals/{apr_id}/decision",
            json={
                "decision": "approved",
                "director_comment": "Лично созвонился с гендиректором поставщика и подтвердил",
            },
            headers=CSRF,
        )
        assert dec.status_code == 200
        assert dec.json()["status"] == "approved"

        signed = acc.post(f"/api/v1/payments/{p_red['id']}/sign", json={}, headers=CSRF)
        assert signed.status_code == 200
        assert signed.json()["status"] == "signed"

    def test_row10_and_row11_yellow_grey_ack_and_director_ack_rejected(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        prod_app, db_path, acc, director = sign_env
        queue = _load_queue_by_id()

        for qid, expected_verdict in (("Q-002", "yellow"), ("Q-004", "grey")):
            p = acc.post("/api/v1/payments", json=_to_payment_input(queue[qid]), headers=CSRF).json()
            assert p["check"]["verdict"] == expected_verdict

            # Row 11: accountant without ack -> 409 ack_or_approval_required
            no_ack = acc.post(f"/api/v1/payments/{p['id']}/sign", json={}, headers=CSRF)
            assert no_ack.status_code == 409
            assert no_ack.json()["code"] == "ack_or_approval_required"
            self._assert_sign_denied_logged(db_path, p["id"], "ack_or_approval_required")

            # Row 11: director with accountant_ack=True -> STILL rejected!
            dir_ack = director.post(
                f"/api/v1/payments/{p['id']}/sign",
                json={"accountant_ack": True},
                headers=CSRF,
            )
            assert dir_ack.status_code == 409
            assert dir_ack.json()["code"] == "ack_or_approval_required"
            self._assert_sign_denied_logged(db_path, p["id"], "ack_or_approval_required")

            # Row 10: accountant with accountant_ack=True -> signed + accountant_ack=True
            ok = acc.post(
                f"/api/v1/payments/{p['id']}/sign",
                json={"accountant_ack": True},
                headers=CSRF,
            )
            assert ok.status_code == 200
            assert ok.json()["status"] == "signed"
            assert ok.json()["accountant_ack"] is True

        # Analyst cannot sign -> 403 forbidden_role
        with TestClient(prod_app) as analyst:
            _login(analyst, "analyst")
            p_g = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
            assert analyst.post(f"/api/v1/payments/{p_g['id']}/sign", headers=CSRF).status_code == 403


class TestApprovalSupersedingAndDirectorRules:
    def test_approval_then_edit_supersedes_and_forbids_signing_again(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sign_env
        queue = _load_queue_by_id()

        # Create red payment, send to director, approve
        p_red = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-003"]), headers=CSRF).json()
        apr_id = acc.post(
            f"/api/v1/payments/{p_red['id']}/send-to-director",
            json={"accountant_note": "Проверить"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_id}/decision",
                json={
                    "decision": "approved",
                    "director_comment": "Подтвердили реквизиты по договору лично",
                },
                headers=CSRF,
            ).status_code
            == 200
        )

        # Direct PUT while approved is blocked (409 not_editable)
        direct_put = acc.put(
            f"/api/v1/payments/{p_red['id']}",
            json=_to_payment_input(queue["Q-003"], amount_kzt=5_100_000),
            headers=CSRF,
        )
        assert direct_put.status_code == 409
        assert direct_put.json()["code"] == "not_editable"

        # Postpone approved payment -> edit -> approval becomes superseded -> signing forbidden again
        assert acc.post(f"/api/v1/payments/{p_red['id']}/postpone", headers=CSRF).status_code == 200
        edited = acc.put(
            f"/api/v1/payments/{p_red['id']}",
            json=_to_payment_input(queue["Q-003"], amount_kzt=5_100_000),
            headers=CSRF,
        )
        assert edited.status_code == 200
        assert edited.json()["status"] == "checked"
        assert edited.json()["approval"] is None

        # Signing is now forbidden again (red_requires_approval)
        resign = acc.post(f"/api/v1/payments/{p_red['id']}/sign", json={}, headers=CSRF)
        assert resign.status_code == 409
        assert resign.json()["code"] == "red_requires_approval"

        # Trying to decide on the superseded approval returns 409 approval_superseded
        dec_sup = director.post(
            f"/api/v1/approvals/{apr_id}/decision",
            json={"decision": "approved", "director_comment": "Повторная попытка решения"},
            headers=CSRF,
        )
        assert dec_sup.status_code == 409
        assert dec_sup.json()["code"] == "approval_superseded"

        # Default GET /approvals hides superseded; ?status=superseded shows it
        default_list = director.get("/api/v1/approvals").json()
        assert all(item["id"] != apr_id for item in default_list)
        sup_list = director.get("/api/v1/approvals?status=superseded").json()
        assert [item["id"] for item in sup_list] == [apr_id]

        conn = connect(db_path)
        try:
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_director_decision_all_four_422_rules_and_trust_account(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        prod_app, db_path, acc, director = sign_env
        queue = _load_queue_by_id()

        # 1. Red payment -> 422 red_comment_required & 422 trust_not_allowed
        p_red = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-003"]), headers=CSRF).json()
        apr_red = acc.post(
            f"/api/v1/payments/{p_red['id']}/send-to-director",
            json={"accountant_note": "Красный"},
            headers=CSRF,
        ).json()["approval"]["id"]

        # Accountant cannot decide -> 403 forbidden_role
        assert (
            acc.post(
                f"/api/v1/approvals/{apr_red}/decision",
                json={"decision": "rejected"},
                headers=CSRF,
            ).status_code
            == 403
        )

        # 422 red_comment_required (empty / too short / whitespace)
        r_short = director.post(
            f"/api/v1/approvals/{apr_red}/decision",
            json={"decision": "approved", "director_comment": "   ок   "},
            headers=CSRF,
        )
        assert r_short.status_code == 422
        assert r_short.json()["code"] == "red_comment_required"

        # 422 trust_not_allowed (trust on red)
        r_trust_red = director.post(
            f"/api/v1/approvals/{apr_red}/decision",
            json={
                "decision": "approved",
                "director_comment": "Подтверждено лично по телефону из договора",
                "trust_account": True,
            },
            headers=CSRF,
        )
        assert r_trust_red.status_code == 422
        assert r_trust_red.json()["code"] == "trust_not_allowed"

        # 2. Yellow (iik_changed + bank_changed) -> 422 trust_comment_required, then approve + trust
        p_yellow = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-002"]), headers=CSRF).json()
        apr_y = acc.post(
            f"/api/v1/payments/{p_yellow['id']}/send-to-director",
            json={"accountant_note": "Смена банка"},
            headers=CSRF,
        ).json()["approval"]["id"]

        # List approvals shows pending first, can_trust=True for yellow, False for red
        aprs = director.get("/api/v1/approvals").json()
        by_id = {item["id"]: item for item in aprs}
        assert by_id[apr_y]["can_trust"] is True
        assert by_id[apr_red]["can_trust"] is False
        assert "analyst_details" not in by_id[apr_red]["check"]

        # Analyst sees analyst_details on GET /approvals
        with TestClient(prod_app) as analyst:
            _login(analyst, "analyst")
            ana_aprs = {item["id"]: item for item in analyst.get("/api/v1/approvals").json()}
            assert ana_aprs[apr_red]["check"]["analyst_details"] is not None

        # 422 trust_comment_required
        r_trust_short = director.post(
            f"/api/v1/approvals/{apr_y}/decision",
            json={
                "decision": "approved",
                "director_comment": "кратко",
                "trust_account": True,
            },
            headers=CSRF,
        )
        assert r_trust_short.status_code == 422
        assert r_trust_short.json()["code"] == "trust_comment_required"

        # Approve yellow WITH trust_account=True -> creates trusted_accounts row & decision:approved_trusted
        r_trust_ok = director.post(
            f"/api/v1/approvals/{apr_y}/decision",
            json={
                "decision": "approved",
                "director_comment": "Позвонили поставщику по договору, новый ИИК верный",
                "trust_account": True,
            },
            headers=CSRF,
        )
        assert r_trust_ok.status_code == 200
        assert r_trust_ok.json()["status"] == "approved"
        assert r_trust_ok.json()["trust_account"] is True

        # Second decision on already decided approval -> 409 approval_already_decided
        r_dup_dec = director.post(
            f"/api/v1/approvals/{apr_y}/decision",
            json={"decision": "rejected"},
            headers=CSRF,
        )
        assert r_dup_dec.status_code == 409
        assert r_dup_dec.json()["code"] == "approval_already_decided"

        # New payment to the now-trusted account evaluates as green (trusted=True)
        p_next = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-002"], purpose="Оплата по новому счёту № 999"),
            headers=CSRF,
        ).json()
        assert p_next["check"]["verdict"] == "green"
        assert p_next["check"]["trusted"] is True

        # 3. 422 invalid_payment_cannot_approve (even if an invalid approval row exists in DB)
        p_inv = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-007"]), headers=CSRF).json()
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT check_id, request_sha256, created_by FROM payments WHERE id = ?",
                (p_inv["id"],),
            ).fetchone()
            assert row is not None
            with tx(conn):
                conn.execute(
                    """
                    INSERT INTO approvals (
                        id, payment_id, check_id, request_sha256, status,
                        accountant_note, created_by, created_at
                    ) VALUES ('apr-inv-1', ?, ?, ?, 'pending', '', ?, ?)
                    """,
                    (p_inv["id"], row["check_id"], row["request_sha256"], row["created_by"], utc_now_iso()),
                )
        finally:
            conn.close()

        r_inv_apr = director.post(
            "/api/v1/approvals/apr-inv-1/decision",
            json={"decision": "approved", "director_comment": "Пытаемся одобрить неверный ИИК"},
            headers=CSRF,
        )
        assert r_inv_apr.status_code == 422
        assert r_inv_apr.json()["code"] == "invalid_payment_cannot_approve"

        # 4. Cross-company director gets 404 on foreign approval
        conn = connect(db_path)
        try:
            with tx(conn):
                conn.execute(
                    """
                    INSERT INTO users (company_id, login, full_name, role, password_hash, is_active, created_at)
                    VALUES ('comp-other', 'other_director', 'Другой Директор', 'director', ?, 1, ?)
                    """,
                    (hash_password(TEST_SEED_PW), utc_now_iso()),
                )
        finally:
            conn.close()

        with TestClient(prod_app) as other_dir:
            _login(other_dir, "other_director")
            cross = other_dir.post(
                f"/api/v1/approvals/{apr_red}/decision",
                json={"decision": "rejected"},
                headers=CSRF,
            )
            assert cross.status_code == 404
            assert cross.json()["code"] == "not_found"


class TestSignedHistoryDirectoryAndAuditAtomicity:
    def test_signed_payment_enters_history_updates_directory_and_keeps_audit_valid(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, _ = sign_env
        queue = _load_queue_by_id()

        # 1. First payment to new supplier (Q-004) -> grey, not in directory
        p_first = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-004"]),
            headers=CSRF,
        ).json()
        assert p_first["check"]["verdict"] == "grey"
        assert p_first["supplier"]["known"] is False

        # Sign with accountant_ack=True -> directory updated immediately
        signed_first = acc.post(
            f"/api/v1/payments/{p_first['id']}/sign",
            json={"accountant_ack": True},
            headers=CSRF,
        ).json()
        assert signed_first["status"] == "signed"
        assert signed_first["supplier"]["known"] is True
        assert signed_first["supplier"]["account_known"] is True

        # 2. Next payment to same supplier immediately sees signed payment in history -> green!
        p_second = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-004"], purpose="Оплата за полиграфию по счёту № 20"),
            headers=CSRF,
        ).json()
        assert p_second["check"]["verdict"] == "green"
        assert p_second["check"]["history"]["payments_count"] == 1

        # 3. Sign yellow payment (Q-002, new IIK + new bank) -> supplier_changes updated with account_added + bank_changed
        p_switch = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-002"]),
            headers=CSRF,
        ).json()
        assert p_switch["check"]["verdict"] == "yellow"
        signed_switch = acc.post(
            f"/api/v1/payments/{p_switch['id']}/sign",
            json={"accountant_ack": True},
            headers=CSRF,
        ).json()
        assert signed_switch["status"] == "signed"
        assert signed_switch["supplier"]["account_known"] is True
        assert signed_switch["supplier"]["requisites_changed_days_ago"] == 0

        # Next payment to the switched account is now green (in signed history)
        p_after_switch = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-002"], purpose="Оплата услуг по счёту № 319"),
            headers=CSRF,
        ).json()
        assert p_after_switch["check"]["verdict"] == "green"

        conn = connect(db_path)
        try:
            changes = conn.execute(
                "SELECT kind FROM supplier_changes WHERE payment_id = ? ORDER BY id ASC",
                (p_switch["id"],),
            ).fetchall()
            assert [c["kind"] for c in changes] == ["account_added", "bank_changed"]
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_sign_and_directory_update_are_atomic_in_one_transaction(
        self,
        sign_env: tuple[FastAPI, Path, TestClient, TestClient],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prod_app, db_path, acc, _ = sign_env
        queue = _load_queue_by_id()
        p = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()

        def _boom(*args: Any, **kwargs: Any) -> int:
            raise RuntimeError("simulated directory failure")

        monkeypatch.setattr(payments_service, "register_signed_payment", _boom)

        with TestClient(prod_app, raise_server_exceptions=False) as non_raising:
            _login(non_raising, "accountant")
            resp = non_raising.post(f"/api/v1/payments/{p['id']}/sign", json={}, headers=CSRF)
            assert resp.status_code == 500

        # Payment status MUST still be 'checked' (rolled back atomically!)
        conn = connect(db_path)
        try:
            row = conn.execute("SELECT status, signed_at FROM payments WHERE id = ?", (p["id"],)).fetchone()
            assert row is not None
            assert row["status"] == "checked"
            assert row["signed_at"] is None
            assert verify_chain(conn).ok is True
        finally:
            conn.close()
