"""Tests for bank-wide anonymized antifraud signals, rules, privacy, Q-003, and /api/metrics."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.risk.bank_signals import (
    clear_bank_signals_cache,
    is_bank_known_bin,
    load_bank_signals,
)
from app.risk.config import DEMO_TODAY
from app.risk.engine import check_payment, localize_check_result
from app.risk.rules import (
    build_analyst_details,
    rule_fresh_iik_many_payers,
    rule_iik_on_watchlist,
    rule_iik_reported_by_clients,
)
from app.schemas import CheckRequest
from app.store import DEFAULT_DATA_DIR, Store, store
from scripts.generate_data import BIK_BY_CODE, generate_bin, generate_iik

KZ_SPECIFIC_LETTERS: set[str] = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")


def _make_clean_external_request(
    *,
    recipient_iik: str,
    recipient_bin: str | None = None,
    recipient_name: str = "ТОО «Сфера Контракт»",
    amount_kzt: float = 650_000,
    purpose: str = "Оплата по договору поставки оборудования, счёт № 701",
    seed: int = 4242,
) -> CheckRequest:
    rng = random.Random(seed)
    code = recipient_iik[4:7]
    return CheckRequest(
        payer_id="client-technostroy",
        recipient_name=recipient_name,
        recipient_bin=recipient_bin or generate_bin(rng, year=20, month=5),
        recipient_iik=recipient_iik,
        recipient_bik=BIK_BY_CODE[code],
        amount_kzt=amount_kzt,
        purpose=purpose,
    )


def _queue_req(data_store: Store, qid: str) -> CheckRequest:
    item = next(q for q in data_store.queue if q["id"] == qid)
    return CheckRequest(
        payer_id=item["payer_id"],
        recipient_name=item["recipient_name"],
        recipient_bin=item["recipient_bin"],
        recipient_iik=item["recipient_iik"],
        recipient_bik=item["recipient_bik"],
        amount_kzt=item["amount_kzt"],
        purpose=item["purpose"],
    )


class TestBankwideRuleComplaints:
    def test_clean_attack_and_edge_thresholds(self) -> None:
        s = Store()
        rng = random.Random(7101)
        clean_iik = generate_iik(rng, "722", prefix="000")
        req = _make_clean_external_request(recipient_iik=clean_iik)

        # Clean: IIK absent from complaints -> None
        assert rule_iik_reported_by_clients(req, s, bank_signals={"complaints": {}}) is None
        # Edge: count=0 -> None
        assert (
            rule_iik_reported_by_clients(
                req,
                s,
                bank_signals={"complaints": {clean_iik: {"count": 0, "last_reported_at": "2026-04-19"}}},
            )
            is None
        )

        # Attack (1 or 2 complaints) -> primary 60 -> yellow alone in engine
        for cnt in (1, 2):
            signals_override = {
                "complaints": {clean_iik: {"count": cnt, "last_reported_at": "2026-04-18"}}
            }
            sig = rule_iik_reported_by_clients(req, s, bank_signals=signals_override)
            assert sig is not None
            assert sig.rule_id == "iik_reported_by_clients"
            assert sig.severity == "primary"
            assert sig.points == 60
            assert sig.evidence.since is None

            s_local = Store()
            s_local.bank_signals = signals_override  # type: ignore[attr-defined]
            res = check_payment(req, s_local)
            assert res.verdict == "yellow"
            assert res.score == 60

        # Attack (>=3 complaints) -> block 100 -> red in engine
        for cnt in (3, 6):
            signals_override = {
                "complaints": {clean_iik: {"count": cnt, "last_reported_at": "2026-04-19"}}
            }
            sig = rule_iik_reported_by_clients(req, s, bank_signals=signals_override)
            assert sig is not None
            assert sig.rule_id == "iik_reported_by_clients"
            assert sig.severity == "block"
            assert sig.points == 100
            assert "3+" in sig.reason_ru
            assert sig.evidence.since is None

            s_local = Store()
            s_local.bank_signals = signals_override  # type: ignore[attr-defined]
            res = check_payment(req, s_local)
            assert res.verdict == "red"
            assert res.score == 100


class TestBankwideRuleWatchlist:
    def test_clean_attack_and_edge(self) -> None:
        s = Store()
        rng = random.Random(7202)
        ext_iik = generate_iik(rng, "965", prefix="000")
        req = _make_clean_external_request(recipient_iik=ext_iik)

        # Clean: not on watchlist -> None
        assert rule_iik_on_watchlist(req, s, bank_signals={"mule_watchlist": {}}) is None
        # Edge: explicit False entry -> None
        assert rule_iik_on_watchlist(req, s, bank_signals={"mule_watchlist": {ext_iik: False}}) is None

        # Attack: on watchlist -> block red (even for typo-free external account)
        override = {
            "mule_watchlist": {
                ext_iik: {
                    "source": "Антифрод-центр НБ РК (синтетический реестр)",
                    "added_at": "2026-04-16",
                    "category": "dropper_account",
                }
            }
        }
        sig = rule_iik_on_watchlist(req, s, bank_signals=override)
        assert sig is not None
        assert sig.rule_id == "iik_on_watchlist"
        assert sig.severity == "block"
        assert sig.points == 100
        assert sig.evidence.since is None

        s_local = Store()
        s_local.bank_signals = override  # type: ignore[attr-defined]
        res = check_payment(req, s_local)
        assert res.verdict == "red"
        assert res.score == 100
        assert res.signals[0].rule_id == "iik_on_watchlist"

        # Dataset-backed external watchlist IIK closes "clean external dropper" blind spot
        dataset = load_bank_signals(DEFAULT_DATA_DIR)
        watch_iik = next(iter(dataset["mule_watchlist"]))
        watch_req = _make_clean_external_request(recipient_iik=watch_iik)
        watch_res = check_payment(watch_req, s)
        assert watch_res.verdict == "red"
        assert watch_res.score == 100
        assert any(sg.rule_id == "iik_on_watchlist" for sg in watch_res.signals)


class TestBankwideRuleFreshInflows:
    def test_clean_attack_boundary_and_bank_known_bin_exemption(self) -> None:
        s = Store()
        rng = random.Random(7303)
        ext_iik = generate_iik(rng, "722", prefix="000")
        unknown_bin = generate_bin(rng, year=22, month=4)
        req = _make_clean_external_request(recipient_iik=ext_iik, recipient_bin=unknown_bin)

        # Clean: no fresh_inflows record
        assert rule_fresh_iik_many_payers(req, s, bank_signals={"fresh_inflows": {}}) is None

        # Edge: 2 distinct payers (<3 threshold) -> None (grey in engine)
        override_2 = {
            "fresh_inflows": {
                ext_iik: {"distinct_payers_7d": 2, "total_amount_kzt_7d": 1_900_000, "window_days": 7}
            }
        }
        assert rule_fresh_iik_many_payers(req, s, bank_signals=override_2) is None

        # Attack (3 or 4 payers) -> primary 50 -> yellow
        for payers in (3, 4):
            override_med = {
                "fresh_inflows": {
                    ext_iik: {
                        "distinct_payers_7d": payers,
                        "total_amount_kzt_7d": 5_500_000,
                        "window_days": 7,
                    }
                }
            }
            sig = rule_fresh_iik_many_payers(req, s, bank_signals=override_med)
            assert sig is not None
            assert sig.rule_id == "fresh_iik_many_payers"
            assert sig.severity == "primary"
            assert sig.points == 50
            assert "3+" in sig.reason_ru

            s_local = Store()
            s_local.bank_signals = override_med  # type: ignore[attr-defined]
            res = check_payment(req, s_local)
            assert res.verdict == "yellow"
            assert res.score == 50

        # Attack (>=5 payers) -> primary 70 -> red
        for payers in (5, 9):
            override_hi = {
                "fresh_inflows": {
                    ext_iik: {
                        "distinct_payers_7d": payers,
                        "total_amount_kzt_7d": 16_200_000,
                        "window_days": 7,
                    }
                }
            }
            sig = rule_fresh_iik_many_payers(req, s, bank_signals=override_hi)
            assert sig is not None
            assert sig.rule_id == "fresh_iik_many_payers"
            assert sig.severity == "primary"
            assert sig.points == 70
            assert "5+" in sig.reason_ru

            s_local = Store()
            s_local.bank_signals = override_hi  # type: ignore[attr-defined]
            res = check_payment(req, s_local)
            assert res.verdict == "red"
            assert res.score == 70

        # Edge (bank_known_bin exemption): established utility with 12 first-time payers -> NOT flagged
        exempt_override = {
            "fresh_inflows": {
                ext_iik: {
                    "distinct_payers_7d": 12,
                    "total_amount_kzt_7d": 8_400_000,
                    "window_days": 7,
                }
            },
            "bank_known_bin": {
                unknown_bin: {
                    "first_seen_at": "2018-03-01",
                    "history_years": 8.1,
                    "active_payers_count": 500,
                    "category": "utility",
                }
            },
        }
        assert is_bank_known_bin(unknown_bin, exempt_override, today=DEMO_TODAY) is True
        assert rule_fresh_iik_many_payers(req, s, today=DEMO_TODAY, bank_signals=exempt_override) is None

        s_exempt = Store()
        s_exempt.bank_signals = exempt_override  # type: ignore[attr-defined]
        res_exempt = check_payment(req, s_exempt, today=DEMO_TODAY)
        assert res_exempt.verdict == "grey"
        assert all(sg.rule_id != "fresh_iik_many_payers" for sg in res_exempt.signals)

        # Edge: BIN seen recently (<2 years) in bank_known_bin is NOT exempt
        too_young_known = {
            **exempt_override,
            "bank_known_bin": {
                unknown_bin: {
                    "first_seen_at": "2025-11-01",
                    "history_years": 0.5,
                    "active_payers_count": 4,
                    "category": "startup",
                }
            },
        }
        assert is_bank_known_bin(unknown_bin, too_young_known, today=DEMO_TODAY) is False
        sig_not_exempt = rule_fresh_iik_many_payers(
            req, s, today=DEMO_TODAY, bank_signals=too_young_known
        )
        assert sig_not_exempt is not None and sig_not_exempt.points == 70

        # Edge: real popular utility from data/bank_signals.json stays grey (NOT flagged)
        dataset = load_bank_signals(DEFAULT_DATA_DIR)
        hist_bins = {p["recipient_bin"] for p in s.history}
        popular_bin, popular_info = next(
            (b, info)
            for b, info in dataset["bank_known_bin"].items()
            if b not in hist_bins and info.get("known_iiks")
        )
        popular_iik = popular_info["known_iiks"][0]
        assert dataset["fresh_inflows"][popular_iik]["distinct_payers_7d"] >= 5
        popular_req = _make_clean_external_request(
            recipient_iik=popular_iik,
            recipient_bin=popular_bin,
            recipient_name=s.registry[popular_bin],
            amount_kzt=320_000,
        )
        popular_res = check_payment(popular_req, s, today=DEMO_TODAY)
        assert popular_res.verdict == "grey"
        assert all(sg.rule_id != "fresh_iik_many_payers" for sg in popular_res.signals)

    def test_missing_bank_signals_file_degrades_gracefully(self, tmp_path: Path) -> None:
        clear_bank_signals_cache()
        empty = load_bank_signals(tmp_path)
        assert empty == {
            "complaints": {},
            "fresh_inflows": {},
            "mule_watchlist": {},
            "bank_known_bin": {},
        }


class TestAnonymityAndAnalystDetails:
    def test_client_output_is_strictly_anonymous_and_bucketed_while_analyst_gets_exact_counts(
        self,
    ) -> None:
        s = Store()
        rng = random.Random(7404)
        ext_iik = generate_iik(rng, "722", prefix="000")
        other_client_names = [
            s.client["name"],
            "ТехноСтрой Астана",
            "Вектор Трейд",
            "Алатау Снаб",
            "КазЛогистик Групп",
        ]
        other_client_bins = [
            s.client["bin"],
            *(p["recipient_bin"] for p in s.history[:3]),
        ]

        override = {
            "complaints": {ext_iik: {"count": 4, "last_reported_at": "2026-04-17"}},
            "fresh_inflows": {
                ext_iik: {
                    "distinct_payers_7d": 7,
                    "total_amount_kzt_7d": 15_430_000,
                    "window_days": 7,
                }
            },
            "mule_watchlist": {
                ext_iik: {
                    "source": "Антифрод-центр НБ РК (синтетический реестр)",
                    "added_at": "2026-04-14",
                    "category": "transit_mule",
                }
            },
            "bank_known_bin": {},
        }
        s.bank_signals = override  # type: ignore[attr-defined]
        req = _make_clean_external_request(recipient_iik=ext_iik)

        # Forbidden exact numbers, dates, volumes, and third-party identities in client view
        forbidden_in_client = (
            "2026-04-17",
            "2026-04-14",
            "15 430 000",
            "15430000",
            "transit_mule",
            *other_client_names,
            *other_client_bins,
        )

        for lang in ("ru", "kk", "en"):
            client_res = check_payment(req, s, lang=lang, include_analyst_details=False)
            assert client_res.verdict == "red"
            assert client_res.analyst_details is None
            dumped_client = client_res.model_dump()
            assert "analyst_details" not in dumped_client
            serialized_client = json.dumps(dumped_client, ensure_ascii=False)

            for secret in forbidden_in_client:
                assert secret not in serialized_client, f"Leaked {secret!r} in client ({lang})"

            by_rule = {sg.rule_id: sg for sg in client_res.signals}
            assert {
                "iik_reported_by_clients",
                "iik_on_watchlist",
                "fresh_iik_many_payers",
            } <= set(by_rule)

            # No exact complaint count '4' or exact payer count '7' in client reasons/evidence
            comp_sig = by_rule["iik_reported_by_clients"]
            assert "4" not in comp_sig.reason and "4" not in (comp_sig.evidence.actual or "")
            assert "3+" in comp_sig.reason
            assert comp_sig.evidence.since is None

            fresh_sig = by_rule["fresh_iik_many_payers"]
            assert "7" not in fresh_sig.reason and "7" not in (fresh_sig.evidence.actual or "")
            assert "5+" in fresh_sig.reason
            assert fresh_sig.evidence.since is None

            watch_sig = by_rule["iik_on_watchlist"]
            assert watch_sig.evidence.since is None

            if lang == "kk":
                for rid in ("iik_reported_by_clients", "iik_on_watchlist", "fresh_iik_many_payers"):
                    assert any(ch in KZ_SPECIFIC_LETTERS for ch in by_rule[rid].reason)

            # Analyst view gets exact counts, dates, and 7d sums
            analyst_res = check_payment(req, s, lang=lang, include_analyst_details=True)
            assert analyst_res.analyst_details is not None
            ana_by_rule = {d.rule_id: d for d in analyst_res.analyst_details.signal_details}
            assert {
                "iik_reported_by_clients",
                "iik_on_watchlist",
                "fresh_iik_many_payers",
            } <= set(ana_by_rule)

            assert "4" in ana_by_rule["iik_reported_by_clients"].reason
            assert "2026-04-17" in ana_by_rule["iik_reported_by_clients"].reason
            assert ana_by_rule["iik_reported_by_clients"].evidence.since == "2026-04-17"

            assert "7" in ana_by_rule["fresh_iik_many_payers"].reason
            assert "15 430 000" in ana_by_rule["fresh_iik_many_payers"].reason

            assert "transit_mule" in ana_by_rule["iik_on_watchlist"].reason
            assert "2026-04-14" in ana_by_rule["iik_on_watchlist"].reason
            assert ana_by_rule["iik_on_watchlist"].evidence.since == "2026-04-14"

        # Re-localization of analyst details matches direct check across kk and en
        ru_analyst = check_payment(req, s, lang="ru", include_analyst_details=True)
        for target_lang in ("kk", "en"):
            direct = check_payment(req, s, lang=target_lang, include_analyst_details=True)
            reloc = localize_check_result(ru_analyst, target_lang, include_analyst_details=True)
            assert reloc.analyst_details is not None and direct.analyst_details is not None
            assert [d.reason for d in reloc.analyst_details.signal_details] == [
                d.reason for d in direct.analyst_details.signal_details
            ]

    def test_bank_signals_json_has_no_third_party_client_pii(self) -> None:
        raw_text = (DEFAULT_DATA_DIR / "bank_signals.json").read_text(encoding="utf-8")
        s = Store()
        # No payer client names or client BIN anywhere in bank_signals.json
        assert s.client["name"] not in raw_text
        assert "ТехноСтрой" not in raw_text
        assert s.client["bin"] not in raw_text
        assert "Вектор Трейд" not in raw_text

        data = json.loads(raw_text)
        for comp in data["complaints"].values():
            assert set(comp.keys()) == {"count", "last_reported_at"}
        for inflow in data["fresh_inflows"].values():
            assert set(inflow.keys()) == {"distinct_payers_7d", "total_amount_kzt_7d", "window_days"}
        for watch in data["mule_watchlist"].values():
            assert set(watch.keys()) == {"source", "added_at", "category"}


class TestDemoQueueAndMetricsCompatibility:
    def test_q003_remains_red_with_bankwide_signals_and_all_10_queue_verdicts_intact(self) -> None:
        s = Store()
        assert len(s.queue) == 10
        for item in s.queue:
            res = check_payment(_queue_req(s, item["id"]), s)
            assert res.verdict == item["scenario"], f"{item['id']} verdict changed to {res.verdict}"

        q3_res = check_payment(_queue_req(s, "Q-003"), s, include_analyst_details=True)
        assert q3_res.verdict == "red"
        assert q3_res.score == 100
        q3_rules = [sg.rule_id for sg in q3_res.signals]
        assert q3_rules[0] == "bcc_account_other_owner"
        assert "iik_reported_by_clients" in q3_rules
        assert "fresh_iik_many_payers" in q3_rules

        # Analyst details on Q-003 carry exact bank-wide counts, while client check hides them
        q3_client = check_payment(_queue_req(s, "Q-003"), s, include_analyst_details=False)
        assert q3_client.analyst_details is None
        client_json = json.dumps(q3_client.model_dump(), ensure_ascii=False)
        assert "14 800 000" not in client_json
        assert "2026-04-18" not in client_json

        analyst = build_analyst_details(_queue_req(s, "Q-003"), s, q3_client.signals, today=DEMO_TODAY)
        ana_ids = {d.rule_id for d in analyst.signal_details}
        assert {"iik_reported_by_clients", "fresh_iik_many_payers"} <= ana_ids

    @pytest.mark.parametrize("lang", ["ru", "kk", "en"])
    def test_metrics_endpoint_works_and_includes_bankwide_kinds(self, lang: str) -> None:
        store.reset()
        try:
            with TestClient(app) as client:
                resp = client.get("/api/metrics", params={"lang": lang})
                assert resp.status_code == 200
                body = resp.json()
                assert body["summary"]["total_cases"] == 400
                assert body["summary"]["total_legit"] == 200
                assert body["summary"]["total_attack"] == 200

                by_kind = {row["kind"]: row for row in body["by_kind"]}
                assert "legit_popular_known_supplier" in by_kind
                assert by_kind["legit_popular_known_supplier"]["false_positive_rate"] == 0.0
                assert "legit_new_supplier_generic_word" in by_kind
                assert by_kind["legit_new_supplier_generic_word"]["total"] == 20
                assert by_kind["legit_new_supplier_generic_word"]["false_positive_rate"] == 0.0
                assert "attack_bankwide_external_drop" in by_kind
                assert by_kind["attack_bankwide_external_drop"]["detection_rate"] >= 0.85
                assert by_kind["legit_popular_known_supplier"]["label_text"].strip()
                assert by_kind["legit_new_supplier_generic_word"]["label_text"].strip()
                assert by_kind["attack_bankwide_external_drop"]["label_text"].strip()
        finally:
            store.reset()
