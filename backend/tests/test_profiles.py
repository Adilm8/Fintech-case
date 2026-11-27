"""Unit tests verifying SupplierProfile equivalence with rules.py and LRU cache semantics."""

from __future__ import annotations

import random
import statistics
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from app.risk.config import CLIENT_P90_MIN_HISTORY
from app.risk.names import (
    confusable_skeleton,
    detect_legal_form_kind,
    extract_ie_initials,
    normalize_company_name,
    normalize_company_name_translated,
    normalize_company_name_translit,
)
from app.risk.profiles import (
    DEFAULT_CACHE_MAXSIZE,
    ProfileCache,
    build_profiles,
    clear_profiles_cache,
    get_profiles,
    history_cache_key,
    invalidate_profiles,
)
from app.risk.rules import (
    _classify_supplier_distinctive_tokens,
    _compute_percentile,
    compute_client_median,
    compute_client_p90,
    rule_iik_belongs_to_other_counterparty,
)
from app.schemas import CheckRequest
from app.store import Store
from app.validators.kz import bin_kind
from scripts.generate_data import generate_bin, generate_iik, generate_iin

PAYER_ID = "client-synth"


def _build_synthetic_store_and_history() -> tuple[Store, list[dict[str, Any]], dict[str, Any]]:
    """Create an isolated in-memory Store with deterministic multi-supplier synthetic history."""
    rng = random.Random(20260420)
    store = Store()

    bin_a = generate_bin(rng, year=16, month=5, entity_digit=4)
    bin_b = generate_bin(rng, year=18, month=9, entity_digit=4)
    bin_ie = generate_iin(rng, year=85, month=7, day=14)
    bin_d = generate_bin(rng, year=20, month=3, entity_digit=5)
    bin_e = generate_bin(rng, year=19, month=11, entity_digit=4)

    iik_a1 = generate_iik(rng, "601", prefix="000")
    iik_a2 = generate_iik(rng, "722", prefix="000")
    iik_b1 = generate_iik(rng, "965", prefix="000")
    iik_ie = generate_iik(rng, "948", prefix="000")
    iik_shared = generate_iik(rng, "914", prefix="000")
    iik_e1 = generate_iik(rng, "998", prefix="000")

    history: list[dict[str, Any]] = [
        # Supplier A: 7 payments, 2 IIKs, 2 BIKs, 2 KNPs, varied amounts
        {
            "id": "SYN-001",
            "payer_id": PAYER_ID,
            "paid_at": "2025-05-01",
            "recipient_name": "ТОО «Алатау Снаб»",
            "recipient_bin": bin_a,
            "recipient_iik": iik_a1,
            "recipient_bik": "HSBKKZKX",
            "amount_kzt": 1_100_000.0,
            "purpose": "Оплата по счёту № 101",
            "knp": "710",
        },
        {
            "id": "SYN-002",
            "payer_id": PAYER_ID,
            "paid_at": "2025-05-10",
            "recipient_name": "ТОО «НұрМеталл Supply»",
            "recipient_bin": bin_b,
            "recipient_iik": iik_b1,
            "recipient_bik": "IRTYKZKA",
            "amount_kzt": 2_250_000.5,
            "purpose": "Поставка металла по счёту № 201",
            "knp": "710",
        },
        {
            "id": "SYN-003",
            "payer_id": PAYER_ID,
            "paid_at": "2025-05-15",
            "recipient_name": "ТОО «Алатау Снаб»",
            "recipient_bin": bin_a,
            "recipient_iik": iik_a1,
            "recipient_bik": "HSBKKZKX",
            "amount_kzt": 1_350_000.0,
            "purpose": "Оплата по счёту № 102",
            "knp": "710",
        },
        {
            "id": "SYN-004",
            "payer_id": PAYER_ID,
            "paid_at": "2025-06-01",
            "recipient_name": "ИП Байжанов К.Т.",
            "recipient_bin": bin_ie,
            "recipient_iik": iik_ie,
            "recipient_bik": "EURIKZKA",
            "amount_kzt": 195_000.0,
            "purpose": "Услуги обслуживания по акту № 1",
            "knp": "859",
        },
        # Shared IIK used first by Supplier D, then by Supplier E, then again by Supplier D
        {
            "id": "SYN-005",
            "payer_id": PAYER_ID,
            "paid_at": "2025-06-10",
            "recipient_name": "ТОО «КазКранМонтаж Старый»",
            "recipient_bin": bin_d,
            "recipient_iik": iik_shared,
            "recipient_bik": "BRKEKZKA",
            "amount_kzt": 800_000.0,
            "purpose": "Аренда крана",
            "knp": "859",
        },
        {
            "id": "SYN-006",
            "payer_id": PAYER_ID,
            "paid_at": "2025-06-20",
            "recipient_name": "ТОО «СтепьЭнерго»",
            "recipient_bin": bin_e,
            "recipient_iik": iik_shared,
            "recipient_bik": "BRKEKZKA",
            "amount_kzt": 450_000.0,
            "purpose": "Электромонтаж",
            "knp": "",
        },
        {
            "id": "SYN-007",
            "payer_id": PAYER_ID,
            "paid_at": "2025-07-01",
            "recipient_name": "ТОО «Алатау Снаб»",
            "recipient_bin": bin_a,
            "recipient_iik": iik_a2,
            "recipient_bik": "CASPKZKA",
            "amount_kzt": 1_480_000.25,
            "purpose": "Оплата по счёту № 103",
            "knp": "859",
        },
        {
            "id": "SYN-008",
            "payer_id": PAYER_ID,
            "paid_at": "2025-07-12",
            "recipient_name": "ТОО «КазКранМонтаж Новый»",
            "recipient_bin": bin_d,
            "recipient_iik": iik_shared,
            "recipient_bik": "BRKEKZKA",
            "amount_kzt": 950_000.0,
            "purpose": "Аренда крана 2",
            "knp": "859",
        },
        {
            "id": "SYN-009",
            "payer_id": PAYER_ID,
            "paid_at": "2025-08-01",
            "recipient_name": "ТОО «Алатау Снаб»",
            "recipient_bin": bin_a,
            "recipient_iik": iik_a1,
            "recipient_bik": "HSBKKZKX",
            "amount_kzt": 1_220_000.0,
            "purpose": "Оплата по счёту № 104",
            "knp": "710",
        },
        {
            "id": "SYN-010",
            "payer_id": PAYER_ID,
            "paid_at": "2025-08-18",
            "recipient_name": "ТОО «Алатау Снаб»",
            "recipient_bin": bin_a,
            "recipient_iik": iik_a2,
            "recipient_bik": "CASPKZKA",
            "amount_kzt": 1_900_000.0,
            "purpose": "Оплата по счёту № 105",
            "knp": "710",
        },
        {
            "id": "SYN-011",
            "payer_id": PAYER_ID,
            "paid_at": "2025-09-02",
            "recipient_name": "ТОО «Алатау Снаб»",
            "recipient_bin": bin_a,
            "recipient_iik": iik_a1,
            "recipient_bik": "HSBKKZKX",
            "amount_kzt": 1_310_000.75,
            "purpose": "Оплата по счёту № 106",
            "knp": "710",
        },
        {
            "id": "SYN-012",
            "payer_id": PAYER_ID,
            "paid_at": "2025-10-05",
            "recipient_name": "ТОО «Алатау Снаб»",
            "recipient_bin": bin_a,
            "recipient_iik": iik_a2,
            "recipient_bik": "CASPKZKA",
            "amount_kzt": 2_400_000.0,
            "purpose": "Оплата по счёту № 107",
            "knp": "859",
        },
        {
            "id": "SYN-013",
            "payer_id": PAYER_ID,
            "paid_at": "2025-10-20",
            "recipient_name": "ТОО «СтепьЭнерго»",
            "recipient_bin": bin_e,
            "recipient_iik": iik_e1,
            "recipient_bik": "TSESKZKA",
            "amount_kzt": 510_000.0,
            "purpose": "Электромонтаж 2",
            "knp": "710",
        },
    ]

    store.history = list(history)
    store.client = {
        "payer_id": PAYER_ID,
        "name": "ТОО «ТестПлательщик»",
        "bin": generate_bin(rng, year=15, month=1),
        "iik": generate_iik(rng, "856", prefix="KZT"),
        "bik": "KCJBKZKX",
    }
    meta = {
        "bin_a": bin_a,
        "bin_b": bin_b,
        "bin_ie": bin_ie,
        "bin_d": bin_d,
        "bin_e": bin_e,
        "iik_a1": iik_a1,
        "iik_a2": iik_a2,
        "iik_shared": iik_shared,
        "iik_new": generate_iik(rng, "601", prefix="000"),
        "bin_new": generate_bin(rng, year=22, month=8),
    }
    return store, history, meta


def _assert_profiles_match_direct_rules(store: Store, payer_id: str) -> None:
    """Assert every SupplierProfile and ClientProfiles field equals direct rule computations."""
    history = store.get_client_history(payer_id)
    profiles = build_profiles(history, banks_by_bik=store.banks_by_bik)

    assert profiles.history_len == len(history)
    assert profiles.client_p90 == compute_client_p90(store, payer_id)
    assert profiles.client_median == compute_client_median(store, payer_id)

    expected_bins: list[str] = []
    for p in history:
        if p["recipient_bin"] not in expected_bins:
            expected_bins.append(p["recipient_bin"])
    assert list(profiles.suppliers.keys()) == expected_bins

    for sup_bin in expected_bins:
        sup_hist = store.get_supplier_history(sup_bin, payer_id)
        prof = profiles.get_supplier(sup_bin)
        assert prof is not None

        assert prof.recipient_bin == sup_bin
        assert prof.payments_count == len(sup_hist)
        assert prof.first_name == sup_hist[0]["recipient_name"]
        assert prof.last_name == sup_hist[-1]["recipient_name"]
        assert prof.first_paid_at == sup_hist[0]["paid_at"]
        assert prof.last_paid_at == sup_hist[-1]["paid_at"]
        assert prof.last_iik == sup_hist[-1]["recipient_iik"]
        assert prof.last_bik == sup_hist[-1]["recipient_bik"]
        assert prof.last_bank == (
            store.get_bank_name_by_bik(sup_hist[-1]["recipient_bik"])
            or sup_hist[-1]["recipient_bik"]
        )
        assert prof.last_amount_kzt == float(sup_hist[-1]["amount_kzt"])

        assert prof.known_iiks == {p["recipient_iik"] for p in sup_hist}
        assert prof.known_biks == {p["recipient_bik"] for p in sup_hist}
        assert prof.known_banks == {
            store.get_bank_name_by_bik(p["recipient_bik"]) or p["recipient_bik"] for p in sup_hist
        }
        assert prof.known_knps == {
            str(p.get("knp", "")).strip() for p in sup_hist if p.get("knp")
        }

        amounts = [float(p["amount_kzt"]) for p in sup_hist]
        expected_median = float(statistics.median(amounts))
        expected_mad = float(statistics.median([abs(x - expected_median) for x in amounts]))
        expected_p90 = _compute_percentile(sorted(amounts), 0.9)
        assert prof.amount_median == expected_median
        assert prof.amount_mad == expected_mad
        assert prof.amount_p90 == expected_p90

        pos_amounts = [a for a in amounts if a > 0]
        if pos_amounts:
            assert prof.positive_amount_median == float(statistics.median(pos_amounts))
            assert prof.positive_amount_p90 == _compute_percentile(sorted(pos_amounts), 0.9)
        else:
            assert prof.positive_amount_median is None
            assert prof.positive_amount_p90 is None

        first_name = sup_hist[0]["recipient_name"]
        expected_norm = normalize_company_name(first_name)
        expected_cyr, expected_lat = normalize_company_name_translit(first_name)
        expected_trans = normalize_company_name_translated(first_name)
        expected_skel = confusable_skeleton(first_name)
        expected_base = expected_norm.split() or expected_cyr.split()
        expected_dist_cyr, expected_dist_lat = _classify_supplier_distinctive_tokens(expected_base)
        expected_is_ie = (
            detect_legal_form_kind(first_name) == "iin" or bin_kind(sup_bin) == "iin"
        )
        expected_ie_init = extract_ie_initials(first_name) if expected_is_ie else ()

        assert prof.normalized_name == expected_norm
        assert prof.normalized_tokens == tuple(expected_norm.split())
        assert prof.translit_cyr == expected_cyr
        assert prof.translit_lat == expected_lat
        assert prof.translit_cyr_tokens == tuple(expected_cyr.split())
        assert prof.translit_lat_tokens == tuple(expected_lat.split())
        assert prof.translated_name == expected_trans
        assert prof.skeleton_name == expected_skel
        assert prof.skeleton_tokens == tuple(expected_skel.split())
        assert prof.base_cyr_tokens == tuple(expected_base)
        assert prof.distinctive_cyr_tokens == tuple(expected_dist_cyr)
        assert prof.distinctive_lat_tokens == tuple(expected_dist_lat)
        assert prof.is_ie is expected_is_ie
        assert prof.ie_initials == expected_ie_init


class TestProfileEquivalence:
    def test_synthetic_history_exact_equivalence(self) -> None:
        store, history, meta = _build_synthetic_store_and_history()
        _assert_profiles_match_direct_rules(store, PAYER_ID)

        profiles = build_profiles(history, banks_by_bik=store.banks_by_bik)

        # Verify default banks.json resolution matches Store.banks_by_bik identically
        profiles_default_banks = build_profiles(history)
        assert profiles_default_banks == profiles

        # Supplier D changed its name over time: first_name vs last_name are preserved distinctly
        prof_d = profiles.get_supplier(meta["bin_d"])
        assert prof_d is not None
        assert prof_d.first_name == "ТОО «КазКранМонтаж Старый»"
        assert prof_d.last_name == "ТОО «КазКранМонтаж Новый»"

        # IE supplier detects is_ie and initials
        prof_ie = profiles.get_supplier(meta["bin_ie"])
        assert prof_ie is not None
        assert prof_ie.is_ie is True
        assert prof_ie.ie_initials == ("к", "т")

        # Multi-IIK / multi-BIK / multi-KNP supplier A
        prof_a = profiles.get_supplier(meta["bin_a"])
        assert prof_a is not None
        assert prof_a.known_iiks == frozenset({meta["iik_a1"], meta["iik_a2"]})
        assert prof_a.known_biks == frozenset({"HSBKKZKX", "CASPKZKA"})
        assert prof_a.known_banks == frozenset(
            {"АО «Народный Банк Казахстана»", "АО «Kaspi Bank»"}
        )
        assert prof_a.known_knps == frozenset({"710", "859"})

    def test_demo_history_exact_equivalence(self) -> None:
        store = Store()
        _assert_profiles_match_direct_rules(store, store.default_payer_id)

    def test_iik_to_bins_index_matches_rule_iik_belongs_to_other_counterparty(self) -> None:
        store, history, meta = _build_synthetic_store_and_history()
        profiles = build_profiles(history, banks_by_bik=store.banks_by_bik)

        # Shared IIK maps to both bin_d and bin_e
        assert profiles.iik_to_bins[meta["iik_shared"]] == frozenset(
            {meta["bin_d"], meta["bin_e"]}
        )
        assert profiles.iik_to_bins[meta["iik_a1"]] == frozenset({meta["bin_a"]})

        # Exhaustively compare against rule_iik_belongs_to_other_counterparty across combinations
        test_pairs = [
            (meta["bin_a"], meta["iik_a1"], "HSBKKZKX"),  # own exclusive IIK -> None
            (meta["bin_b"], meta["iik_a1"], "HSBKKZKX"),  # other BIN's IIK -> Supplier A
            (meta["bin_new"], meta["iik_a1"], "HSBKKZKX"),  # new BIN using A's IIK -> Supplier A
            (meta["bin_d"], meta["iik_shared"], "BRKEKZKA"),  # shared IIK (D->E->D) for D -> E
            (meta["bin_e"], meta["iik_shared"], "BRKEKZKA"),  # shared IIK (D->E->D) for E -> D (last)
            (meta["bin_new"], meta["iik_shared"], "BRKEKZKA"),  # shared IIK for new BIN -> D (last)
            (meta["bin_new"], meta["iik_new"], "HSBKKZKX"),  # unseen IIK -> None
        ]

        for req_bin, req_iik, req_bik in test_pairs:
            req = CheckRequest(
                payer_id=PAYER_ID,
                recipient_name="ТОО «Проверка»",
                recipient_bin=req_bin,
                recipient_iik=req_iik,
                recipient_bik=req_bik,
                amount_kzt=100_000.0,
                purpose="Оплата",
            )
            direct_sig = rule_iik_belongs_to_other_counterparty(req, store)
            other_bins = profiles.other_bins_for_iik(req_iik, req_bin)
            usage = profiles.find_other_counterparty_for_iik(req_iik, req_bin)

            if direct_sig is None:
                assert other_bins == frozenset()
                assert usage is None
            else:
                assert len(other_bins) >= 1
                assert usage is not None
                assert usage.recipient_bin in other_bins
                assert usage.recipient_bin == direct_sig.evidence.actual_params["bin"]
                assert usage.recipient_name == direct_sig.evidence.actual_params["name"]
                assert usage.paid_at == direct_sig.evidence.since

    def test_non_positive_amount_edge_case_matches_rules(self) -> None:
        store, history, meta = _build_synthetic_store_and_history()
        sup_bin = meta["bin_b"]
        # Inject a 0.0 amount record to verify amount_median vs positive_amount_median
        augmented = list(history) + [
            {
                "id": "SYN-ZERO",
                "payer_id": PAYER_ID,
                "paid_at": "2025-11-01",
                "recipient_name": "ТОО «НұрМеталл Supply»",
                "recipient_bin": sup_bin,
                "recipient_iik": history[1]["recipient_iik"],
                "recipient_bik": history[1]["recipient_bik"],
                "amount_kzt": 0.0,
                "purpose": "Корректировка",
                "knp": "710",
            }
        ]
        store.history = augmented
        _assert_profiles_match_direct_rules(store, PAYER_ID)

        profiles = build_profiles(augmented, banks_by_bik=store.banks_by_bik)
        prof_b = profiles.get_supplier(sup_bin)
        assert prof_b is not None
        assert prof_b.amount_median == statistics.median([2_250_000.5, 0.0])
        assert prof_b.positive_amount_median == 2_250_000.5
        assert prof_b.positive_amount_p90 == 2_250_000.5


class TestProfileCache:
    def setup_method(self) -> None:
        clear_profiles_cache()

    def teardown_method(self) -> None:
        clear_profiles_cache()

    def test_cache_hit_returns_identical_object(self) -> None:
        _, history, _ = _build_synthetic_store_and_history()
        first = get_profiles(PAYER_ID, history)
        second = get_profiles(PAYER_ID, history)
        assert first is second

    def test_cache_invalidates_on_history_length_change(self) -> None:
        _, history, _ = _build_synthetic_store_and_history()
        initial = get_profiles(PAYER_ID, history)

        extended = list(history) + [{**history[-1], "id": "SYN-014", "amount_kzt": 777_000.0}]
        updated = get_profiles(PAYER_ID, extended)
        assert updated is not initial
        assert updated.history_len == len(history) + 1
        assert updated.last_record_id == "SYN-014"

        shortened = history[:-1]
        shrunk = get_profiles(PAYER_ID, shortened)
        assert shrunk is not initial
        assert shrunk.history_len == len(history) - 1

    def test_cache_invalidates_on_last_record_id_change(self) -> None:
        _, history, _ = _build_synthetic_store_and_history()
        initial = get_profiles(PAYER_ID, history)

        same_len_new_id = list(history[:-1]) + [
            {**history[-1], "id": "SYN-013-REV2", "amount_kzt": 999_000.0}
        ]
        assert len(same_len_new_id) == len(history)
        updated = get_profiles(PAYER_ID, same_len_new_id)
        assert updated is not initial
        assert updated.last_record_id == "SYN-013-REV2"
        sup_e = updated.get_supplier(history[-1]["recipient_bin"])
        assert sup_e is not None
        assert sup_e.last_amount_kzt == 999_000.0

    def test_cache_separates_payers_with_identical_len_and_last_id(self) -> None:
        _, history, _ = _build_synthetic_store_and_history()
        p1 = get_profiles("payer-1", history)
        p2 = get_profiles("payer-2", history)
        assert p1 is not p2
        assert p1 == p2
        assert get_profiles("payer-1", history) is p1
        assert get_profiles("payer-2", history) is p2

    def test_invalidate_and_clear_functions(self) -> None:
        _, history, _ = _build_synthetic_store_and_history()
        p1 = get_profiles("payer-1", history)
        p2 = get_profiles("payer-2", history)

        removed = invalidate_profiles("payer-1")
        assert removed == 1
        assert get_profiles("payer-2", history) is p2
        assert get_profiles("payer-1", history) is not p1

        clear_profiles_cache()
        assert get_profiles("payer-2", history) is not p2

    def test_lru_eviction_order(self) -> None:
        cache = ProfileCache(maxsize=2)
        _, history, _ = _build_synthetic_store_and_history()

        a = cache.get("payer-a", history[:1])
        b = cache.get("payer-b", history[:1])
        assert cache.size == 2
        assert cache.misses == 2
        assert cache.hits == 0

        # Touch payer-a so payer-b becomes the least-recently-used entry
        assert cache.get("payer-a", history[:1]) is a
        assert cache.hits == 1

        # Inserting payer-c must evict payer-b, keeping payer-a and payer-c
        c = cache.get("payer-c", history[:1])
        assert cache.size == 2
        assert cache.get("payer-a", history[:1]) is a
        assert cache.get("payer-c", history[:1]) is c

        # payer-b was evicted, so fetching it again builds a new object
        b_rebuilt = cache.get("payer-b", history[:1])
        assert b_rebuilt is not b

    def test_default_cache_respects_max_size(self) -> None:
        first_payer = "evict-0"
        first_obj = get_profiles(first_payer, [])
        for idx in range(1, DEFAULT_CACHE_MAXSIZE + 2):
            get_profiles(f"evict-{idx}", [])
        # evict-0 must have been evicted after exceeding DEFAULT_CACHE_MAXSIZE distinct keys
        rebuilt = get_profiles(first_payer, [])
        assert rebuilt is not first_obj

    def test_invalid_maxsize_raises(self) -> None:
        with pytest.raises(ValueError, match="maxsize"):
            ProfileCache(maxsize=0)


class TestEdgeCases:
    def test_empty_history(self) -> None:
        profiles = build_profiles([])
        assert profiles.history_len == 0
        assert profiles.last_record_id is None
        assert profiles.client_p90 is None
        assert profiles.client_median is None
        assert len(profiles.suppliers) == 0
        assert len(profiles.iik_to_bins) == 0
        assert len(profiles.iik_usages) == 0
        assert profiles.get_supplier("160542439625") is None
        assert profiles.other_bins_for_iik("KZ246010005016525808", "160542439625") == frozenset()
        assert (
            profiles.find_other_counterparty_for_iik("KZ246010005016525808", "160542439625")
            is None
        )
        assert history_cache_key("p1", []) == ("p1", 0, None)

    def test_single_payment_and_new_bin_and_client_p90_threshold(self) -> None:
        _, history, meta = _build_synthetic_store_and_history()
        single = [history[0]]
        profiles = build_profiles(single)

        assert profiles.history_len == 1
        assert profiles.last_record_id == "SYN-001"
        assert profiles.client_p90 is None
        assert profiles.client_median is None
        assert profiles.get_supplier(meta["bin_new"]) is None

        prof = profiles.get_supplier(history[0]["recipient_bin"])
        assert prof is not None
        assert prof.payments_count == 1
        assert prof.amount_median == 1_100_000.0
        assert prof.amount_mad == 0.0
        assert prof.amount_p90 == 1_100_000.0
        assert prof.positive_amount_median == 1_100_000.0
        assert prof.positive_amount_p90 == 1_100_000.0
        assert prof.known_iiks == frozenset({history[0]["recipient_iik"]})
        assert prof.known_biks == frozenset({"HSBKKZKX"})
        assert prof.known_banks == frozenset({"АО «Народный Банк Казахстана»"})
        assert prof.known_knps == frozenset({"710"})
        assert prof.last_paid_at == "2025-05-01"

        # Just below CLIENT_P90_MIN_HISTORY -> None; at CLIENT_P90_MIN_HISTORY -> computed
        below = build_profiles(history[: CLIENT_P90_MIN_HISTORY - 1])
        assert below.client_p90 is None
        assert below.client_median is None

        at_min = build_profiles(history[:CLIENT_P90_MIN_HISTORY])
        assert at_min.client_p90 is not None
        assert at_min.client_median is not None

    def test_unknown_bik_falls_back_to_bik_and_profiles_are_immutable(self) -> None:
        _, history, _ = _build_synthetic_store_and_history()
        rec = {**history[0], "recipient_bik": "ZZZZKZKA", "knp": None}
        profiles = build_profiles([rec])
        prof = profiles.get_supplier(rec["recipient_bin"])
        assert prof is not None
        assert prof.known_banks == frozenset({"ZZZZKZKA"})
        assert prof.last_bank == "ZZZZKZKA"
        assert prof.known_knps == frozenset()

        with pytest.raises(FrozenInstanceError):
            profiles.client_p90 = 1.0  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            prof.amount_median = 1.0  # type: ignore[misc]
        with pytest.raises(TypeError):
            profiles.suppliers["x"] = prof  # type: ignore[index]
        with pytest.raises(TypeError):
            profiles.iik_to_bins["x"] = frozenset()  # type: ignore[index]
