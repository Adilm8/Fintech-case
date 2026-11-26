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


def _build_supplier_payments(
    sup: dict[str, Any],
    rng: random.Random,
    start_invoice: int,
) -> tuple[list[dict[str, Any]], int]:
    """Generate chronological historical payment records for a single supplier."""
    entries: list[dict[str, Any]] = []
    inv = start_invoice

    if "schedule" in sup:
        # Explicit (days_ago, amount, purpose_tpl, use_old_account) schedule.
        for days_ago, amount, purpose_tpl, use_old in sup["schedule"]:
            paid_at = (DEMO_TODAY - timedelta(days=days_ago)).isoformat()
            iik = sup["old_iik"] if use_old else sup["iik"]
            bik = sup["old_bik"] if use_old else sup["bik"]
            entries.append(
                {
                    "payer_id": CLIENT_PAYER_ID,
                    "paid_at": paid_at,
                    "recipient_name": sup["name"],
                    "recipient_bin": sup["bin"],
                    "recipient_iik": iik,
                    "recipient_bik": bik,
                    "amount_kzt": amount,
                    "purpose": purpose_tpl.format(inv=inv),
                }
            )
            inv += 1
        return entries, inv

    amounts = list(sup["amounts"])
    if sup.get("pin_last_amount") is not None:
        pinned = sup["pin_last_amount"]
        amounts.remove(pinned)
        rng.shuffle(amounts)
        amounts.append(pinned)
    elif sup.get("shuffle_amounts", True):
        rng.shuffle(amounts)

    for days_ago, amount in zip(sup["days_ago"], amounts, strict=True):
        paid_at = (DEMO_TODAY - timedelta(days=days_ago)).isoformat()
        entries.append(
            {
                "payer_id": CLIENT_PAYER_ID,
                "paid_at": paid_at,
                "recipient_name": sup["name"],
                "recipient_bin": sup["bin"],
                "recipient_iik": sup["iik"],
                "recipient_bik": sup["bik"],
                "amount_kzt": amount,
                "purpose": sup["purpose_tpl"].format(inv=inv),
            }
        )
        inv += 1
    return entries, inv


def generate_all(output_dir: Path = DATA_DIR) -> dict[str, Path]:
    """Generate all deterministic synthetic JSON files into output_dir."""
    banks_path = write_banks_json(output_dir)
    rng = random.Random(SEED)

    # --- Client company (SME banking with BCC) ---
    # Keep exact initial RNG draw sequence so client and Q-001..Q-004 requisites stay identical.
    client_bin = generate_bin(rng, year=17, month=3)
    client_iik = generate_iik(rng, BCC_BANK_CODE, prefix="KZT", banks_path=banks_path)

    # --- Core 5 regular suppliers (12-month history, preserving exact BIN/IIK and medians) ---
    base_suppliers_spec: list[dict[str, Any]] = [
        {
            "key": "alatau",
            "name": "ТОО «Алатау Снаб»",
            "id_kind": "bin",
            "reg_year": 16,
            "reg_month": 5,
            "bank_code": "601",  # Halyk Bank
            "iik_prefix": "000",
            # 13 payments over 12 months; exact median = 1_350_000 KZT, MAD = 40_000 KZT
            "amounts": [
                1_220_000,
                1_260_000,
                1_290_000,
                1_310_000,
                1_325_000,
                1_340_000,
                1_350_000,
                1_365_000,
                1_380_000,
                1_400_000,
                1_420_000,
                1_460_000,
                1_510_000,
            ],
            "pin_last_amount": 1_350_000,
            "days_ago": [356, 326, 297, 267, 236, 206, 176, 147, 118, 92, 66, 38, 11],
            "purpose_tpl": "Оплата по счёту № {inv} за строительные материалы по договору № 14-А",
            "bcc_opened_days_ago": None,
        },
        {
            "key": "kazlogistic",
            "name": "ТОО «КазЛогистик Групп»",
            "id_kind": "bin",
            "reg_year": 18,
            "reg_month": 9,
            "bank_code": "998",  # Alatau City Bank
            "iik_prefix": "000",
            # 12 payments over 12 months; exact median = 820_000 KZT
            "amounts": [
                720_000,
                745_000,
                765_000,
                790_000,
                805_000,
                815_000,
                825_000,
                840_000,
                860_000,
                885_000,
                910_000,
                940_000,
            ],
            "pin_last_amount": 825_000,
            "days_ago": [351, 320, 290, 259, 229, 198, 168, 138, 109, 79, 49, 18],
            "purpose_tpl": "Оплата транспортно-экспедиционных услуг по счёту № {inv}",
            "bcc_opened_days_ago": None,
        },
        {
            "key": "stepenergo",
            "name": "ТОО «СтепьЭнергоСервис»",
            "id_kind": "bin",
            "reg_year": 15,
            "reg_month": 11,
            "bank_code": BCC_BANK_CODE,  # BCC
            "iik_prefix": "KZT",
            # 12 payments over 12 months; exact median = 540_000 KZT
            "amounts": [
                460_000,
                480_000,
                505_000,
                520_000,
                530_000,
                535_000,
                545_000,
                555_000,
                570_000,
                595_000,
                620_000,
                645_000,
            ],
            "pin_last_amount": 545_000,
            "days_ago": [347, 317, 286, 256, 225, 195, 164, 134, 104, 74, 44, 14],
            "purpose_tpl": "Оплата электромонтажных материалов по счёту № {inv}",
            "bcc_opened_days_ago": 920,
        },
        {
            "key": "nurmetall",
            "name": "ТОО «НурМеталлПоставка»",
            "id_kind": "bin",
            "reg_year": 14,
            "reg_month": 2,
            "bank_code": "965",  # ForteBank
            "iik_prefix": "000",
            # 12 payments over 12 months; exact median = 2_150_000 KZT
            "amounts": [
                1_820_000,
                1_910_000,
                1_980_000,
                2_040_000,
                2_090_000,
                2_130_000,
                2_170_000,
                2_240_000,
                2_320_000,
                2_410_000,
                2_520_000,
                2_640_000,
            ],
            "pin_last_amount": 2_170_000,
            "days_ago": [344, 314, 283, 252, 222, 191, 160, 130, 100, 70, 41, 10],
            "purpose_tpl": "Оплата за металлопрокат по договору № 47-М, счёт № {inv}",
            "bcc_opened_days_ago": None,
        },
        {
            "key": "almatyoffice",
            "name": "ТОО «АлматыОфисТрейд»",
            "id_kind": "bin",
            "reg_year": 19,
            "reg_month": 7,
            "bank_code": BCC_BANK_CODE,  # BCC
            "iik_prefix": "KZT",
            # 11 payments over 12 months; exact median = 310_000 KZT
            "amounts": [
                245_000,
                265_000,
                280_000,
                295_000,
                305_000,
                310_000,
                320_000,
                330_000,
                345_000,
                365_000,
                390_000,
            ],
            "pin_last_amount": 310_000,
            "days_ago": [340, 308, 275, 242, 210, 178, 148, 118, 86, 54, 22],
            "purpose_tpl": "Оплата канцелярских и хозяйственных товаров по счёту № {inv}",
            "bcc_opened_days_ago": 540,
        },
    ]

    suppliers: dict[str, dict[str, Any]] = {}
    for spec in base_suppliers_spec:
        sup_bin = generate_bin(rng, year=spec["reg_year"], month=spec["reg_month"])
        sup_iik = generate_iik(
            rng, spec["bank_code"], prefix=spec["iik_prefix"], banks_path=banks_path
        )
        sup_bik = BIK_BY_CODE[spec["bank_code"]]
        assert bik_matches_iik(sup_bik, sup_iik, path=banks_path)
        suppliers[spec["key"]] = {
            **spec,
            "bin": sup_bin,
            "iik": sup_iik,
            "bik": sup_bik,
        }

    # --- Core demo scenario entities (Q-002..Q-004, exact RNG order preserved) ---
    yellow_new_bank_code = "965"
    yellow_new_iik = generate_iik(rng, yellow_new_bank_code, prefix="000", banks_path=banks_path)
    yellow_new_bik = BIK_BY_CODE[yellow_new_bank_code]
    assert bik_matches_iik(yellow_new_bik, yellow_new_iik, path=banks_path)

    vektor_bin = generate_bin(rng, year=25, month=11)
    vektor_name = "ТОО «Вектор Трейд»"
    red_bcc_iik = generate_iik(rng, BCC_BANK_CODE, prefix="KZT", banks_path=banks_path)
    assert bik_matches_iik(BCC_BIK, red_bcc_iik, path=banks_path)

    red_recipient_bin = generate_bin(rng, year=24, month=6)
    red_registry_name = "ТОО «Атлант Ресурс»"
    # Note: 'C' in "Cнаб" is ASCII Latin U+0043, mimicking Cyrillic 'С' (U+0421).
    red_lookalike_name = 'ТОО "Алатау \u0043наб"'

    grey_bin = generate_bin(rng, year=21, month=8)
    grey_name = "ТОО «Сарыарка Принт»"
    grey_bank_code = "722"  # Kaspi Bank
    grey_iik = generate_iik(rng, grey_bank_code, prefix="000", banks_path=banks_path)
    grey_bik = BIK_BY_CODE[grey_bank_code]
    assert bik_matches_iik(grey_bik, grey_iik, path=banks_path)

    # --- 7 additional suppliers for rich 12-month history (total 12 suppliers, 150 payments) ---
    extra_rng = random.Random(SEED + 100)

    # 6) Seasonal concrete/aggregates supplier (summer construction surge, winter dip)
    beton_purpose = "Оплата за поставку товарного бетона М350 по договору № 62-Б, счёт № {inv}"
    # 7) Crane rental supplier that legally switched bank accounts mid-year (RBK -> Freedom Bank)
    kran_old_purpose = "Оплата аренды башенного крана по договору № 19-К, счёт № {inv}"
    kran_new_purpose = (
        "Оплата аренды башенного крана по доп. соглашению № 2 (договор № 19-К), счёт № {inv}"
    )
    # 9) Insulation supplier with advance (30-35%) + final settlement (65-70%) pairs
    teplo_adv_purpose = "Аванс 30% за теплоизоляционные материалы по договору № 28-Т, счёт № {inv}"
    teplo_bal_purpose = (
        "Доплата 70% по акту приёмки теплоизоляционных материалов (договор № 28-Т), счёт № {inv}"
    )
    # 10) Large cement supplier in BCC with seasonal surges and advance/balance settlements
    cem_adv_purpose = "Аванс 40% за поставку портландцемента М500 по договору № 09-Ц, счёт № {inv}"
    cem_bal_purpose = "Оплата за поставку портландцемента М500 по договору № 09-Ц, счёт № {inv}"

    extra_suppliers_spec: list[dict[str, Any]] = [
        {
            "key": "astanabeton",
            "name": "ТОО «АстанаБетонСервис»",
            "id_kind": "bin",
            "reg_year": 17,
            "reg_month": 4,
            "bank_code": "914",  # Bereke Bank
            "iik_prefix": "000",
            # 14 payments: strong construction seasonality (summer peak ~4.8M, winter ~1.4M)
            # Median = 2_725_000 KZT, MAD = 1_150_000 KZT -> 4_650_000 KZT seasonal payment is green.
            "schedule": [
                (355, 2_850_000, beton_purpose, False),  # Apr 2025 (spring)
                (325, 3_600_000, beton_purpose, False),  # May 2025 (spring ramp)
                (298, 4_550_000, beton_purpose, False),  # Jun 2025 (summer peak)
                (275, 4_950_000, beton_purpose, False),  # Jul 2025 (summer peak)
                (252, 4_800_000, beton_purpose, False),  # Aug 2025 (summer peak)
                (230, 4_200_000, beton_purpose, False),  # Sep 2025 (late summer)
                (205, 3_200_000, beton_purpose, False),  # Sep/Oct 2025 (autumn)
                (177, 2_400_000, beton_purpose, False),  # Oct 2025 (autumn)
                (148, 1_650_000, beton_purpose, False),  # Nov 2025 (winter)
                (119, 1_450_000, beton_purpose, False),  # Dec 2025 (winter)
                (90, 1_350_000, beton_purpose, False),  # Jan 2026 (winter)
                (62, 1_550_000, beton_purpose, False),  # Feb 2026 (winter)
                (34, 2_600_000, beton_purpose, False),  # Mar 2026 (spring start)
                (13, 3_800_000, beton_purpose, False),  # Apr 2026 (spring surge)
            ],
            "bcc_opened_days_ago": None,
        },
        {
            "key": "evraziyakran",
            "name": "ТОО «ЕвразияКранМонтаж»",
            "id_kind": "bin",
            "reg_year": 15,
            "reg_month": 8,
            "old_bank_code": "821",  # Bank RBK (first 6 payments)
            "bank_code": "551",  # Freedom Bank (last 6 payments after legal account change)
            "iik_prefix": "000",
            # 12 payments over 12 months; switched account in Oct/Nov 2025
            "schedule": [
                (352, 910_000, kran_old_purpose, True),
                (322, 980_000, kran_old_purpose, True),
                (291, 1_040_000, kran_old_purpose, True),
                (260, 1_020_000, kran_old_purpose, True),
                (229, 950_000, kran_old_purpose, True),
                (198, 890_000, kran_old_purpose, True),
                (166, 920_000, kran_new_purpose, False),
                (136, 870_000, kran_new_purpose, False),
                (105, 860_000, kran_new_purpose, False),
                (74, 940_000, kran_new_purpose, False),
                (43, 990_000, kran_new_purpose, False),
                (12, 960_000, kran_new_purpose, False),
            ],
            "bcc_opened_days_ago": None,
        },
        {
            "key": "ip_baizhanov",
            "name": "ИП Байжанов К.Т.",
            "id_kind": "iin",
            "iin_year": 84,
            "iin_month": 7,
            "iin_day": 15,
            "bank_code": "722",  # Kaspi Bank
            "iik_prefix": "000",
            # 12 payments over 12 months; small-medium IE contractor paid by IIN
            "amounts": [
                155_000,
                165_000,
                170_000,
                175_000,
                180_000,
                185_000,
                185_000,
                190_000,
                195_000,
                205_000,
                210_000,
                220_000,
            ],
            "pin_last_amount": 185_000,
            "days_ago": [349, 318, 288, 257, 227, 196, 165, 135, 106, 75, 45, 15],
            "purpose_tpl": "Оплата услуг технического обслуживания объекта по акту № {inv}",
            "bcc_opened_days_ago": None,
        },
        {
            "key": "kazteplo",
            "name": "ТОО «КазТеплоИзоляция»",
            "id_kind": "bin",
            "reg_year": 16,
            "reg_month": 10,
            "bank_code": "948",  # Eurasian Bank
            "iik_prefix": "000",
            # 16 payments: 8 paired advance (30%) + final settlement (70%) cycles
            "schedule": [
                (350, 440_000, teplo_adv_purpose, False),
                (336, 980_000, teplo_bal_purpose, False),
                (304, 510_000, teplo_adv_purpose, False),
                (290, 1_160_000, teplo_bal_purpose, False),
                (258, 560_000, teplo_adv_purpose, False),
                (244, 1_250_000, teplo_bal_purpose, False),
                (212, 480_000, teplo_adv_purpose, False),
                (198, 1_090_000, teplo_bal_purpose, False),
                (165, 430_000, teplo_adv_purpose, False),
                (151, 950_000, teplo_bal_purpose, False),
                (116, 420_000, teplo_adv_purpose, False),
                (102, 920_000, teplo_bal_purpose, False),
                (68, 470_000, teplo_adv_purpose, False),
                (54, 1_040_000, teplo_bal_purpose, False),
                (24, 520_000, teplo_adv_purpose, False),
                (9, 1_180_000, teplo_bal_purpose, False),
            ],
            "bcc_opened_days_ago": None,
        },
        {
            "key": "qazaqcem",
            "name": "ТОО «ЦементПром Караганда»",
            "id_kind": "bin",
            "reg_year": 12,
            "reg_month": 3,
            "bank_code": BCC_BANK_CODE,  # BCC
            "iik_prefix": "KZT",
            # 14 payments: large bulk supplier with advances + summer surges
            "schedule": [
                (354, 1_650_000, cem_adv_purpose, False),
                (341, 3_300_000, cem_bal_purpose, False),
                (309, 4_600_000, cem_bal_purpose, False),
                (281, 5_100_000, cem_bal_purpose, False),
                (250, 5_200_000, cem_bal_purpose, False),
                (221, 4_300_000, cem_bal_purpose, False),
                (192, 1_550_000, cem_adv_purpose, False),
                (179, 3_100_000, cem_bal_purpose, False),
                (149, 2_800_000, cem_bal_purpose, False),
                (117, 2_600_000, cem_bal_purpose, False),
                (85, 2_450_000, cem_bal_purpose, False),
                (56, 2_900_000, cem_bal_purpose, False),
                (28, 1_700_000, cem_adv_purpose, False),
                (8, 3_500_000, cem_bal_purpose, False),
            ],
            "bcc_opened_days_ago": 1200,
        },
        {
            "key": "tazasu",
            "name": "ТОО «ТазаСу Сервис»",
            "id_kind": "bin",
            "reg_year": 20,
            "reg_month": 2,
            "bank_code": "849",  # Nurbank
            "iik_prefix": "000",
            # 12 payments: small supplier (office & site drinking water, mild summer bump)
            "schedule": [
                (348, 52_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (319, 64_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (289, 76_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (258, 78_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (228, 72_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (197, 58_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (167, 48_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (137, 45_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (107, 42_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (76, 46_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (46, 54_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
                (16, 60_000, "Оплата доставки питьевой воды по счёту № {inv}", False),
            ],
            "bcc_opened_days_ago": None,
        },
        {
            "key": "digitalit",
            "name": "ТОО «НомадКлауд Софт»",
            "id_kind": "bin",
            "reg_year": 21,
            "reg_month": 5,
            "bank_code": "949",  # Altyn Bank
            "iik_prefix": "000",
            # 10 payments: small-medium IT / 1C cloud subscription + quarterly license renewals
            "schedule": [
                (
                    342,
                    125_000,
                    "Оплата облачного хостинга и сопровождения 1С по счёту № {inv}",
                    False,
                ),
                (
                    306,
                    240_000,
                    "Оплата квартальной лицензии и сопровождения 1С по счёту № {inv}",
                    False,
                ),
                (
                    271,
                    130_000,
                    "Оплата облачного хостинга и сопровождения 1С по счёту № {inv}",
                    False,
                ),
                (
                    235,
                    120_000,
                    "Оплата облачного хостинга и сопровождения 1С по счёту № {inv}",
                    False,
                ),
                (
                    200,
                    135_000,
                    "Оплата облачного хостинга и сопровождения 1С по счёту № {inv}",
                    False,
                ),
                (
                    162,
                    245_000,
                    "Оплата квартальной лицензии и сопровождения 1С по счёту № {inv}",
                    False,
                ),
                (
                    125,
                    130_000,
                    "Оплата облачного хостинга и сопровождения 1С по счёту № {inv}",
                    False,
                ),
                (
                    89,
                    140_000,
                    "Оплата облачного хостинга и сопровождения 1С по счёту № {inv}",
                    False,
                ),
                (
                    52,
                    135_000,
                    "Оплата облачного хостинга и сопровождения 1С по счёту № {inv}",
                    False,
                ),
                (
                    17,
                    145_000,
                    "Оплата облачного хостинга и сопровождения 1С по счёту № {inv}",
                    False,
                ),
            ],
            "bcc_opened_days_ago": None,
        },
    ]

    for spec in extra_suppliers_spec:
        if spec["id_kind"] == "iin":
            sup_id = generate_iin(
                extra_rng,
                year=spec["iin_year"],
                month=spec["iin_month"],
                day=spec["iin_day"],
            )
        else:
            sup_id = generate_bin(extra_rng, year=spec["reg_year"], month=spec["reg_month"])
        sup_iik = generate_iik(
            extra_rng,
            spec["bank_code"],
            prefix=spec["iik_prefix"],
            banks_path=banks_path,
        )
        sup_bik = BIK_BY_CODE[spec["bank_code"]]
        assert bik_matches_iik(sup_bik, sup_iik, path=banks_path)

        record: dict[str, Any] = {
            **spec,
            "bin": sup_id,
            "iik": sup_iik,
            "bik": sup_bik,
        }
        if "old_bank_code" in spec:
            old_code = spec["old_bank_code"]
            old_iik = generate_iik(
                extra_rng, old_code, prefix=spec["iik_prefix"], banks_path=banks_path
            )
            old_bik = BIK_BY_CODE[old_code]
            assert bik_matches_iik(old_bik, old_iik, path=banks_path)
            record["old_iik"] = old_iik
            record["old_bik"] = old_bik
        suppliers[spec["key"]] = record

    # --- Additional synthetic BCC clients & new queue entities ---
    extra_bcc_companies_spec = [
        ("ТОО «Орбита Логистика»", 20, 6, 780),
        ("ТОО «Байтерек Инвест Трейд»", 26, 2, 14),
        ("ТОО «Каспий Технолоджи»", 25, 12, 21),
        ("ТОО «Жетысу ПромСервис»", 18, 4, 610),
    ]
    extra_bcc_companies: list[dict[str, Any]] = []
    for name, reg_y, reg_m, opened_days_ago in extra_bcc_companies_spec:
        comp_bin = generate_bin(extra_rng, year=reg_y, month=reg_m)
        comp_iik = generate_iik(extra_rng, BCC_BANK_CODE, prefix="KZT", banks_path=banks_path)
        assert bik_matches_iik(BCC_BIK, comp_iik, path=banks_path)
        extra_bcc_companies.append(
            {
                "name": name,
                "bin": comp_bin,
                "iik": comp_iik,
                "opened_days_ago": opened_days_ago,
            }
        )

    # Q-009: Kazakh-letter lookalike clone of ТОО «НурМеталлПоставка» (ұ U+04B1 instead of у)
    kz_clone_bin = generate_bin(extra_rng, year=25, month=12)  # young BIN (4 months old)
    kz_clone_name = "ТОО «Н\u04b1рМеталлПоставка»"
    kz_clone_bank_code = "948"  # Eurasian Bank (outside BCC)
    kz_clone_iik = generate_iik(extra_rng, kz_clone_bank_code, prefix="000", banks_path=banks_path)
    kz_clone_bik = BIK_BY_CODE[kz_clone_bank_code]
    assert bik_matches_iik(kz_clone_bik, kz_clone_iik, path=banks_path)

    # Q-010: New legal-entity invoice billed to an individual's IIN (dropper pattern)
    dropper_iin = generate_iin(extra_rng, year=91, month=4, day=12)
    dropper_bank_code = "886"  # Home Credit Bank
    dropper_iik = generate_iik(extra_rng, dropper_bank_code, prefix="000", banks_path=banks_path)
    dropper_bik = BIK_BY_CODE[dropper_bank_code]
    assert bik_matches_iik(dropper_bik, dropper_iik, path=banks_path)

    # Ensure all generated BINs/IINs are distinct.
    all_ids = [
        client_bin,
        *(s["bin"] for s in suppliers.values()),
        vektor_bin,
        red_recipient_bin,
        grey_bin,
        *(c["bin"] for c in extra_bcc_companies),
        kz_clone_bin,
        dropper_iin,
    ]
    assert len(all_ids) == len(set(all_ids)), "Generated duplicate BIN/IIN"

    # --- registry.json (BIN/IIN -> synthetic legal name) ---
    registry: dict[str, str] = {
        client_bin: CLIENT_NAME,
    }
    for sup in suppliers.values():
        registry[sup["bin"]] = sup["name"]
    registry[vektor_bin] = vektor_name
    registry[red_recipient_bin] = red_registry_name
    registry[grey_bin] = grey_name
    for comp in extra_bcc_companies:
        registry[comp["bin"]] = comp["name"]
    registry[kz_clone_bin] = kz_clone_name

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
    for comp in extra_bcc_companies:
        bcc_accounts[comp["iik"]] = {
            "owner_bin": comp["bin"],
            "owner_name": comp["name"],
            "opened_at": (DEMO_TODAY - timedelta(days=comp["opened_days_ago"])).isoformat(),
        }

    # --- history.json (150 payments across 12 suppliers over 12 months before DEMO_TODAY) ---
    raw_payments: list[dict[str, Any]] = []
    invoice_counter = 101
    for sup in suppliers.values():
        sup_payments, invoice_counter = _build_supplier_payments(sup, extra_rng, invoice_counter)
        raw_payments.extend(sup_payments)

    raw_payments.sort(key=lambda item: (item["paid_at"], item["recipient_bin"], item["amount_kzt"]))
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

    # --- queue.json (Q-001..Q-004 preserved verbatim + Q-005..Q-010 new realistic scenarios) ---
    alatau = suppliers["alatau"]
    kazlogistic = suppliers["kazlogistic"]
    stepenergo = suppliers["stepenergo"]
    astanabeton = suppliers["astanabeton"]
    evraziyakran = suppliers["evraziyakran"]
    ip_baizhanov = suppliers["ip_baizhanov"]

    # Intentional single-digit typo at the end of StepEnergo's real BCC IIK (fails mod-97)
    typo_last_digit = str((int(stepenergo["iik"][-1]) + 1) % 10)
    typo_iik = f"{stepenergo['iik'][:-1]}{typo_last_digit}"
    assert not iik_ok(typo_iik, check_bank_code=True, banks_path=banks_path)[0]

    queue: list[dict[str, Any]] = [
        # Q-001..Q-004: preserved demo scenarios without changes
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
        # Q-005..Q-010: additional realistic scenarios
        {
            "id": "Q-005",
            "scenario": "green",
            "created_at": DEMO_TODAY.isoformat(),
            "payer_id": CLIENT_PAYER_ID,
            "recipient_name": astanabeton["name"],
            "recipient_bin": astanabeton["bin"],
            "recipient_iik": astanabeton["iik"],
            "recipient_bik": astanabeton["bik"],
            "amount_kzt": 4_650_000,
            "purpose": "Оплата за поставку товарного бетона М350 (сезонный заказ, апрель) по счёту № 412",
        },
        {
            "id": "Q-006",
            "scenario": "green",
            "created_at": DEMO_TODAY.isoformat(),
            "payer_id": CLIENT_PAYER_ID,
            "recipient_name": evraziyakran["name"],
            "recipient_bin": evraziyakran["bin"],
            "recipient_iik": evraziyakran["iik"],
            "recipient_bik": evraziyakran["bik"],
            "amount_kzt": 970_000,
            "purpose": "Оплата аренды башенного крана по доп. соглашению № 2 (договор № 19-К), счёт № 419",
        },
        {
            "id": "Q-007",
            "scenario": "invalid",
            "created_at": DEMO_TODAY.isoformat(),
            "payer_id": CLIENT_PAYER_ID,
            "recipient_name": stepenergo["name"],
            "recipient_bin": stepenergo["bin"],
            "recipient_iik": typo_iik,
            "recipient_bik": stepenergo["bik"],
            "amount_kzt": 550_000,
            "purpose": "Оплата электромонтажных материалов по счёту № 425",
        },
        {
            "id": "Q-008",
            "scenario": "green",
            "created_at": DEMO_TODAY.isoformat(),
            "payer_id": CLIENT_PAYER_ID,
            "recipient_name": ip_baizhanov["name"],
            "recipient_bin": ip_baizhanov["bin"],
            "recipient_iik": ip_baizhanov["iik"],
            "recipient_bik": ip_baizhanov["bik"],
            "amount_kzt": 190_000,
            "purpose": "Оплата услуг технического обслуживания объекта по акту № 431",
        },
        {
            "id": "Q-009",
            "scenario": "red",
            "created_at": DEMO_TODAY.isoformat(),
            "payer_id": CLIENT_PAYER_ID,
            "recipient_name": kz_clone_name,
            "recipient_bin": kz_clone_bin,
            "recipient_iik": kz_clone_iik,
            "recipient_bik": kz_clone_bik,
            "amount_kzt": 2_280_000,
            "purpose": "Оплата за металлопрокат по договору № 47-М, счёт № 438",
        },
        {
            "id": "Q-010",
            "scenario": "yellow",
            "created_at": DEMO_TODAY.isoformat(),
            "payer_id": CLIENT_PAYER_ID,
            "recipient_name": "ТОО «Арматура Центр»",
            "recipient_bin": dropper_iin,
            "recipient_iik": dropper_iik,
            "recipient_bik": dropper_bik,
            "amount_kzt": 1_450_000,
            "purpose": "Оплата за поставку арматуры А500С по счёту № 442",
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
