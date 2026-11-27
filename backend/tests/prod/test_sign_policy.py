"""Tests for B5: §5 server-side signing policy (all 11 rows), approvals, trust, history & audit."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.i18n import t
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
from app.risk.config import IDENTITY_SIGNAL_IDS
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
from app.settings import BACKEND_DIR, Settings
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
        info_first = Signal(
            rule_id="first_payment",
            points=0,
            severity="info",
            reason_ru="Первый платёж",
            evidence=Evidence(field="bin"),
        )
        info_verified = Signal(
            rule_id="bcc_owner_verified",
            points=0,
            severity="info",
            reason_ru="Подтверждено",
            evidence=Evidence(field="iik"),
        )
        cases: list[tuple[CheckResult, bool]] = [
            (_dummy_check("yellow", [_dummy_signal("iik_changed")]), True),
            # Single trust rule: weighted signals must include iik_changed (bank change alone is not enough).
            (_dummy_check("yellow", [_dummy_signal("bank_changed")]), False),
            (
                _dummy_check(
                    "yellow", [_dummy_signal("iik_changed"), _dummy_signal("bank_changed")]
                ),
                True,
            ),
            (_dummy_check("yellow", [_dummy_signal("amount_anomaly")]), False),
            (
                _dummy_check(
                    "yellow",
                    [_dummy_signal("iik_changed"), _dummy_signal("bcc_account_other_owner", "block")],
                ),
                False,
            ),
            (_dummy_check("red", [_dummy_signal("iik_changed")]), True),
            (_dummy_check("red", [_dummy_signal("bank_changed")]), False),
            (
                _dummy_check(
                    "red",
                    [_dummy_signal("iik_changed"), _dummy_signal("bank_changed")],
                ),
                True,
            ),
            (
                _dummy_check(
                    "red",
                    [_dummy_signal("iik_changed"), _dummy_signal("bank_changed"), info_first],
                ),
                True,
            ),
            (
                _dummy_check(
                    "red",
                    [_dummy_signal("iik_changed"), _dummy_signal("bank_changed"), info_verified],
                ),
                True,
            ),
            (
                _dummy_check(
                    "red",
                    [
                        _dummy_signal("iik_changed"),
                        _dummy_signal("bank_changed"),
                        _dummy_signal("lookalike_supplier"),
                    ],
                ),
                False,
            ),
            (
                _dummy_check(
                    "red",
                    [
                        _dummy_signal("iik_changed"),
                        _dummy_signal("bank_changed"),
                        _dummy_signal("iik_on_watchlist", "block"),
                    ],
                ),
                False,
            ),
            (
                _dummy_check(
                    "red",
                    [
                        _dummy_signal("iik_changed"),
                        _dummy_signal("bank_changed"),
                        _dummy_signal("urgent_wording", "amplifier"),
                    ],
                ),
                False,
            ),
            (_dummy_check("green", []), False),
            (_dummy_check("grey", [info_first]), False),
            (_dummy_check("invalid", [_dummy_signal("invalid_iik", "block")]), False),
        ]
        for chk, expected in cases:
            demo_apr = DemoApproval(id="apr-1", request=req, check=chk)
            assert policy.can_trust(chk) is expected
            assert demo_can_trust_approval(demo_apr) is expected

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
        s1 = acc.post(
            f"/api/v1/payments/{p1['id']}/sign",
            json=build_sign_payload(acc, p1["id"]),
            headers=CSRF,
        )
        assert s1.status_code == 200
        assert s1.json()["status"] == "signed"
        assert s1.json()["signed_by"]["login"] == "accountant"
        assert s1.json()["signed_at"] is not None

        # Row 1: Double sign -> 409 already_signed + sign_denied in audit_log
        s2 = acc.post(
            f"/api/v1/payments/{p1['id']}/sign",
            json=build_sign_payload(acc, p1["id"]),
            headers=CSRF,
        )
        assert s2.status_code == 409
        assert s2.json()["code"] == "already_signed"
        self._assert_sign_denied_logged(db_path, p1["id"], "already_signed")

        # Row 8: Director can also sign a green payment directly
        p2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-008"]),
            headers=CSRF,
        ).json()
        d_sign = director.post(
            f"/api/v1/payments/{p2['id']}/sign",
            json=build_sign_payload(director, p2["id"]),
            headers=CSRF,
        )
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
        r_post = acc.post(
            f"/api/v1/payments/{p_post['id']}/sign",
            json=build_sign_payload(acc, p_post["id"]),
            headers=CSRF,
        )
        assert r_post.status_code == 409
        assert r_post.json()["code"] == "not_signable_status"
        self._assert_sign_denied_logged(db_path, p_post["id"], "not_signable_status")

        p_canc = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-008"]), headers=CSRF).json()
        assert acc.post(f"/api/v1/payments/{p_canc['id']}/cancel", headers=CSRF).status_code == 200
        r_canc = acc.post(
            f"/api/v1/payments/{p_canc['id']}/sign",
            json=build_sign_payload(acc, p_canc["id"]),
            headers=CSRF,
        )
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
            json=build_sign_payload(acc, p["id"], accountant_ack=True),
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
            json=build_sign_payload(acc, p["id"], accountant_ack=True),
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
        r_chg = acc.post(
            f"/api/v1/payments/{p1['id']}/sign",
            json=build_sign_payload(acc, p1["id"]),
            headers=CSRF,
        )
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

        r_worsened = acc.post(
            f"/api/v1/payments/{p_y['id']}/sign",
            json=build_sign_payload(acc, p_y["id"]),
            headers=CSRF,
        )
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
            json=build_sign_payload(acc, p_inv["id"], accountant_ack=True),
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
            json=build_sign_payload(acc, p_red["id"], accountant_ack=True),
            headers=CSRF,
        )
        assert r_red_acc.status_code == 409
        assert r_red_acc.json()["code"] == "red_requires_approval"
        self._assert_sign_denied_logged(db_path, p_red["id"], "red_requires_approval")

        r_red_dir = director.post(
            f"/api/v1/payments/{p_red['id']}/sign",
            json=build_sign_payload(director, p_red["id"]),
            headers=CSRF,
        )
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

        signed = acc.post(
            f"/api/v1/payments/{p_red['id']}/sign",
            json=build_sign_payload(acc, p_red["id"]),
            headers=CSRF,
        )
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
            no_ack = acc.post(
                f"/api/v1/payments/{p['id']}/sign",
                json=build_sign_payload(acc, p["id"]),
                headers=CSRF,
            )
            assert no_ack.status_code == 409
            assert no_ack.json()["code"] == "ack_or_approval_required"
            self._assert_sign_denied_logged(db_path, p["id"], "ack_or_approval_required")

            # Row 11: director with accountant_ack=True -> STILL rejected!
            dir_ack = director.post(
                f"/api/v1/payments/{p['id']}/sign",
                json=build_sign_payload(director, p["id"], accountant_ack=True),
                headers=CSRF,
            )
            assert dir_ack.status_code == 409
            assert dir_ack.json()["code"] == "ack_or_approval_required"
            self._assert_sign_denied_logged(db_path, p["id"], "ack_or_approval_required")

            # Row 10: accountant with accountant_ack=True -> signed + accountant_ack=True
            ok = acc.post(
                f"/api/v1/payments/{p['id']}/sign",
                json=build_sign_payload(acc, p["id"], accountant_ack=True),
                headers=CSRF,
            )
            assert ok.status_code == 200
            assert ok.json()["status"] == "signed"
            assert ok.json()["accountant_ack"] is True

        # Analyst cannot sign -> 403 forbidden_role
        with TestClient(prod_app) as analyst:
            _login(analyst, "analyst")
            p_g = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
            assert (
                analyst.post(
                    f"/api/v1/payments/{p_g['id']}/sign",
                    json=build_sign_payload(analyst, p_g["id"]),
                    headers=CSRF,
                ).status_code
                == 403
            )


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
        resign = acc.post(
            f"/api/v1/payments/{p_red['id']}/sign",
            json=build_sign_payload(acc, p_red["id"]),
            headers=CSRF,
        )
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
        _, db_path, acc, director = sign_env
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
            json=build_sign_payload(acc, p_first["id"], accountant_ack=True),
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
            json=build_sign_payload(acc, p_switch["id"], accountant_ack=True),
            headers=CSRF,
        ).json()
        assert signed_switch["status"] == "signed"
        assert signed_switch["supplier"]["account_known"] is True
        assert signed_switch["supplier"]["requisites_changed_days_ago"] == 0

        # Account confirmation rule (H1): signed by the accountant alone, the new account is NOT
        # yet trusted history, so the next usual payment must not be green.
        p_after_switch = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-002"], purpose="Оплата услуг по счёту № 319"),
            headers=CSRF,
        ).json()
        assert p_after_switch["check"]["verdict"] != "green"
        assert {x["rule_id"] for x in p_after_switch["check"]["signals"]} & {
            "iik_changed",
            "bank_changed",
            "iik_recently_changed",
        }

        # The director approves the change; after a director-approved signature the account is
        # confirmed and the next usual payment to it is green.
        apr = acc.post(
            f"/api/v1/payments/{p_after_switch['id']}/send-to-director",
            json={"accountant_note": "Реквизиты подтверждены по телефону из договора"},
            headers=CSRF,
        ).json()["approval"]["id"]
        decided = director.post(
            f"/api/v1/approvals/{apr}/decision",
            json={
                "decision": "approved",
                "director_comment": "Подтверждено лично по телефону из договора",
            },
            headers=CSRF,
        )
        assert decided.status_code == 200, decided.text
        signed_after = acc.post(
            f"/api/v1/payments/{p_after_switch['id']}/sign",
            json=build_sign_payload(acc, p_after_switch["id"]),
            headers=CSRF,
        )
        assert signed_after.status_code == 200, signed_after.text
        assert signed_after.json()["status"] == "signed"

        p_confirmed = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-002"], purpose="Оплата услуг по счёту № 320"),
            headers=CSRF,
        ).json()
        # Only the aggregate 72h structuring signal may remain (three payments in one test day);
        # the account-change signals are gone and the verdict is not worsened by them.
        confirmed_rules = {x["rule_id"] for x in p_confirmed["check"]["signals"]}
        assert not confirmed_rules & {"iik_changed", "bank_changed", "iik_recently_changed"}
        assert confirmed_rules <= {"structuring_72h"}

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
            resp = non_raising.post(
                f"/api/v1/payments/{p['id']}/sign",
                json=build_sign_payload(non_raising, p["id"]),
                headers=CSRF,
            )
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


class TestIdentitySignalSignPolicy:
    def test_identity_signal_constant_matches_spec_and_frontend(self) -> None:
        expected = frozenset(
            {
                "lookalike_supplier",
                "bin_name_mismatch",
                "entity_type_mismatch",
                "kbe_mismatch",
                "iik_belongs_to_other_counterparty",
                "mixed_script_name",
                "iik_reported_by_clients",
                "fresh_iik_many_payers",
            }
        )
        assert IDENTITY_SIGNAL_IDS == expected

        ts_path = BACKEND_DIR.parent / "frontend" / "src" / "lib" / "identitySignals.ts"
        ts_src = ts_path.read_text(encoding="utf-8")
        block = re.search(
            r"export const IDENTITY_SIGNAL_IDS\s*=\s*\[(.*?)\]\s*as const",
            ts_src,
            re.DOTALL,
        )
        assert block is not None
        ts_ids = frozenset(re.findall(r'"([a-z0-9_]+)"', block.group(1)))
        assert ts_ids == IDENTITY_SIGNAL_IDS

    @pytest.mark.parametrize("signal_id", sorted(IDENTITY_SIGNAL_IDS))
    @pytest.mark.parametrize("verdict", ["yellow", "grey"])
    def test_sign_decision_and_permissions_block_every_identity_signal_unit(
        self, signal_id: str, verdict: Verdict
    ) -> None:
        sha = "sha-identity-unit"

        for role in ("accountant", "director"):
            for ack in (False, True):
                res = policy.sign_decision(
                    role=role,
                    status="checked",
                    previous_verdict=verdict,
                    fresh_verdict=verdict,
                    payment_request_sha256=sha,
                    approval_status=None,
                    approval_request_sha256=None,
                    accountant_ack=ack,
                    signal_ids=[signal_id],
                )
                assert res.allowed is False
                assert res.block_code == "identity_requires_approval"

        # Permissions for accountant (pass generator to verify single-pass iterables work safely)
        perms = policy.permissions_for(
            role="accountant",
            status="checked",
            verdict=verdict,
            payment_request_sha256=sha,
            signal_ids=(s for s in (signal_id,)),
        )
        assert perms.can_sign is False
        assert perms.sign_requires_ack is False
        assert perms.sign_block_code == "identity_requires_approval"
        assert perms.can_send_to_director is True

        # Director approval unlocks signing even when identity signals are present
        approved_res = policy.sign_decision(
            role="accountant",
            status="approved",
            previous_verdict=verdict,
            fresh_verdict=verdict,
            payment_request_sha256=sha,
            approval_status="approved",
            approval_request_sha256=sha,
            accountant_ack=False,
            signal_ids=[signal_id],
        )
        assert approved_res.allowed is True
        approved_perms = policy.permissions_for(
            role="accountant",
            status="approved",
            verdict=verdict,
            payment_request_sha256=sha,
            approval_status="approved",
            approval_request_sha256=sha,
            signal_ids=[signal_id],
        )
        assert approved_perms.can_sign is True
        assert approved_perms.sign_requires_ack is False
        assert approved_perms.sign_block_code is None

    @pytest.mark.parametrize("signal_id", sorted(IDENTITY_SIGNAL_IDS))
    @pytest.mark.parametrize("verdict", ["yellow", "grey"])
    def test_api_sign_rejects_each_identity_signal_with_409_and_audit(
        self,
        sign_env: tuple[FastAPI, Path, TestClient, TestClient],
        monkeypatch: pytest.MonkeyPatch,
        signal_id: str,
        verdict: Verdict,
    ) -> None:
        _, db_path, acc, director = sign_env
        queue = _load_queue_by_id()

        def _fake_check_payment(*args: Any, **kwargs: Any) -> CheckResult:
            return CheckResult(
                check_id=f"chk-id-{uuid.uuid4().hex[:10]}",
                verdict=verdict,
                score=40 if verdict == "yellow" else 25,
                headline_ru="Сомнения в получателе",
                signals=[_dummy_signal(signal_id)],
                comparison=[],
                next_action=NextAction(text_ru="Отправьте директору", primary="send_to_director"),
                history=HistorySummary(payments_count=0),
            )

        monkeypatch.setattr(payments_service, "check_payment", _fake_check_payment)

        created = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-004"]),
            headers=CSRF,
        )
        assert created.status_code == 201
        payment = created.json()
        assert payment["permissions"]["can_sign"] is False
        assert payment["permissions"]["sign_requires_ack"] is False
        assert payment["permissions"]["sign_block_code"] == "identity_requires_approval"
        assert payment["permissions"]["can_send_to_director"] is True

        # Signing with accountant_ack=True must return 409 identity_requires_approval
        denied = acc.post(
            f"/api/v1/payments/{payment['id']}/sign",
            json=build_sign_payload(acc, payment["id"], accountant_ack=True),
            headers=CSRF,
        )
        assert denied.status_code == 409
        assert denied.json()["code"] == "identity_requires_approval"
        assert denied.json()["detail"] == t("error.prod.identity_requires_approval", "ru")

        # Audit log records sign_denied with identity_requires_approval and intact hash chain
        conn = connect(db_path)
        try:
            entries = list_audit(conn, payment_id=payment["id"], action="sign_denied", limit=5)
            assert len(entries) == 1
            assert entries[0].details.get("code") == "identity_requires_approval"
            assert signal_id in entries[0].signal_ids
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

        # Director approval path still unlocks signing
        sent = acc.post(
            f"/api/v1/payments/{payment['id']}/send-to-director",
            json={"accountant_note": "Проверить личность получателя"},
            headers=CSRF,
        )
        assert sent.status_code == 200
        apr_id = sent.json()["approval"]["id"]
        dec = director.post(
            f"/api/v1/approvals/{apr_id}/decision",
            json={
                "decision": "approved",
                "director_comment": "Подтвердили реквизиты поставщика напрямую",
            },
            headers=CSRF,
        )
        assert dec.status_code == 200

        signed = acc.post(
            f"/api/v1/payments/{payment['id']}/sign",
            json=build_sign_payload(acc, payment["id"]),
            headers=CSRF,
        )
        assert signed.status_code == 200
        assert signed.json()["status"] == "signed"

    def test_real_engine_identity_yellow_vs_regular_yellow_and_i18n(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sign_env
        queue = _load_queue_by_id()

        # 1. Q-010 triggers real entity_type_mismatch on yellow -> blocked for accountant ack
        p_id = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-010"]),
            headers=CSRF,
        ).json()
        assert p_id["check"]["verdict"] == "yellow"
        assert "entity_type_mismatch" in {s["rule_id"] for s in p_id["check"]["signals"]}
        assert p_id["permissions"]["can_sign"] is False
        assert p_id["permissions"]["sign_requires_ack"] is False
        assert p_id["permissions"]["sign_block_code"] == "identity_requires_approval"
        assert p_id["permissions"]["can_send_to_director"] is True

        for lang in ("ru", "kk", "en"):
            resp = acc.post(
                f"/api/v1/payments/{p_id['id']}/sign?lang={lang}",
                json=build_sign_payload(acc, p_id["id"], accountant_ack=True),
                headers=CSRF,
            )
            assert resp.status_code == 409
            assert resp.json() == {
                "code": "identity_requires_approval",
                "detail": t("error.prod.identity_requires_approval", lang),
            }

        conn = connect(db_path)
        try:
            denied_entries = list_audit(conn, payment_id=p_id["id"], action="sign_denied", limit=10)
            assert len(denied_entries) == 3
            assert all(e.details.get("code") == "identity_requires_approval" for e in denied_entries)
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

        # Director approval unlocks Q-010
        apr_id = acc.post(
            f"/api/v1/payments/{p_id['id']}/send-to-director",
            json={"accountant_note": "ИИН вместо БИН в наименовании ТОО"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_id}/decision",
                json={
                    "decision": "approved",
                    "director_comment": "Проверено с руководителем контрагента",
                },
                headers=CSRF,
            ).status_code
            == 200
        )
        refreshed = acc.get(f"/api/v1/payments/{p_id['id']}").json()
        assert refreshed["permissions"]["can_sign"] is True
        assert refreshed["permissions"]["sign_requires_ack"] is False
        assert refreshed["permissions"]["sign_block_code"] is None
        signed_id = acc.post(
            f"/api/v1/payments/{p_id['id']}/sign",
            json=build_sign_payload(acc, p_id["id"]),
            headers=CSRF,
        )
        assert signed_id.status_code == 200
        assert signed_id.json()["status"] == "signed"

        # 2. Q-002 (yellow without identity signal: iik_changed + bank_changed) remains signable with ack
        p_regular = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-002"]),
            headers=CSRF,
        ).json()
        assert p_regular["check"]["verdict"] == "yellow"
        assert not (IDENTITY_SIGNAL_IDS & {s["rule_id"] for s in p_regular["check"]["signals"]})
        assert p_regular["permissions"]["can_sign"] is True
        assert p_regular["permissions"]["sign_requires_ack"] is True
        assert p_regular["permissions"]["sign_block_code"] is None

        signed_reg = acc.post(
            f"/api/v1/payments/{p_regular['id']}/sign",
            json=build_sign_payload(acc, p_regular["id"], accountant_ack=True),
            headers=CSRF,
        )
        assert signed_reg.status_code == 200
        assert signed_reg.json()["status"] == "signed"
        assert signed_reg.json()["accountant_ack"] is True


class TestRedBankChangeTrustFlow:
    def test_prod_red_bank_change_only_can_be_approved_and_trusted(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director = sign_env
        queue = _load_queue_by_id()

        # Q-002 at 850k (>= supplier median 820k) yields RED (65) with ONLY iik_changed + bank_changed
        red_bank_payload = _to_payment_input(
            queue["Q-002"],
            amount_kzt=850_000,
            purpose="Оплата транспортных услуг по счёту № 601",
        )
        p_red_bank = acc.post("/api/v1/payments", json=red_bank_payload, headers=CSRF).json()
        assert p_red_bank["check"]["verdict"] == "red"
        assert p_red_bank["check"]["score"] == 65
        assert {s["rule_id"] for s in p_red_bank["check"]["signals"]} == {
            "iik_changed",
            "bank_changed",
        }

        apr_id = acc.post(
            f"/api/v1/payments/{p_red_bank['id']}/send-to-director",
            json={"accountant_note": "Поставщик перешёл в другой банк"},
            headers=CSRF,
        ).json()["approval"]["id"]

        # GET /approvals exposes can_trust=True for this red bank-change payment
        aprs = {item["id"]: item for item in director.get("/api/v1/approvals").json()}
        assert aprs[apr_id]["can_trust"] is True

        # Comment < 10 chars -> 422 trust_comment_required
        short_resp = director.post(
            f"/api/v1/approvals/{apr_id}/decision",
            json={
                "decision": "approved",
                "director_comment": "коротко",
                "trust_account": True,
            },
            headers=CSRF,
        )
        assert short_resp.status_code == 422
        assert short_resp.json()["code"] == "trust_comment_required"

        # Valid >= 10 char comment -> 200 approved + trust_account=True
        ok_resp = director.post(
            f"/api/v1/approvals/{apr_id}/decision",
            json={
                "decision": "approved",
                "director_comment": "Позвонили поставщику по договору и подтвердили новый банк",
                "trust_account": True,
            },
            headers=CSRF,
        )
        assert ok_resp.status_code == 200
        assert ok_resp.json()["status"] == "approved"
        assert ok_resp.json()["trust_account"] is True

        # Later payment to the same trusted BIN+IIK evaluates as green with trusted=True
        later_payload = _to_payment_input(
            queue["Q-002"],
            amount_kzt=850_000,
            purpose="Оплата транспортных услуг по счёту № 602",
        )
        p_later = acc.post("/api/v1/payments", json=later_payload, headers=CSRF).json()
        assert p_later["check"]["verdict"] == "green"
        assert p_later["check"]["trusted"] is True
        assert p_later["check"]["trusted_info"] is not None
        later_rule_ids = {s["rule_id"] for s in p_later["check"]["signals"]}
        assert "trusted_account" in later_rule_ids
        assert "iik_changed" not in later_rule_ids
        assert "bank_changed" not in later_rule_ids

        # Original approved red payment can be signed cleanly
        signed = acc.post(
            f"/api/v1/payments/{p_red_bank['id']}/sign",
            json=build_sign_payload(acc, p_red_bank["id"]),
            headers=CSRF,
        )
        assert signed.status_code == 200
        assert signed.json()["status"] == "signed"

        conn = connect(db_path)
        try:
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_prod_red_with_other_signals_refuses_trust(
        self, sign_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, _, acc, director = sign_env
        queue = _load_queue_by_id()

        # 1. Q-002 at 850k + urgent wording -> red with 3 weighted signals -> can_trust=False
        p_urgent = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(
                queue["Q-002"],
                amount_kzt=850_000,
                purpose="Оплата срочно по счёту № 603",
            ),
            headers=CSRF,
        ).json()
        assert p_urgent["check"]["verdict"] == "red"
        apr_urgent = acc.post(
            f"/api/v1/payments/{p_urgent['id']}/send-to-director",
            json={"accountant_note": "Срочный счёт"},
            headers=CSRF,
        ).json()["approval"]["id"]

        # 2. Q-003 (lookalike + mixed script + block/other signals) -> can_trust=False
        p_attack = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-003"]),
            headers=CSRF,
        ).json()
        assert p_attack["check"]["verdict"] == "red"
        apr_attack = acc.post(
            f"/api/v1/payments/{p_attack['id']}/send-to-director",
            json={"accountant_note": "Подозрительная подмена"},
            headers=CSRF,
        ).json()["approval"]["id"]

        aprs = {item["id"]: item for item in director.get("/api/v1/approvals").json()}
        assert aprs[apr_urgent]["can_trust"] is False
        assert aprs[apr_attack]["can_trust"] is False

        for apr_id in (apr_urgent, apr_attack):
            refused = director.post(
                f"/api/v1/approvals/{apr_id}/decision",
                json={
                    "decision": "approved",
                    "director_comment": "Попытка доверить подозрительный красный счёт",
                    "trust_account": True,
                },
                headers=CSRF,
            )
            assert refused.status_code == 422
            assert refused.json()["code"] == "trust_not_allowed"
