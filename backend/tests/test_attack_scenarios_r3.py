"""Round-3 attack and edge scenarios for the risk engine in demo mode.

Everything goes through the public surface: `POST /api/payments/check` (dry-run unless
`commit=true`) and, where a synthetic store has to be tweaked, `check_payment` itself.

Convention:
- an attack must end as yellow / red / invalid (never green);
- a legitimate payment must never end as red;
- a confirmed hole is marked `xfail(strict=True)` with the reason starting with "gap:".
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.risk.bank_signals import load_bank_signals
from app.risk.config import DEMO_TODAY
from app.risk.engine import check_payment
from app.risk.rules import compute_client_p90
from app.schemas import CheckRequest
from app.store import Store, store
from app.validators.kz import make_bin_iin, make_iik

PAYER = "client-technostroy"

# Known supplier from the synthetic history (stable fixture of the demo data set).
SUPPLIER_NAME = "ТОО «Алатау Снаб»"
SUPPLIER_BIN = "160542439625"
SUPPLIER_IIK = "KZ246010005016525808"
SUPPLIER_BIK = "HSBKKZKX"
SUPPLIER_AMOUNT = 1_360_000
SUPPLIER_PURPOSE = "Оплата по счёту № 214 за строительные материалы по договору № 14-А"

BASE: dict[str, Any] = {
    "payer_id": PAYER,
    "recipient_name": SUPPLIER_NAME,
    "recipient_bin": SUPPLIER_BIN,
    "recipient_iik": SUPPLIER_IIK,
    "recipient_bik": SUPPLIER_BIK,
    "amount_kzt": SUPPLIER_AMOUNT,
    "purpose": SUPPLIER_PURPOSE,
}

# A brand-new counterparty with a well-formed legal-entity BIN and a Caspi-bank account.
NEW_BIN = make_bin_iin("19064123456")
NEW_IIK = make_iik("722", "0001234567890")
NEW_SUPPLIER: dict[str, Any] = {
    "recipient_name": "ТОО «Новая Компания»",
    "recipient_bin": NEW_BIN,
    "recipient_iik": NEW_IIK,
    "recipient_bik": "CASPKZKA",
    "amount_kzt": 50_000,
}

# A different account for the known supplier at the same bank / at another bank.
SAME_BANK_NEW_IIK = make_iik("601", "0005016525809")
OTHER_BANK_NEW_IIK = make_iik("722", "0001234567890")

VERDICTS_NEED_REVIEW = {"yellow", "red"}


@pytest.fixture(autouse=True)
def _reset_store() -> Generator[None]:
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _check(
    client: TestClient,
    *,
    commit: bool = False,
    lang: str = "ru",
    expected_status: int = 200,
    **overrides: Any,
) -> dict[str, Any]:
    payload = {**BASE, **overrides}
    params: dict[str, str] = {"lang": lang}
    if commit:
        params["commit"] = "true"
    resp = client.post("/api/payments/check", json=payload, params=params)
    assert resp.status_code == expected_status, resp.text
    return resp.json()


def _new(client: TestClient, **overrides: Any) -> dict[str, Any]:
    return _check(client, **{**NEW_SUPPLIER, **overrides})


def _ids(result: dict[str, Any]) -> list[str]:
    return [s["rule_id"] for s in result["signals"]]


def _bik_for_iik(iik: str) -> str:
    bank = store.banks_by_code.get(iik[4:7])
    if bank is None:
        pytest.skip(f"bank code {iik[4:7]} is absent from the demo directory")
    return bank["bik"]


# ---------------------------------------------------------------------------
# 1. Names: homoglyphs, invisible characters, quotes, legal forms
# ---------------------------------------------------------------------------

# (label, name) — a name written with a foreign-script letter inside a Cyrillic word.
HOMOGLYPH_NAMES = [
    ("latin_a", "ТОО «Аlaтау Снаб»".replace("l", "a")),
    ("latin_c", "ТОО «Алатау Cнаб»"),
    ("latin_o_in_too", "ТOО «Алатау Снаб»"),
    ("latin_t_in_too", "TОО «Алатау Снаб»"),
    ("greek_omicron", "ТОО «Алатау Снаб»".replace("О", "Ο")),
    ("greek_alpha", "ТОО «Алатау Снаб»".replace("а", "α", 1)),
    ("fullwidth_c", "ТОО «Алатау Снаб»".replace("С", "Ｃ")),
    ("digit_zero_for_o", "Т0О «Алатау Снаб»"),
    ("digit_three_for_z", "ТОО «Ал3тау Снаб»"),
]

# Cosmetic variants of the very same name: no risk by themselves.
HARMLESS_NAME_VARIANTS = [
    ("extra_spaces", "ТОО   «Алатау    Снаб»"),
    ("straight_quotes", 'ТОО "Алатау Снаб"'),
    ("without_legal_form", "Алатау Снаб"),
    ("lowercase", "тоо «алатау снаб»"),
    ("uppercase", "ТОО «АЛАТАУ СНАБ»"),
    ("zero_width_space", "ТОО «Ала\u200bтау Снаб»"),
    ("soft_hyphen", "ТОО «Ала­тау Снаб»"),
    ("nbsp", "ТОО «Алатау Снаб»"),
    ("latin_legal_form_too", "TOO «Алатау Снаб»"),
    ("kazakh_letters_inside", "ТОО «Алатау Снәб»"),
]


class TestNameHomoglyphs:
    @pytest.mark.parametrize("label,name", HOMOGLYPH_NAMES, ids=[h[0] for h in HOMOGLYPH_NAMES])
    def test_homoglyph_name_on_known_pair_is_flagged(
        self, client: TestClient, label: str, name: str
    ) -> None:
        result = _check(client, recipient_name=name)
        assert result["verdict"] in VERDICTS_NEED_REVIEW, label
        assert "mixed_script_name" in _ids(result)
        diff = next(d for d in result["comparison"] if d["field"] == "name")
        assert diff["differs"] is True
        assert diff["diff_positions"], "the suspicious characters must be pointed out"
        assert result["next_action"]["primary"] == "send_to_director"

    @pytest.mark.parametrize(
        "label,name", HARMLESS_NAME_VARIANTS, ids=[h[0] for h in HARMLESS_NAME_VARIANTS]
    )
    def test_harmless_name_variants_are_not_red(
        self, client: TestClient, label: str, name: str
    ) -> None:
        result = _check(client, recipient_name=name)
        assert result["verdict"] != "red", label
        assert "mixed_script_name" not in _ids(result), label

    @pytest.mark.parametrize("label,name", HOMOGLYPH_NAMES, ids=[h[0] for h in HOMOGLYPH_NAMES])
    def test_double_with_homoglyph_name_and_new_bin_is_never_green(
        self, client: TestClient, label: str, name: str
    ) -> None:
        result = _new(client, recipient_name=name, amount_kzt=SUPPLIER_AMOUNT)
        assert result["verdict"] in VERDICTS_NEED_REVIEW, label
        assert "lookalike_supplier" in _ids(result)

    @pytest.mark.parametrize(
        "name",
        [
            "ТОО «Алатау Снаб»",
            "ТОО «АЛАТАУ СНАБ»",
            "TOO «Alatau Snab»",
            "Alatau Snab LLP",
            "ТОО «Алатау-Снаб»",
            "ТОО «АлатауСнаб»",
            "ТОО «Алатау Сн аб»",
            "ТОО «Снаб Алатау»",
            "ТОО «Алатау Снәб»",
            "ТОО «Алатау Снаб Групп»",
            "ТОО «Алатау Снабжение»",
            "ТОО «Алатау»",
            "ИП Алатау Снаб",
            "АО «Алатау Снаб»",
        ],
    )
    def test_double_of_regular_supplier_with_other_bin_is_flagged(
        self, client: TestClient, name: str
    ) -> None:
        result = _new(client, recipient_name=name, amount_kzt=SUPPLIER_AMOUNT)
        assert result["verdict"] in VERDICTS_NEED_REVIEW, name
        assert "lookalike_supplier" in _ids(result)

    def test_exact_name_with_foreign_bin_is_a_blocking_red(self, client: TestClient) -> None:
        result = _new(client, recipient_name=SUPPLIER_NAME, amount_kzt=SUPPLIER_AMOUNT)
        assert result["verdict"] == "red"
        assert result["score"] == 100
        assert result["next_action"]["primary"] == "postpone"
        sig = next(s for s in result["signals"] if s["rule_id"] == "lookalike_supplier")
        assert sig["severity"] == "block"

    def test_unrelated_new_company_is_only_grey(self, client: TestClient) -> None:
        result = _new(client)
        assert result["verdict"] == "grey"
        assert _ids(result) == ["first_payment"]

    @pytest.mark.parametrize(
        "name",
        [
            "ТОО «ҚазТехСервис»",
            "ТОО «Қарағанды Құрылыс»",
            "ТОО «Kaspi Сервис»",
            "ТОО «Алматы-2»",
            "ТОО «Строй 2020»",
            "ТОО «1С Франчайзинг»",
            'ТОО "Mega Group"',
            "АО «Қазақтелеком»",
            "КХ «Береке»",
            "ТОО «ЭкоSTAR»",
            "ТОО «Көк Бұлақ»",
        ],
    )
    def test_legitimate_new_company_names_are_not_false_positives(
        self, client: TestClient, name: str
    ) -> None:
        result = _new(client, recipient_name=name)
        assert result["verdict"] == "grey", name
        assert "mixed_script_name" not in _ids(result)
        assert "lookalike_supplier" not in _ids(result)

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param(
                "ТОО «ТазаСу»",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason="gap: double of 'ТазаСу Сервис' without the generic word 'Сервис' "
                    "and with a different BIN stays grey (primary action: sign)",
                ),
                id="drop_generic_word",
            ),
            pytest.param(
                "ТОО «АстанаБетон»",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason="gap: double 'АстанаБетон' (truncated 'АстанаБетонСервис') with a "
                    "different BIN stays grey (primary action: sign)",
                ),
                id="truncated_token",
            ),
            pytest.param(
                "ТОО «КазТепло»",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason="gap: double 'КазТепло' (truncated 'КазТеплоИзоляция') with a "
                    "different BIN stays grey (primary action: sign)",
                ),
                id="truncated_second_supplier",
            ),
        ],
    )
    def test_truncated_double_of_regular_supplier(self, client: TestClient, name: str) -> None:
        result = _new(client, recipient_name=name, amount_kzt=740_000)
        assert result["verdict"] in VERDICTS_NEED_REVIEW


# ---------------------------------------------------------------------------
# 2. Requisites: format, checksum, entity type, missing fields
# ---------------------------------------------------------------------------


class TestRequisiteTampering:
    @pytest.mark.parametrize(
        "field,value",
        [
            ("recipient_bin", "160542439626"),  # last digit changed
            ("recipient_bin", "16О542439625"),  # Cyrillic О instead of zero
            ("recipient_bin", "１６０５４２４３９６２５"),  # fullwidth digits
            ("recipient_bin", "160542-439625"),
            ("recipient_bin", "16054243962"),  # 11 digits
            ("recipient_bin", "0160542439625"),  # 13 digits
            ("recipient_bin", "000000000000"),
            ("recipient_bin", make_bin_iin("19134123456")),  # month 13
            ("recipient_iik", "KZ256010005016525808"),  # wrong mod-97
            ("recipient_iik", "КZ246010005016525808"),  # Cyrillic К
            ("recipient_iik", "КЗ246010005016525808"),
            ("recipient_iik", "KZ24601OOO5016525808"),  # letter O for zero
            ("recipient_iik", "KZ24-6010-0050-1652-5808"),
            ("recipient_iik", "246010005016525808"),  # no country prefix
            ("recipient_iik", "KZ2460100050165258080"),  # 21 chars
            ("recipient_iik", "KZ24601000501652580"),  # 19 chars
            ("recipient_bik", "НSBKKZKX"),  # Cyrillic Н
            ("recipient_bik", "HSBKKZK"),
            ("recipient_bik", "ZZZZKZKX"),  # unknown bank
        ],
    )
    def test_tampered_requisite_is_invalid_and_postponed(
        self, client: TestClient, field: str, value: str
    ) -> None:
        result = _check(client, **{field: value})
        assert result["verdict"] == "invalid", (field, value)
        assert result["next_action"]["primary"] == "postpone"
        assert result["score"] == 0
        assert any(s["severity"] == "block" for s in result["signals"])

    @pytest.mark.parametrize("field", ["recipient_bin", "recipient_iik", "recipient_bik"])
    def test_empty_requisite_is_invalid(self, client: TestClient, field: str) -> None:
        result = _check(client, **{field: ""})
        assert result["verdict"] == "invalid"

    @pytest.mark.parametrize("field", ["recipient_name", "recipient_bin", "recipient_iik"])
    def test_requisite_missing_from_payload_is_rejected(
        self, client: TestClient, field: str
    ) -> None:
        payload = {**BASE}
        payload.pop(field)
        resp = client.post("/api/payments/check", json=payload)
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "field,value",
        [
            ("recipient_iik", "kz246010005016525808"),  # lowercase
            ("recipient_iik", "KZ24 6010 0050 1652 5808"),  # spaces
            ("recipient_bik", "hsbkkzkx"),
            ("recipient_bik", "HSBK KZKX"),
            ("recipient_bin", "1605 4243 9625"),
        ],
    )
    def test_formatting_noise_in_requisites_is_normalised_not_penalised(
        self, client: TestClient, field: str, value: str
    ) -> None:
        result = _check(client, **{field: value})
        assert result["verdict"] == "green"

    def test_bik_of_another_bank_is_caught_by_bank_code_check(self, client: TestClient) -> None:
        result = _check(client, recipient_bik="KCJBKZKX")
        assert result["verdict"] == "invalid"
        assert "iik_bank_code_vs_bik" in _ids(result)

    def test_new_iik_with_old_bik_is_invalid_not_a_mere_change(self, client: TestClient) -> None:
        result = _check(client, recipient_iik=OTHER_BANK_NEW_IIK)
        assert result["verdict"] == "invalid"
        assert "iik_bank_code_vs_bik" in _ids(result)

    def test_valid_checksum_individual_iin_under_legal_form_is_yellow(
        self, client: TestClient
    ) -> None:
        iin = make_bin_iin("90010150001")
        result = _new(client, recipient_bin=iin)
        assert result["verdict"] == "yellow"
        assert "entity_type_mismatch" in _ids(result)
        assert result["next_action"]["primary"] == "send_to_director"

    def test_legal_entity_bin_under_individual_entrepreneur_name_is_not_red(
        self, client: TestClient
    ) -> None:
        result = _new(client, recipient_name="ИП Иванов")
        assert result["verdict"] in {"grey", "yellow"}
        assert "entity_type_mismatch" in _ids(result)

    def test_known_ie_with_company_form_in_name_is_yellow(self, client: TestClient) -> None:
        result = _check(
            client,
            recipient_name="ТОО «Байжанов»",
            recipient_bin="840715543940",
            recipient_iik="KZ927220007997531813",
            recipient_bik="CASPKZKA",
            amount_kzt=190_000,
        )
        assert result["verdict"] == "yellow"
        assert "entity_type_mismatch" in _ids(result)

    def test_known_ie_paid_as_legal_entity_kbe_is_yellow(self, client: TestClient) -> None:
        result = _check(
            client,
            recipient_name="ИП Байжанов К.Т.",
            recipient_bin="840715543940",
            recipient_iik="KZ927220007997531813",
            recipient_bik="CASPKZKA",
            amount_kzt=190_000,
            kbe="17",
        )
        assert result["verdict"] == "yellow"
        assert "kbe_mismatch" in _ids(result)

    def test_known_ie_regular_payment_stays_green(self, client: TestClient) -> None:
        result = _check(
            client,
            recipient_name="ИП Байжанов К.Т.",
            recipient_bin="840715543940",
            recipient_iik="KZ927220007997531813",
            recipient_bik="CASPKZKA",
            amount_kzt=190_000,
        )
        assert result["verdict"] == "green"

    def test_kbe_mismatch_alone_does_not_raise_colour_but_is_reported(
        self, client: TestClient
    ) -> None:
        result = _check(client, kbe="19")
        assert result["verdict"] == "green"
        assert _ids(result) == ["kbe_mismatch"]
        assert result["score"] == 25

    def test_kbe_mismatch_amplifies_account_change_to_yellow_or_more(
        self, client: TestClient
    ) -> None:
        result = _check(client, kbe="19", recipient_iik=SAME_BANK_NEW_IIK)
        assert result["verdict"] in VERDICTS_NEED_REVIEW
        assert {"iik_changed", "kbe_mismatch"} <= set(_ids(result))

    @pytest.mark.parametrize("knp", ["859", "999", "abc"])
    def test_unusual_knp_alone_is_an_amplifier_below_yellow(
        self, client: TestClient, knp: str
    ) -> None:
        result = _check(client, knp=knp)
        assert result["verdict"] == "green"
        assert "knp_unusual" in _ids(result)

    def test_young_future_dated_bin_with_urgency_and_big_amount_is_yellow_or_more(
        self, client: TestClient
    ) -> None:
        p90 = compute_client_p90(store, PAYER)
        young_bin = make_bin_iin("26034123456")
        result = _new(
            client,
            recipient_bin=young_bin,
            amount_kzt=p90 * 3.5,
            purpose="срочно",
        )
        assert result["verdict"] in VERDICTS_NEED_REVIEW
        assert {"bin_young", "amount_anomaly", "urgent_wording"} <= set(_ids(result))

    @pytest.mark.xfail(
        strict=True,
        reason="gap: BIN whose registration date lies in the future (2030) is only a +15 "
        "'young BIN' amplifier; the first payment stays grey with primary action 'sign'",
    )
    def test_bin_registered_in_the_future_is_not_a_plain_grey(self, client: TestClient) -> None:
        result = _new(client, recipient_bin=make_bin_iin("30034123456"), amount_kzt=1_000)
        assert result["verdict"] in {"yellow", "red", "invalid"}


# ---------------------------------------------------------------------------
# 3. Substituted accounts: IIK / BIK changes and BCC ownership
# ---------------------------------------------------------------------------


class TestAccountSubstitution:
    def test_new_iik_at_same_bank_is_yellow_with_diff_positions(self, client: TestClient) -> None:
        result = _check(client, recipient_iik=SAME_BANK_NEW_IIK)
        assert result["verdict"] == "yellow"
        assert _ids(result) == ["iik_changed"]
        diff = next(d for d in result["comparison"] if d["field"] == "iik")
        assert diff["differs"] is True and diff["diff_positions"]
        assert result["next_action"]["primary"] == "send_to_director"

    def test_new_iik_at_another_bank_with_matching_bik_is_red(self, client: TestClient) -> None:
        result = _check(client, recipient_iik=OTHER_BANK_NEW_IIK, recipient_bik="CASPKZKA")
        assert result["verdict"] == "red"
        assert {"iik_changed", "bank_changed"} <= set(_ids(result))
        assert result["next_action"]["primary"] == "postpone"

    def test_new_iik_at_another_bank_with_small_amount_is_still_yellow(
        self, client: TestClient
    ) -> None:
        result = _check(
            client,
            recipient_iik=OTHER_BANK_NEW_IIK,
            recipient_bik="CASPKZKA",
            amount_kzt=100_000,
        )
        assert result["verdict"] == "yellow"

    @pytest.mark.parametrize(
        "purpose",
        [
            "срочно",
            "СРОЧНО!!!",
            "Шұғыл төлем",
            "ЖЕДЕЛ",
            "urgent",
            "новые реквизиты",
            "новые  реквизиты",
        ],
    )
    def test_urgency_on_top_of_account_change_never_lowers_the_verdict(
        self, client: TestClient, purpose: str
    ) -> None:
        result = _check(client, recipient_iik=SAME_BANK_NEW_IIK, purpose=purpose)
        assert result["verdict"] in VERDICTS_NEED_REVIEW
        assert {"iik_changed", "urgent_wording"} <= set(_ids(result))
        assert result["score"] >= 45

    def test_account_change_plus_homoglyph_name_is_red(self, client: TestClient) -> None:
        result = _check(client, recipient_iik=SAME_BANK_NEW_IIK, recipient_name="ТОО «Алатау Cнаб»")
        assert result["verdict"] == "red"
        assert {"iik_changed", "mixed_script_name"} <= set(_ids(result))

    def test_account_change_plus_five_times_amount_is_red(self, client: TestClient) -> None:
        result = _check(client, recipient_iik=SAME_BANK_NEW_IIK, amount_kzt=SUPPLIER_AMOUNT * 5)
        assert result["verdict"] == "red"

    def test_account_change_plus_duplicate_invoice_is_red(self, client: TestClient) -> None:
        result = _check(client, recipient_iik=SAME_BANK_NEW_IIK, purpose="по счёту № 113")
        assert result["verdict"] == "red"
        assert {"iik_changed", "duplicate_invoice"} <= set(_ids(result))

    def test_same_account_with_unchanged_bank_has_no_account_signals(
        self, client: TestClient
    ) -> None:
        result = _check(client)
        assert result["verdict"] == "green"
        assert result["signals"] == []

    # -- BCC accounts -------------------------------------------------------

    def test_bcc_account_of_another_company_is_a_blocking_red(self, client: TestClient) -> None:
        result = _check(client, recipient_iik="KZ51856KZT2486117574", recipient_bik="KCJBKZKX")
        assert result["verdict"] == "red"
        assert result["score"] == 100
        sig = next(s for s in result["signals"] if s["rule_id"] == "bcc_account_other_owner")
        assert sig["severity"] == "block"

    @pytest.mark.parametrize(
        "iik",
        [
            "KZ12856KZT1721175500",  # the payer's own account
            "KZ55856KZT5935868570",  # another supplier's account
            "KZ75856KZT9103291175",  # another supplier's account
        ],
    )
    def test_known_supplier_pointed_to_foreign_bcc_account_is_red(
        self, client: TestClient, iik: str
    ) -> None:
        result = _check(client, recipient_iik=iik, recipient_bik="KCJBKZKX", amount_kzt=1_000)
        assert result["verdict"] == "red"
        assert "bcc_account_other_owner" in _ids(result)

    def test_bcc_account_missing_from_registry_is_invalid(self, client: TestClient) -> None:
        iik = make_iik("856", "9999999999999")
        result = _check(client, recipient_iik=iik, recipient_bik="KCJBKZKX")
        assert result["verdict"] == "invalid"
        assert "bcc_account_not_found" in _ids(result)

    def test_swapped_bin_with_the_suppliers_real_account_and_name_is_red(
        self, client: TestClient
    ) -> None:
        result = _check(client, recipient_bin=NEW_BIN)
        assert result["verdict"] == "red"
        assert {"lookalike_supplier", "iik_belongs_to_other_counterparty"} <= set(_ids(result))

    def test_swapped_bin_with_the_suppliers_real_account_and_other_name_is_yellow(
        self, client: TestClient
    ) -> None:
        result = _check(client, recipient_bin=NEW_BIN, recipient_name="ТОО «Другая Фирма»")
        assert result["verdict"] in VERDICTS_NEED_REVIEW
        assert "iik_belongs_to_other_counterparty" in _ids(result)

    def test_swapped_bin_with_new_account_and_same_name_is_red(self, client: TestClient) -> None:
        result = _check(client, recipient_bin=NEW_BIN, recipient_iik=SAME_BANK_NEW_IIK)
        assert result["verdict"] == "red"

    def test_bcc_account_of_the_same_owner_is_a_verified_green(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        iik = make_iik("856", "1111111111111")
        monkeypatch.setitem(
            store.bcc_accounts,
            iik,
            {"owner_bin": SUPPLIER_BIN, "owner_name": SUPPLIER_NAME, "opened_at": "2020-01-01"},
        )
        result = _check(client, recipient_iik=iik, recipient_bik="KCJBKZKX")
        assert result["verdict"] != "red"
        assert "bcc_owner_verified" in _ids(result)
        assert "bcc_account_other_owner" not in _ids(result)

    def test_fresh_bcc_account_of_the_same_owner_is_never_red(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        iik = make_iik("856", "1111111111111")
        monkeypatch.setitem(
            store.bcc_accounts,
            iik,
            {
                "owner_bin": SUPPLIER_BIN,
                "owner_name": SUPPLIER_NAME,
                "opened_at": (DEMO_TODAY - timedelta(days=2)).isoformat(),
            },
        )
        result = _check(client, recipient_iik=iik, recipient_bik="KCJBKZKX")
        assert result["verdict"] != "red"
        assert "new_bcc_account" in _ids(result)

    @pytest.mark.parametrize("owner_bin", ["170446108884", "999", "000000000000"])
    def test_bcc_account_owned_by_someone_else_is_red_whatever_the_owner_record(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, owner_bin: str
    ) -> None:
        iik = make_iik("856", "1111111111111")
        monkeypatch.setitem(
            store.bcc_accounts,
            iik,
            {"owner_bin": owner_bin, "owner_name": "ТОО «Чужой»", "opened_at": "2020-01-01"},
        )
        result = _check(client, recipient_iik=iik, recipient_bik="KCJBKZKX")
        assert result["verdict"] == "red"
        assert "bcc_account_other_owner" in _ids(result)

    def test_future_dated_bcc_account_does_not_look_verified_and_old(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        iik = make_iik("856", "1111111111111")
        monkeypatch.setitem(
            store.bcc_accounts,
            iik,
            {"owner_bin": SUPPLIER_BIN, "owner_name": SUPPLIER_NAME, "opened_at": "2030-01-01"},
        )
        result = _check(client, recipient_iik=iik, recipient_bik="KCJBKZKX")
        assert "new_bcc_account" in _ids(result)

    def test_returning_to_an_older_known_account_is_not_a_change(self) -> None:
        local = Store()
        local.history.insert(
            0,
            {
                "id": "OLD-1",
                "payer_id": PAYER,
                "paid_at": "2025-01-01",
                "recipient_name": SUPPLIER_NAME,
                "recipient_bin": SUPPLIER_BIN,
                "recipient_iik": SAME_BANK_NEW_IIK,
                "recipient_bik": SUPPLIER_BIK,
                "amount_kzt": SUPPLIER_AMOUNT,
                "purpose": "Оплата по счёту № 5",
                "knp": "710",
            },
        )
        local.invalidate_profiles_cache()
        req = CheckRequest(**{**BASE, "recipient_iik": SAME_BANK_NEW_IIK})
        result = check_payment(req, local)
        assert "iik_changed" not in [s.rule_id for s in result.signals]


# ---------------------------------------------------------------------------
# 4. Bank-wide signals (synthetic complaints, watchlist, fresh inflows)
# ---------------------------------------------------------------------------

_SIGNALS = load_bank_signals(store.data_dir)
_WATCHLIST = sorted(_SIGNALS["mule_watchlist"])
_COMPLAINTS_BLOCK = sorted(
    iik for iik, rec in _SIGNALS["complaints"].items() if int(rec["count"]) >= 3
)
_COMPLAINTS_ANY = sorted(_SIGNALS["complaints"])
_FRESH_MEDIUM = sorted(
    iik for iik, rec in _SIGNALS["fresh_inflows"].items() if int(rec["distinct_payers_7d"]) >= 3
)
_KNOWN_BANK_IIKS = {
    iik for rec in _SIGNALS["bank_known_bin"].values() for iik in rec.get("known_iiks", [])
}


class TestBankwideSignals:
    @pytest.mark.parametrize("iik", _WATCHLIST)
    def test_watchlist_account_is_red_for_new_and_known_supplier(
        self, client: TestClient, iik: str
    ) -> None:
        bik = _bik_for_iik(iik)
        new = _new(client, recipient_iik=iik, recipient_bik=bik)
        known = _check(client, recipient_iik=iik, recipient_bik=bik)
        for result in (new, known):
            assert result["verdict"] == "red"
            assert "iik_on_watchlist" in _ids(result)
            assert result["next_action"]["primary"] == "postpone"

    @pytest.mark.parametrize("iik", _COMPLAINTS_BLOCK)
    def test_account_with_many_complaints_is_red(self, client: TestClient, iik: str) -> None:
        result = _new(client, recipient_iik=iik, recipient_bik=_bik_for_iik(iik))
        assert result["verdict"] == "red"
        assert "iik_reported_by_clients" in _ids(result)

    @pytest.mark.parametrize("iik", _COMPLAINTS_ANY)
    def test_any_reported_account_is_at_least_yellow(self, client: TestClient, iik: str) -> None:
        result = _new(client, recipient_iik=iik, recipient_bik=_bik_for_iik(iik))
        assert result["verdict"] in VERDICTS_NEED_REVIEW
        assert "iik_reported_by_clients" in _ids(result)

    @pytest.mark.parametrize("iik", [i for i in _FRESH_MEDIUM if i not in _KNOWN_BANK_IIKS])
    def test_fresh_account_with_many_payers_is_at_least_yellow(
        self, client: TestClient, iik: str
    ) -> None:
        result = _new(client, recipient_iik=iik, recipient_bik=_bik_for_iik(iik))
        assert result["verdict"] in VERDICTS_NEED_REVIEW
        assert "fresh_iik_many_payers" in _ids(result)

    def test_director_trust_never_hides_a_blocking_bank_signal(self, client: TestClient) -> None:
        iik = _WATCHLIST[0]
        bik = _bik_for_iik(iik)
        store.trust_account(SUPPLIER_BIN, iik, payer_id=PAYER)
        result = _check(client, recipient_iik=iik, recipient_bik=bik)
        assert result["verdict"] == "red"
        assert "iik_on_watchlist" in _ids(result)

    def test_director_trust_never_hides_a_foreign_bcc_owner(self, client: TestClient) -> None:
        iik = "KZ51856KZT2486117574"
        store.trust_account(SUPPLIER_BIN, iik, payer_id=PAYER)
        result = _check(client, recipient_iik=iik, recipient_bik="KCJBKZKX")
        assert result["verdict"] == "red"
        assert "bcc_account_other_owner" in _ids(result)


# ---------------------------------------------------------------------------
# 5. Director trust: scope and abuse
# ---------------------------------------------------------------------------


class TestTrustScope:
    def test_trust_turns_exactly_the_trusted_pair_green(self, client: TestClient) -> None:
        assert _check(client, recipient_iik=SAME_BANK_NEW_IIK)["verdict"] == "yellow"
        store.trust_account(SUPPLIER_BIN, SAME_BANK_NEW_IIK, payer_id=PAYER)
        trusted = _check(client, recipient_iik=SAME_BANK_NEW_IIK)
        assert trusted["verdict"] == "green"
        assert trusted["trusted"] is True

    def test_trust_does_not_extend_to_another_account_of_the_same_supplier(
        self, client: TestClient
    ) -> None:
        store.trust_account(SUPPLIER_BIN, SAME_BANK_NEW_IIK, payer_id=PAYER)
        other = make_iik("601", "0005016525810")
        result = _check(client, recipient_iik=other)
        assert result["verdict"] == "yellow"
        assert result["trusted"] is False

    def test_trust_does_not_extend_to_another_bin_with_the_same_account(
        self, client: TestClient
    ) -> None:
        store.trust_account(SUPPLIER_BIN, SAME_BANK_NEW_IIK, payer_id=PAYER)
        result = _check(client, recipient_iik=SAME_BANK_NEW_IIK, recipient_bin=NEW_BIN)
        assert result["verdict"] == "red"
        assert result["trusted"] is False

    @pytest.mark.parametrize(
        "amount,expected",
        [(SUPPLIER_AMOUNT * 10, {"yellow", "red"}), (SUPPLIER_AMOUNT * 100, {"red"})],
    )
    def test_trusted_account_still_gets_amount_checks(
        self, client: TestClient, amount: float, expected: set[str]
    ) -> None:
        store.trust_account(SUPPLIER_BIN, SAME_BANK_NEW_IIK, payer_id=PAYER)
        result = _check(client, recipient_iik=SAME_BANK_NEW_IIK, amount_kzt=amount)
        assert result["verdict"] in expected
        assert "amount_anomaly" in _ids(result)

    def test_trusted_account_still_gets_identity_checks(self, client: TestClient) -> None:
        store.trust_account(SUPPLIER_BIN, SAME_BANK_NEW_IIK, payer_id=PAYER)
        result = _check(
            client, recipient_iik=SAME_BANK_NEW_IIK, recipient_name="ТОО «Другая Фирма»"
        )
        assert result["verdict"] in VERDICTS_NEED_REVIEW
        assert "bin_name_mismatch" in _ids(result)

    def test_trust_of_another_payer_does_not_apply(self, client: TestClient) -> None:
        store.trust_account(SUPPLIER_BIN, SAME_BANK_NEW_IIK, payer_id="client-someone-else")
        result = _check(client, recipient_iik=SAME_BANK_NEW_IIK)
        assert result["verdict"] == "yellow"
        assert result["trusted"] is False


# ---------------------------------------------------------------------------
# 6. Amounts
# ---------------------------------------------------------------------------


class TestAmounts:
    @pytest.mark.parametrize("amount", [0, -1, -5_000_000, "abc", "NaN", "Infinity", 1e12 + 1])
    def test_unacceptable_amount_is_rejected_by_validation(
        self, client: TestClient, amount: Any
    ) -> None:
        resp = client.post("/api/payments/check", json={**BASE, "amount_kzt": amount})
        assert resp.status_code == 422

    @pytest.mark.parametrize("amount", [1e11, 1e12])
    def test_absurdly_large_amount_to_known_supplier_is_red(
        self, client: TestClient, amount: float
    ) -> None:
        result = _check(client, amount_kzt=amount)
        assert result["verdict"] == "red"
        assert result["score"] >= 65
        assert "amount_anomaly" in _ids(result)

    def test_one_tenge_up_or_down_does_not_change_the_verdict(self, client: TestClient) -> None:
        for delta in (-1, 0, 1):
            result = _check(client, amount_kzt=SUPPLIER_AMOUNT + delta)
            assert result["verdict"] == "green"

    @pytest.mark.parametrize("amount", [0.01, 1, 680_000, 1_620_000, 2_000_000])
    def test_ordinary_and_tiny_amounts_to_known_supplier_stay_green(
        self, client: TestClient, amount: float
    ) -> None:
        assert _check(client, amount_kzt=amount)["verdict"] == "green"

    @pytest.mark.parametrize("amount", [2_700_000, 6_800_000, 13_500_000])
    def test_two_to_ten_times_the_usual_amount_is_yellow_or_more(
        self, client: TestClient, amount: float
    ) -> None:
        result = _check(client, amount_kzt=amount)
        assert result["verdict"] in VERDICTS_NEED_REVIEW
        assert "amount_anomaly" in _ids(result)
        diff = next(d for d in result["comparison"] if d["field"] == "amount")
        assert diff["differs"] is True

    def test_first_payment_amount_ladder_against_client_p90(self, client: TestClient) -> None:
        p90 = compute_client_p90(store, PAYER)
        assert p90 and p90 > 0
        small = _new(client, amount_kzt=1_000)
        at_p90 = _new(client, amount_kzt=p90)
        above_yellow = _new(client, amount_kzt=p90 * 3.01)
        above_red = _new(client, amount_kzt=p90 * 10.01)
        assert small["verdict"] == "grey"
        assert at_p90["verdict"] == "grey"
        assert above_yellow["verdict"] == "yellow"
        assert above_red["verdict"] == "red"

    def test_grey_first_payment_above_client_p90_goes_to_director(self, client: TestClient) -> None:
        p90 = compute_client_p90(store, PAYER)
        result = _new(client, amount_kzt=p90 * 1.5)
        assert result["verdict"] == "grey"
        assert result["next_action"]["primary"] == "send_to_director"

    def test_first_payment_with_urgency_and_elevated_amount_becomes_yellow(
        self, client: TestClient
    ) -> None:
        p90 = compute_client_p90(store, PAYER)
        result = _new(client, amount_kzt=p90 * 1.5, purpose="срочно")
        assert result["verdict"] in VERDICTS_NEED_REVIEW


# ---------------------------------------------------------------------------
# 7. Structuring and duplicate invoices
# ---------------------------------------------------------------------------


class TestStructuringAndDuplicates:
    def test_dry_run_checks_are_not_remembered(self, client: TestClient) -> None:
        for i in range(5):
            result = _check(client, amount_kzt=SUPPLIER_AMOUNT + i)
            assert result["verdict"] == "green"
        assert store.recent_checks == []

    def test_committing_the_same_request_twice_is_not_a_split(self, client: TestClient) -> None:
        first = _check(client, commit=True)
        second = _check(client, commit=True)
        assert first["verdict"] == second["verdict"] == "green"
        assert len(store.recent_checks) == 1

    def test_split_payments_to_known_supplier_escalate_with_each_part(
        self, client: TestClient
    ) -> None:
        verdicts = []
        for i, amount in enumerate([1_349_000, 1_348_000, 1_347_000, 1_346_000]):
            result = _check(client, commit=True, amount_kzt=amount, purpose=f"по счёту № {950 + i}")
            verdicts.append((result["verdict"], _ids(result)))
        assert verdicts[0] == ("green", [])
        assert verdicts[1][0] == "green" and "structuring_72h" in verdicts[1][1]
        assert verdicts[2][0] == "yellow" and "structuring_72h" in verdicts[2][1]
        assert verdicts[3][0] == "yellow"

    def test_small_split_to_known_supplier_is_caught_on_the_third_part(
        self, client: TestClient
    ) -> None:
        results = [
            _check(client, commit=True, amount_kzt=700_000 + i, purpose="оплата") for i in range(5)
        ]
        assert results[0]["verdict"] == results[1]["verdict"] == "green"
        assert all(r["verdict"] == "yellow" for r in results[3:])

    def test_split_to_new_supplier_just_under_p90_is_red_by_the_fourth_part(
        self, client: TestClient
    ) -> None:
        results = [
            _new(client, commit=True, amount_kzt=2_800_000 + i, purpose=f"по счёту № {700 + i}")
            for i in range(5)
        ]
        assert results[0]["verdict"] == "grey"
        assert any("new_recipient_accumulated" in _ids(r) for r in results[1:3])
        assert results[3]["verdict"] == "red"
        assert results[4]["verdict"] == "red"

    def test_split_to_new_supplier_without_invoice_numbers_is_red_as_well(
        self, client: TestClient
    ) -> None:
        results = [
            _new(client, commit=True, amount_kzt=2_800_000 + i, purpose="оплата услуг")
            for i in range(4)
        ]
        assert results[3]["verdict"] == "red"
        assert {"new_recipient_accumulated", "structuring_72h"} <= set(_ids(results[3]))

    def test_structuring_window_includes_three_days_but_not_four(self) -> None:
        def verdict_for(days_ago: int) -> list[str]:
            local = Store()
            local.history.append(
                {
                    "id": "BOUND-1",
                    "payer_id": PAYER,
                    "paid_at": (DEMO_TODAY - timedelta(days=days_ago)).isoformat(),
                    "recipient_name": SUPPLIER_NAME,
                    "recipient_bin": SUPPLIER_BIN,
                    "recipient_iik": SUPPLIER_IIK,
                    "recipient_bik": SUPPLIER_BIK,
                    "amount_kzt": 1_350_000,
                    "purpose": "Оплата по счёту № 999",
                    "knp": "710",
                }
            )
            local.invalidate_profiles_cache()
            req = CheckRequest(**{**BASE, "purpose": "по счёту № 1000", "amount_kzt": 1_350_000})
            return [s.rule_id for s in check_payment(req, local).signals]

        for days in (0, 1, 2, 3):
            assert "structuring_72h" in verdict_for(days), days
        assert "structuring_72h" not in verdict_for(4)

    # -- duplicate invoices ---------------------------------------------------

    @pytest.mark.parametrize("delta", [0, 1, -1])
    def test_repeated_history_invoice_is_yellow_even_if_amount_differs_by_a_tenge(
        self, client: TestClient, delta: int
    ) -> None:
        result = _check(
            client,
            amount_kzt=1_350_000 + delta,
            purpose="Оплата по счёту № 113 за строительные материалы по договору № 14-А",
        )
        assert result["verdict"] == "yellow"
        assert _ids(result) == ["duplicate_invoice"]
        assert result["next_action"]["primary"] == "send_to_director"

    @pytest.mark.parametrize(
        "purpose",
        [
            "счет №113",
            "Оплата сч. 113",
            "invoice No 113",
            "Оплата по счету N113",
            "Шот № 113 бойынша төлем",
            "Оплата по счёту №\u200b113",
            "СЧЁТ № 113",
            "Оплата по счёту № １１３",
        ],
    )
    def test_invoice_number_written_differently_is_still_a_duplicate(
        self, client: TestClient, purpose: str
    ) -> None:
        result = _check(client, purpose=purpose)
        assert "duplicate_invoice" in _ids(result), purpose
        assert result["verdict"] == "yellow"

    def test_same_invoice_number_for_another_supplier_is_not_a_duplicate(
        self, client: TestClient
    ) -> None:
        result = _check(
            client,
            recipient_name="ИП Байжанов К.Т.",
            recipient_bin="840715543940",
            recipient_iik="KZ927220007997531813",
            recipient_bik="CASPKZKA",
            amount_kzt=190_000,
            purpose="по счёту № 113",
        )
        assert "duplicate_invoice" not in _ids(result)
        assert result["verdict"] == "green"

    def test_committed_invoice_cannot_be_paid_again_with_a_tenge_more(
        self, client: TestClient
    ) -> None:
        first = _check(client, commit=True, purpose="по счёту № 900")
        assert first["verdict"] == "green"
        second = _check(
            client, commit=True, purpose="по счёту № 900", amount_kzt=SUPPLIER_AMOUNT + 1
        )
        assert second["verdict"] == "yellow"
        assert "duplicate_invoice" in _ids(second)
        probe = _check(client, purpose="по счёту № 900")
        assert "duplicate_invoice" in _ids(probe)

    def test_duplicate_invoice_without_number_is_not_flagged(self, client: TestClient) -> None:
        _check(client, commit=True, purpose="оплата услуг")
        result = _check(client, purpose="оплата услуг", amount_kzt=SUPPLIER_AMOUNT + 1)
        assert "duplicate_invoice" not in _ids(result)


# ---------------------------------------------------------------------------
# 8. Wording of the payment purpose
# ---------------------------------------------------------------------------


class TestUrgentWording:
    @pytest.mark.parametrize(
        "purpose",
        [
            "срочно",
            "СРОЧНО!!!",
            "Срочный платёж",
            "Cрочно",  # Latin C
            "срочнo",  # Latin o
            "с р о ч н о",
            "срo\u200bчно",  # zero-width space
            "srochno oplatit",
            "URGENT payment",
            "urgent!!",
            "NEW  BANK  DETAILS",
            "новые  реквизиты",
            "Шұғыл төлем",
            "ШҰҒЫЛ",
            "ЖЕДЕЛ",
            "сегодня",
            "Срочно оплатить, директор в отпуске",
        ],
    )
    def test_urgent_wording_is_detected_in_many_disguises(
        self, client: TestClient, purpose: str
    ) -> None:
        result = _check(client, purpose=purpose)
        assert "urgent_wording" in _ids(result), purpose
        # An amplifier alone never raises the colour of an otherwise clean payment.
        assert result["verdict"] == "green"

    @pytest.mark.parametrize("purpose", ["несрочно", "досрочно", "Today only", ""])
    def test_innocent_wording_is_not_flagged(self, client: TestClient, purpose: str) -> None:
        result = _check(client, purpose=purpose)
        assert "urgent_wording" not in _ids(result)

    @pytest.mark.parametrize("purpose", ["срочно", "шұғыл", "Срочно, новые реквизиты"])
    def test_urgency_for_a_new_supplier_raises_grey_to_yellow(
        self, client: TestClient, purpose: str
    ) -> None:
        result = _new(client, purpose=purpose)
        assert result["verdict"] == "yellow"
        assert {"urgent_wording", "first_payment"} <= set(_ids(result))

    def test_new_supplier_without_purpose_stays_grey(self, client: TestClient) -> None:
        assert _new(client, purpose="")["verdict"] == "grey"

    @pytest.mark.parametrize(
        "purpose",
        [
            pytest.param(
                "Реквизиты изменились",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason="gap: inverted word order 'Реквизиты изменились' is not recognised "
                    "(only 'изменились реквизиты' is in the phrase list)",
                ),
                id="inverted_order",
            ),
            pytest.param(
                "Изменение реквизитов",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason="gap: 'Изменение реквизитов' is not recognised as requisite-change "
                    "wording",
                ),
                id="noun_form",
            ),
            pytest.param(
                "Жаңа деректемелер бойынша",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason="gap: Kazakh 'жаңа деректемелер' (new requisites) is not recognised",
                ),
                id="kazakh_new_requisites",
            ),
            pytest.param(
                "новый р/с",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason="gap: abbreviation 'новый р/с' (new settlement account) is not "
                    "recognised",
                ),
                id="abbreviation",
            ),
        ],
    )
    def test_requisite_change_wording_variants_are_detected(
        self, client: TestClient, purpose: str
    ) -> None:
        assert "urgent_wording" in _ids(_check(client, purpose=purpose))

    @pytest.mark.parametrize(
        "purpose",
        ["Реквизиты изменились", "Изменение реквизитов", "Жаңа деректемелер бойынша"],
    )
    def test_unrecognised_wording_is_still_covered_by_the_account_change_itself(
        self, client: TestClient, purpose: str
    ) -> None:
        result = _check(client, purpose=purpose, recipient_iik=SAME_BANK_NEW_IIK)
        assert result["verdict"] in VERDICTS_NEED_REVIEW


# ---------------------------------------------------------------------------
# 9. Budget (treasury) payments
# ---------------------------------------------------------------------------

BUDGET_BIN = make_bin_iin("19064123450")


class TestBudgetPayments:
    @pytest.mark.parametrize(
        "bank_code,bik", [("070", "KKMFKZ2A"), ("009", "GCVPKZ2A")], ids=["kkmf", "gcvp"]
    )
    def test_genuine_budget_payment_is_green_and_clean(
        self, client: TestClient, bank_code: str, bik: str
    ) -> None:
        result = _check(
            client,
            recipient_name="КГД МФ РК",
            recipient_bin=BUDGET_BIN,
            recipient_iik=make_iik(bank_code, "0001234567890"),
            recipient_bik=bik,
            amount_kzt=5_000_000,
            purpose="Налоги",
        )
        assert result["verdict"] == "green"
        assert result["signals"] == []
        assert "бюджет" in result["headline"].lower()

    @pytest.mark.parametrize(
        "iik_code,bik",
        [("722", "KKMFKZ2A"), ("070", "CASPKZKA"), ("070", "GCVPKZ2A")],
    )
    def test_budget_bik_with_a_commercial_account_is_invalid(
        self, client: TestClient, iik_code: str, bik: str
    ) -> None:
        result = _check(
            client,
            recipient_name="КГД МФ РК",
            recipient_bin=BUDGET_BIN,
            recipient_iik=make_iik(iik_code, "0001234567890"),
            recipient_bik=bik,
            amount_kzt=5_000_000,
            purpose="Налоги",
        )
        assert result["verdict"] == "invalid"
        assert "iik_bank_code_vs_bik" in _ids(result)

    def test_budget_payment_with_malformed_bin_is_still_invalid(self, client: TestClient) -> None:
        result = _check(
            client,
            recipient_name="КГД МФ РК",
            recipient_bin="123456789012",
            recipient_iik=make_iik("070", "0001234567890"),
            recipient_bik="KKMFKZ2A",
        )
        assert result["verdict"] == "invalid"

    @pytest.mark.xfail(
        strict=True,
        reason="gap: the budget fast-path ignores history; a regular supplier whose account is "
        "swapped for a treasury account (070/KKMFKZ2A) is turned green 'Платёж в бюджет'",
    )
    def test_known_supplier_swapped_to_treasury_account_is_not_green(
        self, client: TestClient
    ) -> None:
        result = _check(
            client,
            recipient_iik=make_iik("070", "0001234567890"),
            recipient_bik="KKMFKZ2A",
        )
        assert result["verdict"] != "green"


# ---------------------------------------------------------------------------
# 10. Hostile input and API behaviour
# ---------------------------------------------------------------------------


class TestHostileInput:
    @pytest.mark.parametrize(
        "name",
        [
            "ТОО <script>alert(1)</script>",
            "ТОО '; DROP TABLE payments;--",
            "ТОО {{7*7}} ${jndi:ldap://x}",
            "\N{RIGHT-TO-LEFT OVERRIDE}ТОО «Алатау Снаб»",  # right-to-left override
            "ТОО «Ала́тау Снаб»",  # combining acute
            "ТОО «Алатау Снаб» \U0001f4a5",
        ],
    )
    def test_hostile_names_never_crash_and_never_turn_a_new_bin_green(
        self, client: TestClient, name: str
    ) -> None:
        result = _new(client, recipient_name=name)
        assert result["verdict"] in {"grey", "yellow", "red"}

    @pytest.mark.parametrize(
        "purpose", ["'; DROP TABLE payments;--", "<img src=x onerror=alert(1)>", "%s%s%s", "\x00"]
    )
    def test_hostile_purpose_never_crashes(self, client: TestClient, purpose: str) -> None:
        resp = client.post("/api/payments/check", json={**BASE, "purpose": purpose})
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "overrides",
        [
            {"recipient_name": "а" * 251},
            {"purpose": "а" * 501},
            {"recipient_name": "   "},
            {"recipient_name": "\u200b\u200b"},
            {"recipient_name": ""},
            {"payer_id": "../../etc/passwd"},
            {"payer_id": "client-xyz"},
            {"recipient_bin": "1" * 65},
            {"kbe": "1" * 11},
        ],
    )
    def test_out_of_contract_payloads_are_rejected(
        self, client: TestClient, overrides: dict[str, Any]
    ) -> None:
        resp = client.post("/api/payments/check", json={**BASE, **overrides})
        assert resp.status_code == 422

    def test_empty_payer_falls_back_to_the_default_client(self, client: TestClient) -> None:
        assert _check(client, payer_id="")["verdict"] == "green"

    @pytest.mark.parametrize("lang", ["ru", "kk", "en"])
    def test_verdict_does_not_depend_on_language(self, client: TestClient, lang: str) -> None:
        result = _check(
            client, lang=lang, recipient_iik=OTHER_BANK_NEW_IIK, recipient_bik="CASPKZKA"
        )
        assert result["verdict"] == "red"
        assert result["signals"] and all(s["reason"] for s in result["signals"])
        assert result["next_action"]["text"]

    def test_same_request_gives_the_same_verdict_and_score(self, client: TestClient) -> None:
        a = _check(client, recipient_iik=SAME_BANK_NEW_IIK, purpose="срочно")
        b = _check(client, recipient_iik=SAME_BANK_NEW_IIK, purpose="срочно")
        assert (a["verdict"], a["score"], _ids(a)) == (b["verdict"], b["score"], _ids(b))

    def test_client_response_hides_analyst_details(self, client: TestClient) -> None:
        result = _check(client, recipient_iik=SAME_BANK_NEW_IIK)
        assert result.get("analyst_details") is None

    def test_every_check_is_audited_without_requisites(self, client: TestClient) -> None:
        result = _check(client, recipient_iik=SAME_BANK_NEW_IIK)
        entries = client.get("/api/audit").json()
        mine = [e for e in entries if e["check_id"] == result["check_id"]]
        assert len(mine) == 1
        assert mine[0]["verdict"] == "yellow"
        assert SAME_BANK_NEW_IIK not in str(mine[0])
        assert SUPPLIER_BIN not in str(mine[0])


# ---------------------------------------------------------------------------
# 11. Legitimate payments are never red
# ---------------------------------------------------------------------------


class TestLegitimatePaymentsStayCalm:
    def test_every_green_queue_item_is_green_or_grey_never_red(self, client: TestClient) -> None:
        for item in store.queue:
            if item["scenario"] not in {"green", "grey"}:
                continue
            payload = {
                k: item[k]
                for k in (
                    "payer_id",
                    "recipient_name",
                    "recipient_bin",
                    "recipient_iik",
                    "recipient_bik",
                    "amount_kzt",
                    "purpose",
                )
            }
            resp = client.post("/api/payments/check", json=payload)
            assert resp.status_code == 200
            assert resp.json()["verdict"] in {"green", "grey"}, item["id"]

    def test_every_history_supplier_repeated_at_its_median_is_green(
        self, client: TestClient
    ) -> None:
        latest: dict[str, dict[str, Any]] = {}
        for p in store.history:
            latest[p["recipient_bin"]] = p
        assert latest
        for bin_, p in latest.items():
            result = _check(
                client,
                recipient_name=p["recipient_name"],
                recipient_bin=bin_,
                recipient_iik=p["recipient_iik"],
                recipient_bik=p["recipient_bik"],
                amount_kzt=p["amount_kzt"],
                purpose="Оплата по счёту № 777000",
            )
            assert result["verdict"] != "red", bin_
            assert "bcc_account_other_owner" not in _ids(result)

    def test_kazakh_purpose_for_known_supplier_is_green(self, client: TestClient) -> None:
        result = _check(client, purpose="Құрылыс материалдарына №214 шот бойынша төлем")
        assert result["verdict"] == "green"
        assert result["signals"] == []

    def test_purpose_with_the_word_today_is_only_an_amplifier(self, client: TestClient) -> None:
        result = _check(client, purpose="Оплата сегодняшнего счёта")
        assert result["verdict"] == "green"


def test_future_dated_check_uses_demo_today_constant() -> None:
    """The structuring and duplicate windows are anchored to DEMO_TODAY, not wall-clock time."""
    assert DEMO_TODAY == date(2026, 4, 20)
