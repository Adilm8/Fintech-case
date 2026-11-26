"""Deterministic synthetic data generator for BCC Business Shield.

Generates all JSON datasets in backend/data/ using SEED = 42 and DEMO_TODAY:
- banks.json
- registry.json
- bcc_accounts.json
- history.json
- queue.json
"""

from __future__ import annotations

import json
import random
import string
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.risk.config import BCC_BANK_CODE, BCC_BIK, DEMO_TODAY
from app.validators.kz import (
    BankRecord,
    bik_matches_iik,
    bin_iin_checksum_ok,
    bin_kind,
    clear_banks_cache,
    compute_bin_iin_check_digit,
    iik_ok,
    make_iik,
)

SEED = 42
DATA_DIR = BACKEND_ROOT / "data"

CLIENT_PAYER_ID = "client-technostroy"
CLIENT_NAME = "ТОО «ТехноСтрой Астана»"

BANKS_NOTE = (
    "Kazakhstan bank codes and BIC, checked against the National Bank of Kazakhstan "
    "BIC reference (nationalbank.kz/ru/page/spravochnik-bik-rk-ps) on 2026-11-26."
)

BANKS_CATALOG: list[BankRecord] = [
    {"code": "601", "bik": "HSBKKZKX", "name": "АО «Народный Банк Казахстана»"},
    {"code": "722", "bik": "CASPKZKA", "name": "АО «Kaspi Bank»"},
    {"code": "965", "bik": "IRTYKZKA", "name": "АО «ForteBank»"},
    {"code": "998", "bik": "TSESKZKA", "name": "АО «Alatau City Bank»"},
    {"code": "856", "bik": "KCJBKZKX", "name": "АО «Банк ЦентрКредит»"},
    {"code": "551", "bik": "KSNVKZKA", "name": "АО «Фридом Банк Казахстан»"},
    {"code": "948", "bik": "EURIKZKA", "name": "АО «Евразийский Банк»"},
    {"code": "821", "bik": "KINCKZKA", "name": "АО «Bank RBK»"},
    {"code": "972", "bik": "HCSKKZKA", "name": "АО «Отбасы банк»"},
    {"code": "886", "bik": "INLMKZKA", "name": "АО «Home Credit Bank»"},
    {"code": "125", "bik": "NBRKKZKX", "name": "РГУ «Национальный Банк Республики Казахстан»"},
    {"code": "949", "bik": "ATYNKZKA", "name": "АО «Altyn Bank»"},
    {"code": "913", "bik": "BKCHKZKA", "name": "АО ДБ «Банк Китая в Казахстане»"},
    {"code": "914", "bik": "BRKEKZKA", "name": "АО «Bereke Bank»"},
    {"code": "832", "bik": "CITIKZKA", "name": "АО «Ситибанк Казахстан»"},
    {"code": "907", "bik": "DVKAKZKA", "name": "АО «Банк Развития Казахстана»"},
    {"code": "246", "bik": "HLALKZKZ", "name": "АО «Исламский Банк ADCB»"},
    {"code": "930", "bik": "ICBKKZKX", "name": "АО «Торгово-промышленный Банк Китая в г. Алматы»"},
    {"code": "719", "bik": "KMFBKZKK", "name": "АО «KMF Банк»"},
    {"code": "563", "bik": "KPSTKZKA", "name": "АО «Казпочта»"},
    {"code": "885", "bik": "KZIBKZKA", "name": "АО ДБ «Казахстан-Зираат Интернешнл Банк»"},
    {"code": "724", "bik": "MOKFKZKA", "name": "АО «Коммерческий Банк БиЭнКей»"},
    {"code": "849", "bik": "NURSKZKX", "name": "АО «Нурбанк»"},
    {"code": "435", "bik": "SHBKKZKA", "name": "АО «Шинхан Банк Казахстан»"},
    {"code": "432", "bik": "VTBAKZKZ", "name": "ДО АО Банк ВТБ (Казахстан)"},
    {"code": "896", "bik": "ZAJSKZ22", "name": "АО «Исламский банк Заман-Банк»"},
]

BIK_BY_CODE: dict[str, str] = {bank["code"]: bank["bik"] for bank in BANKS_CATALOG}


def generate_bin(
    rng: random.Random,
    *,
    year: int | None = None,
    month: int | None = None,
    entity_digit: int = 4,
) -> str:
    """Generate a valid synthetic 12-digit KZ BIN (5th digit in 4, 5, 6)."""
    if entity_digit not in (4, 5, 6):
        raise ValueError(f"BIN entity_digit must be 4, 5, or 6, got {entity_digit}")

    yy = rng.randint(5, 25) if year is None else year % 100
    mm = rng.randint(1, 12) if month is None else month
    if not (1 <= mm <= 12):
        raise ValueError(f"Month must be 1..12, got {mm}")

    while True:
        serial = rng.randint(0, 999999)
        prefix11 = f"{yy:02d}{mm:02d}{entity_digit}{serial:06d}"
        check = compute_bin_iin_check_digit(prefix11)
        if check is not None:
            candidate = f"{prefix11}{check}"
            assert bin_iin_checksum_ok(candidate) and bin_kind(candidate) == "bin"
            return candidate


def generate_iin(
    rng: random.Random,
    *,
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
) -> str:
    """Generate a valid synthetic 12-digit KZ IIN (5th digit in 0..3)."""
    yy = rng.randint(70, 99) if year is None else year % 100
    mm = rng.randint(1, 12) if month is None else month
    dd = rng.randint(1, 28) if day is None else day
    if not (1 <= mm <= 12) or not (1 <= dd <= 31):
        raise ValueError(f"Invalid IIN date: month={mm}, day={dd}")

    while True:
        century_gender = rng.choice((3, 4, 5, 6))
        serial = rng.randint(0, 9999)
        prefix11 = f"{yy:02d}{mm:02d}{dd:02d}{century_gender}{serial:04d}"
        check = compute_bin_iin_check_digit(prefix11)
        if check is not None:
            candidate = f"{prefix11}{check}"
            assert bin_iin_checksum_ok(candidate) and bin_kind(candidate) == "iin"
            return candidate


def generate_iik(
    rng: random.Random,
    bank_code: str,
    *,
    prefix: str = "KZT",
    banks_path: Path | None = None,
) -> str:
    """Generate a valid synthetic 20-char KZ IIK for the given 3-digit bank code."""
    if len(prefix) > 13 or not all(ch in string.ascii_uppercase + string.digits for ch in prefix):
        raise ValueError(f"Invalid IIK body prefix: {prefix!r}")
    digits_needed = 13 - len(prefix)
    tail = "".join(rng.choices(string.digits, k=digits_needed))
    iik = make_iik(bank_code, f"{prefix}{tail}")
    ok, err = iik_ok(iik, check_bank_code=banks_path is not None, banks_path=banks_path)
    assert ok, f"Generated invalid IIK {iik}: {err}"
    return iik


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_banks_json(output_dir: Path = DATA_DIR) -> Path:
    """Write data/banks.json and validate every entry."""
    output_dir.mkdir(parents=True, exist_ok=True)
    seen_codes: set[str] = set()
    seen_biks: set[str] = set()
    for bank in BANKS_CATALOG:
        code = bank["code"]
        bik = bank["bik"]
        assert len(code) == 3 and code.isdigit(), f"Invalid bank code: {code}"
        assert len(bik) == 8 and bik.isascii() and bik.isupper() and bik.isalnum(), (
            f"Invalid BIK: {bik}"
        )
        assert code not in seen_codes, f"Duplicate bank code: {code}"
        assert bik not in seen_biks, f"Duplicate BIK: {bik}"
        seen_codes.add(code)
        seen_biks.add(bik)

    payload = {
        "note": BANKS_NOTE,
        "banks": BANKS_CATALOG,
    }
    banks_path = _write_json(output_dir / "banks.json", payload)
    clear_banks_cache()

    # Sanity-check bank code / BIK consistency against a sample IIK for each bank.
    rng = random.Random(SEED)
    for bank in BANKS_CATALOG:
        sample_iik = generate_iik(rng, bank["code"], banks_path=banks_path)
        assert bik_matches_iik(bank["bik"], sample_iik, path=banks_path)

    return banks_path


def generate_all(output_dir: Path = DATA_DIR) -> dict[str, Path]:
    """Generate all deterministic synthetic JSON files into output_dir."""
    banks_path = write_banks_json(output_dir)
    rng = random.Random(SEED)

    # --- Client company (SME banking with BCC) ---
    client_bin = generate_bin(rng, year=17, month=3)
    client_iik = generate_iik(rng, BCC_BANK_CODE, prefix="KZT")

    # --- 5 regular suppliers in client's 6-month payment history ---
    # Each supplier has >= 5 payments; total = 30 payments.
    suppliers_spec: list[dict[str, Any]] = [
        {
            "key": "alatau",
            "name": "ТОО «Алатау Снаб»",
            "reg_year": 16,
            "reg_month": 5,
            "bank_code": "601",  # Halyk Bank
            "iik_prefix": "000",
            # 7 payments with exact median = 1_350_000 KZT
            "amounts": [
                1_290_000,
                1_320_000,
                1_340_000,
                1_350_000,
                1_370_000,
                1_390_000,
                1_410_000,
            ],
            "days_ago": [172, 145, 118, 92, 66, 38, 11],
            "purpose_tpl": "Оплата по счёту № {inv} за строительные материалы по договору № 14-А",
            "bcc_opened_days_ago": None,
        },
        {
            "key": "kazlogistic",
            "name": "ТОО «КазЛогистик Групп»",
            "reg_year": 18,
            "reg_month": 9,
            "bank_code": "998",  # Alatau City Bank
            "iik_prefix": "000",
            # 6 payments with median = 820_000 KZT
            "amounts": [760_000, 790_000, 810_000, 830_000, 850_000, 875_000],
            "days_ago": [168, 138, 109, 79, 49, 18],
            "purpose_tpl": "Оплата транспортно-экспедиционных услуг по счёту № {inv}",
            "bcc_opened_days_ago": None,
        },
        {
            "key": "stepenergo",
            "name": "ТОО «СтепьЭнергоСервис»",
            "reg_year": 15,
            "reg_month": 11,
            "bank_code": BCC_BANK_CODE,  # BCC
            "iik_prefix": "KZT",
            # 6 payments with median = 540_000 KZT
            "amounts": [510_000, 525_000, 535_000, 545_000, 560_000, 580_000],
            "days_ago": [164, 134, 104, 74, 44, 14],
            "purpose_tpl": "Оплата электромонтажных материалов по счёту № {inv}",
            "bcc_opened_days_ago": 920,
        },
        {
            "key": "nurmetall",
            "name": "ТОО «НурМеталлПоставка»",
            "reg_year": 14,
            "reg_month": 2,
            "bank_code": "965",  # ForteBank
            "iik_prefix": "000",
            # 6 payments with median = 2_150_000 KZT
            "amounts": [2_040_000, 2_090_000, 2_130_000, 2_170_000, 2_210_000, 2_260_000],
            "days_ago": [160, 130, 100, 70, 41, 10],
            "purpose_tpl": "Оплата за металлопрокат по договору № 47-М, счёт № {inv}",
            "bcc_opened_days_ago": None,
        },
        {
            "key": "almatyoffice",
            "name": "ТОО «АлматыОфисТрейд»",
            "reg_year": 19,
            "reg_month": 7,
            "bank_code": BCC_BANK_CODE,  # BCC
            "iik_prefix": "KZT",
            # 5 payments with median = 310_000 KZT
            "amounts": [285_000, 300_000, 310_000, 325_000, 340_000],
            "days_ago": [154, 121, 88, 55, 22],
            "purpose_tpl": "Оплата канцелярских и хозяйственных товаров по счёту № {inv}",
            "bcc_opened_days_ago": 540,
        },
    ]

    suppliers: dict[str, dict[str, Any]] = {}
    for spec in suppliers_spec:
        sup_bin = generate_bin(rng, year=spec["reg_year"], month=spec["reg_month"])
        sup_iik = generate_iik(rng, spec["bank_code"], prefix=spec["iik_prefix"])
        sup_bik = BIK_BY_CODE[spec["bank_code"]]
        assert bik_matches_iik(sup_bik, sup_iik, path=banks_path)
        suppliers[spec["key"]] = {
            **spec,
            "bin": sup_bin,
            "iik": sup_iik,
            "bik": sup_bik,
        }

    # --- Additional synthetic entities for demo scenarios ---
    # 1) Yellow scenario: new valid IIK for КазЛогистик Групп in another bank (ForteBank 965).
    yellow_new_bank_code = "965"
    yellow_new_iik = generate_iik(rng, yellow_new_bank_code, prefix="000")
    yellow_new_bik = BIK_BY_CODE[yellow_new_bank_code]
    assert bik_matches_iik(yellow_new_bik, yellow_new_iik, path=banks_path)

    # 2) Red scenario:
    #    - Owner of the BCC account: ТОО «Вектор Трейд» (opened 12 days before DEMO_TODAY)
    #    - Invoice BIN belongs to a different synthetic company: ТОО «Атлант Ресурс»
    #    - Invoice name is a lookalike of ТОО «Алатау Снаб» with a LATIN 'C' (\u0043).
    vektor_bin = generate_bin(rng, year=25, month=11)
    vektor_name = "ТОО «Вектор Трейд»"
    red_bcc_iik = generate_iik(rng, BCC_BANK_CODE, prefix="KZT")
    assert bik_matches_iik(BCC_BIK, red_bcc_iik, path=banks_path)

    red_recipient_bin = generate_bin(rng, year=24, month=6)
    red_registry_name = "ТОО «Атлант Ресурс»"
    # Note: 'C' in "Cнаб" is ASCII Latin U+0043, mimicking Cyrillic 'С' (U+0421).
    red_lookalike_name = 'ТОО "Алатау \u0043наб"'

    # 3) Grey scenario: first payment to a brand-new valid supplier.
    grey_bin = generate_bin(rng, year=21, month=8)
    grey_name = "ТОО «Сарыарка Принт»"
    grey_bank_code = "722"  # Kaspi Bank
    grey_iik = generate_iik(rng, grey_bank_code, prefix="000")
    grey_bik = BIK_BY_CODE[grey_bank_code]
    assert bik_matches_iik(grey_bik, grey_iik, path=banks_path)

    # Ensure all generated BINs are distinct.
    all_bins = [
        client_bin,
        *(s["bin"] for s in suppliers.values()),
        vektor_bin,
        red_recipient_bin,
        grey_bin,
    ]
    assert len(all_bins) == len(set(all_bins)), "Generated duplicate BIN"

    # --- registry.json (BIN -> synthetic company name) ---
    registry: dict[str, str] = {
        client_bin: CLIENT_NAME,
    }
    for sup in suppliers.values():
        registry[sup["bin"]] = sup["name"]
    registry[vektor_bin] = vektor_name
    registry[red_recipient_bin] = red_registry_name
    registry[grey_bin] = grey_name

    # --- bcc_accounts.json (IIK -> {owner_bin, owner_name, opened_at}) ---
    bcc_accounts: dict[str, dict[str, str]] = {
        client_iik: {
            "owner_bin": client_bin,
            "owner_name": CLIENT_NAME,
            "opened_at": (DEMO_TODAY - timedelta(days=1460)).isoformat(),
        },
        red_bcc_iik: {
            "owner_bin": vektor_bin,
            "owner_name": vektor_name,
            "opened_at": (DEMO_TODAY - timedelta(days=12)).isoformat(),
        },
    }
    for sup in suppliers.values():
        if sup["bank_code"] == BCC_BANK_CODE:
            bcc_accounts[sup["iik"]] = {
                "owner_bin": sup["bin"],
                "owner_name": sup["name"],
                "opened_at": (DEMO_TODAY - timedelta(days=sup["bcc_opened_days_ago"])).isoformat(),
            }

    # --- history.json (~30 payments over 6 months before DEMO_TODAY) ---
    raw_payments: list[dict[str, Any]] = []
    invoice_counter = 101
    for sup in suppliers.values():
        # Shuffle amounts deterministically across the payment dates while keeping exact set.
        amounts = list(sup["amounts"])
        rng.shuffle(amounts)
        for days_ago, amount in zip(sup["days_ago"], amounts, strict=True):
            paid_at = (DEMO_TODAY - timedelta(days=days_ago)).isoformat()
            raw_payments.append(
                {
                    "payer_id": CLIENT_PAYER_ID,
                    "paid_at": paid_at,
                    "recipient_name": sup["name"],
                    "recipient_bin": sup["bin"],
                    "recipient_iik": sup["iik"],
                    "recipient_bik": sup["bik"],
                    "amount_kzt": amount,
                    "purpose": sup["purpose_tpl"].format(inv=invoice_counter),
                }
            )
            invoice_counter += 1

    raw_payments.sort(key=lambda item: (item["paid_at"], item["recipient_bin"]))
    payments: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_payments, start=1):
        payments.append({"id": f"HIST-{idx:03d}", **item})

    history = {
        "client": {
            "payer_id": CLIENT_PAYER_ID,
            "name": CLIENT_NAME,
            "bin": client_bin,
            "iik": client_iik,
            "bik": BCC_BIK,
        },
        "payments": payments,
    }

    # --- queue.json (4 demo scenarios: green, yellow, red, grey) ---
    alatau = suppliers["alatau"]
    kazlogistic = suppliers["kazlogistic"]

    queue: list[dict[str, Any]] = [
        {
            "id": "Q-001",
            "scenario": "green",
            "created_at": DEMO_TODAY.isoformat(),
            "payer_id": CLIENT_PAYER_ID,
            "recipient_name": alatau["name"],
            "recipient_bin": alatau["bin"],
            "recipient_iik": alatau["iik"],
            "recipient_bik": alatau["bik"],
            "amount_kzt": 1_360_000,
            "purpose": "Оплата по счёту № 214 за строительные материалы по договору № 14-А",
        },
        {
            "id": "Q-002",
            "scenario": "yellow",
            "created_at": DEMO_TODAY.isoformat(),
            "payer_id": CLIENT_PAYER_ID,
            "recipient_name": kazlogistic["name"],
            "recipient_bin": kazlogistic["bin"],
            "recipient_iik": yellow_new_iik,
            "recipient_bik": yellow_new_bik,
            "amount_kzt": 820_000,
            "purpose": "Оплата транспортно-экспедиционных услуг по счёту № 318",
        },
        {
            "id": "Q-003",
            "scenario": "red",
            "created_at": DEMO_TODAY.isoformat(),
            "payer_id": CLIENT_PAYER_ID,
            "recipient_name": red_lookalike_name,
            "recipient_bin": red_recipient_bin,
            "recipient_iik": red_bcc_iik,
            "recipient_bik": BCC_BIK,
            "amount_kzt": 4_900_000,
            "purpose": "Оплата по договору № 14-А за поставку оборудования, срочно, по новым реквизитам",
        },
        {
            "id": "Q-004",
            "scenario": "grey",
            "created_at": DEMO_TODAY.isoformat(),
            "payer_id": CLIENT_PAYER_ID,
            "recipient_name": grey_name,
            "recipient_bin": grey_bin,
            "recipient_iik": grey_iik,
            "recipient_bik": grey_bik,
            "amount_kzt": 240_000,
            "purpose": "Оплата за полиграфическую продукцию по счёту № 19",
        },
    ]

    registry_path = _write_json(output_dir / "registry.json", registry)
    bcc_accounts_path = _write_json(output_dir / "bcc_accounts.json", bcc_accounts)
    history_path = _write_json(output_dir / "history.json", history)
    queue_path = _write_json(output_dir / "queue.json", queue)

    return {
        "banks": banks_path,
        "registry": registry_path,
        "bcc_accounts": bcc_accounts_path,
        "history": history_path,
        "queue": queue_path,
    }


def main() -> None:
    paths = generate_all()
    for name, path in paths.items():
        print(f"Wrote {name}: {path}")


if __name__ == "__main__":
    main()
