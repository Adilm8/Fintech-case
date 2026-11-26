"""Deterministic generator for the labeled evaluation set (data/eval_set.json).

Builds 400 labeled payment verification cases (200 legit, 200 attack) using SEED = 42
on top of the client payment history produced by scripts/generate_data.py.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.risk.config import BCC_BANK_CODE, BCC_BIK
from app.risk.names import name_similarity, normalize_company_name
from app.validators.kz import (
    bik_matches_iik,
    bik_ok,
    bin_iin_checksum_ok,
    bin_kind,
    iik_ok,
    load_banks,
)
from scripts.generate_data import CLIENT_PAYER_ID, generate_bin, generate_iik, generate_iin

SEED = 42
DATA_DIR = BACKEND_ROOT / "data"
OUTPUT_FILENAME = "eval_set.json"

# Clean unrelated company names for new legitimate suppliers and typo-free drops.
_NEW_LEGIT_CORP_NAMES: tuple[str, ...] = (
    "ТОО «Акмола ДорСтрой»",
    "ТОО «Тарбагатай Стекло»",
    "ТОО «Шымкент Пластик Пром»",
    "ТОО «Костанай АгроТех»",
    "ТОО «Атырау НефтеХимСнаб»",
    "ТОО «Павлодар Полимер»",
    "ТОО «Уральск Геодезия»",
    "ТОО «Тараз Керамика»",
    "ТОО «Кызылорда ЛифтМонтаж»",
    "ТОО «Актобе ВентСистемы»",
    "ТОО «Семей ФасадПрофиль»",
    "ТОО «Петропавл АвтоШины»",
    "ТОО «Кокшетау ЛесПром»",
    "ТОО «Талдыкорган СветоТех»",
    "ТОО «Туркестан Плитка»",
    "АО «КазСпецОдежда»",
    "ТОО «Мангистау ПортТранс»",
    "ТОО «Балхаш КабельТрейд»",
    "ТОО «Экибастуз НасосСервис»",
    "ТОО «Рудный КрепёжОпт»",
    "ТОО «Жезказган РезинаТех»",
    "ТОО «Капшагай Оконные Системы»",
    "ТОО «Сатпаев КровляМастер»",
    "ТОО «Риддер Лесоматериалы»",
    "ТОО «Темиртау СваркаПрофи»",
    "ТОО «Актау Морской Груз»",
    "ТОО «Боровое ДеревоПром»",
    "ТОО «Оскемен ПриборКонтроль»",
)

_NEW_LEGIT_BRAND_NUMERIC_NAMES: tuple[str, ...] = (
    "ТОО «ЭкоSTAR»",
    "ТОО «QazaqСтрой»",
    "ТОО «Алматы-2»",
    "ТОО «Строй 2020»",
    "ТОО «Бетон М350»",
)

# Legitimate new suppliers sharing generic words (Сервис, Снаб, Групп, Трейд, Софт, Монтаж)
# or IE surnames with different initials — MUST NOT be flagged as lookalike or amount anomaly.
_NEW_LEGIT_GENERIC_WORD_SPECS: tuple[tuple[str, str], ...] = (
    ("ТОО «Астана Сервис»", "bin"),
    ("ТОО «Монтаж Сервис»", "bin"),
    ("ИП Байжанова А.К.", "iin"),
    ("ИП Байжанов А.С.", "iin"),
    ("ТОО «Алматы Сервис»", "bin"),
    ("ТОО «Караганда Сервис»", "bin"),
    ("ТОО «Шымкент Снаб»", "bin"),
    ("ТОО «Актобе Снаб»", "bin"),
    ("ТОО «Актау Снаб»", "bin"),
    ("ТОО «Павлодар Групп»", "bin"),
    ("ТОО «Костанай Групп»", "bin"),
    ("ТОО «Атырау Трейд»", "bin"),
    ("ТОО «Тараз Поставка»", "bin"),
    ("ТОО «Семей Строй Сервис»", "bin"),
    ("ТОО «Уральск Софт»", "bin"),
    ("ТОО «Петропавл Логистик»", "bin"),
    ("ТОО «Кызылорда Пром»", "bin"),
    ("ТОО «Астана Монтаж Групп»", "bin"),
    ('ТОО "Almaty Service"', "bin"),
    ('ТОО "Astana Trade Group"', "bin"),
)

_BUDGET_RECIPIENT_NAMES: tuple[str, ...] = (
    "ГУ «Управление государственных доходов по г. Астана»",
    "ГУ «Комитет казначейства Министерства финансов РК»",
    "НАО «ГК «Правительство для граждан»»",
    "ГУ «Департамент государственных доходов по г. Алматы»",
)

_UNICODE_EVASION_CASES: tuple[tuple[str, str], ...] = (
    ("ТОО «Алатау Снаб»", "ТОО «\u0251латау Снаб»"),
    ("ТОО «Алатау Снаб»", "ТОО «Алатау \u13dfнаб»"),
    ("ТОО «Алатау Снаб»", "ТОО «Алат\u3164ау\u2800 Сн\u0301аб\ufe0f»"),
    ("ТОО «КазЛогистик Групп»", "ТОО «Ка3Л0гистик Групп»"),
    ("ТОО «Алатау Снаб»", "ТОО «Алатау Сн0б»"),
    ("ТОО «КазЛогистик Групп»", "ТОО «К\u0251зЛогистик Групп»"),
    ("ТОО «СтепьЭнергоСервис»", "ТОО «\u13dfтепьЭнергоСервис»"),
    ("ТОО «НурМеталлПоставка»", "ТОО «НурМеталлП0ставка»"),
    ("ТОО «АлматыОфисТрейд»", "ТОО «Алматы0фисТрейд»"),
    ("ТОО «АстанаБетонСервис»", "ТОО «Аст\u0251наБетонСервис»"),
    ("ТОО «ТазаСу Сервис»", "ТОО «Таз\u0301а\u200bСу \u13dfервис»"),
    ("ТОО «КазТеплоИзоляция»", "ТОО «Ка3Тепл0Изоляция»"),
    ("ТОО «ЦементПром Караганда»", "ТОО «ЦементПр0м Караганда»"),
    # 2 honest blind-spot cases: brand-new unrelated shell with subtle normal digit/suffix
    ("ТОО «Алатау Снаб»", "ТОО «Вектор Логистик-7»"),
    ("ТОО «КазЛогистик Групп»", "ТОО «СтарТранс 2026»"),
)

_VARIANT_TRANSLIT_MAP: tuple[tuple[str, str], ...] = (
    ("ТОО «Алатау Снаб»", "ТОО «Алатау Снабжение»"),
    ("ТОО «Алатау Снаб»", "ТОО «АлатауСнабСервис»"),
    ("ТОО «Алатау Снаб»", "ТОО «Алатау Снабкомплект»"),
    ("ТОО «Алатау Снаб»", 'ТОО "Alatau Snab"'),
    ("ТОО «Алатау Снаб»", 'LLP "Alatau Snabzhenie"'),
    ("ТОО «КазЛогистик Групп»", 'LLP "KazLogistik Grupp"'),
)

_K2_LOOKALIKE_VARIANTS: tuple[tuple[str, str], ...] = (
    ("ТОО «Алатау Снаб»", "ТОО «Торговый дом Алатау»"),
    ("ТОО «Алатау Снаб»", "ТОО «А-Снаб»"),
    ("ТОО «Алатау Снаб»", "ТОО «Alatau Supply»"),
    ("ТОО «Алатау Снаб»", "ТОО «Алатоо Снаб»"),
)

_DROPPER_KBE_ONLY_NAMES: tuple[str, ...] = (
    "Арматура Поставка",
    "СнабЦентр Астана",
    "МеталлСервис Казахстан",
    "КабельПром Трейд",
    "СтройБаза Алматы",
    "СпецТех Комплект",
)

_NEW_LEGIT_IE_NAMES: tuple[str, ...] = (
    "ИП Сулейменов Д.А.",
    "ИП Нурпеисова Г.М.",
    "ИП Абдрахманов Е.С.",
    "ИП Тулегенов Р.К.",
    "ИП Мусаева А.Т.",
    "ИП Жумабаев Б.Н.",
    "ИП Сатыбалдиева М.О.",
)

_DROP_SHELL_NAMES: tuple[str, ...] = (
    "ТОО «Меридиан Поставка»",
    "ТОО «Зенит СтройКомплект»",
    "ТОО «Горизонт ИнвестГрупп»",
    "ТОО «Полюс ТехноСнаб»",
    "ТОО «Импульс БизнесТрейд»",
    "ТОО «Сфера Контракт»",
    "ТОО «Орион ПромРесурс»",
    "ТОО «Эверест Альянс»",
    "ТОО «Кристалл Маркет»",
    "ТОО «Прайд КапиталСтрой»",
    "ТОО «Триумф Партнёр»",
    "ТОО «Арсенал Логистик»",
    "ТОО «Спектр Материалы»",
    "ТОО «Регион ОптСнаб»",
    "ТОО «Сигма Инжиниринг»",
    "ТОО «Квант Комплектация»",
    "ТОО «Прогресс Девелопмент»",
    "ТОО «Альфа СтройРесурс»",
    "ТОО «Стандарт Импорт»",
    "ТОО «Лидер Коммерц»",
)

_DROPPER_CORP_NAMES: tuple[str, ...] = (
    "ТОО «КазАрматура Торг»",
    "ТОО «Астана ПрофильПлюс»",
    "ТОО «СтепьСтрой Ресурс»",
    "АО «ПромСнаб Импорт»",
    "ЖШС «Береке Құрылыс»",
    'LLP "Qazaq Build Trade"',
    "Т.О.О. «ЮгМеталл Снаб»",
    "ТОО «Сарыарка БетонПлюс»",
    "ТОО «Батыс ЭнергоКомплект»",
    "ТОО «Шыгыс Инструмент»",
    "ТОО «Орталык СпецТех»",
    "ТОО «Север Изоляция»",
)

_DROPPER_NO_LEGAL_FORM_NAMES: tuple[str, ...] = (
    "СнабСтрой Астана",
    "МеталлТрейд Актау",
    "ТехСервис Комплект",
    "Алматы Поставка Центр",
)

_REBRAND_NAMES: dict[str, tuple[str, ...]] = {
    "ТОО «Алатау Снаб»": ("ТОО «Алатау Билдинг Групп»", "ТОО «АС Стройматериалы»"),
    "ТОО «КазЛогистик Групп»": ("ТОО «ТрансЕвразия Карго»", "ТОО «КЛГ Фрейт»"),
    "ТОО «СтепьЭнергоСервис»": ("ТОО «ВольтАстана Инжиниринг»", "ТОО «СЭС Электрик»"),
    "ТОО «НурМеталлПоставка»": ("ТОО «СтальПрокат Холдинг»", "ТОО «НМП Металлургия»"),
    "ТОО «АлматыОфисТрейд»": ("ТОО «ОфисМаркет Казахстан»",),
    "ТОО «АстанаБетонСервис»": ("ТОО «Столица ЖБИ Завод»",),
    "ТОО «ЕвразияКранМонтаж»": ("ТОО «Высота СпецТехника»",),
    "ИП Байжанов К.Т.": ("ИП Байжанов Сервис",),
    "ТОО «КазТеплоИзоляция»": ("ТОО «ТермоЗащита Пром»",),
    "ТОО «ЦементПром Караганда»": ("ТОО «ЦентрЦемент Холдинг»",),
    "ТОО «ТазаСу Сервис»": ("ТОО «АкваАстана Доставка»",),
    "ТОО «НомадКлауд Софт»": ("ТОО «Цифровые Решения КЗ»",),
}

_URGENT_TAIL: tuple[str, ...] = (
    "срочно",
    "по новым реквизитам",
    "срочно, изменились реквизиты",
    "смена реквизитов, оплатить сегодня",
    "жедел төлем",
    "шұғыл",
)


def _round_kzt(amount: float) -> int:
    """Round KZT amount to realistic thousands (or hundreds for small amounts)."""
    if amount < 100_000:
        return max(5_000, round(amount / 1_000.0) * 1_000)
    return max(10_000, round(amount / 5_000.0) * 5_000)


def _dump_eval_json(payload: dict[str, Any]) -> str:
    """Serialize eval_set payload as readable JSON with one case per line."""
    header = (
        "{\n"
        f'  "seed": {payload["seed"]},\n'
        f'  "payer_id": {json.dumps(payload["payer_id"], ensure_ascii=False)},\n'
        f'  "total_cases": {payload["total_cases"]},\n'
        '  "cases": [\n'
    )
    rows = [
        "    " + json.dumps(case, ensure_ascii=False, separators=(", ", ": "))
        for case in payload["cases"]
    ]
    return header + ",\n".join(rows) + "\n  ]\n}\n"


def _is_distinct_from_history(name: str, hist_names: list[str]) -> bool:
    norm_candidate = normalize_company_name(name)
    cand_tokens = set(norm_candidate.split())
    for h_name in hist_names:
        if name_similarity(name, h_name) >= 75.0:
            return False
        norm_h = normalize_company_name(h_name)
        h_tokens = set(norm_h.split())
        if len(norm_h) >= 8 and h_tokens.issubset(cand_tokens):
            return False
    return True


def _format_name_variant(rng: random.Random, name: str, id_kind: str) -> str:
    """Apply a legitimate legal-form / punctuation / casing variation to a known supplier name."""
    if id_kind == "iin":
        core = name.removeprefix("ИП ").strip()
        variants = [
            f"И.П. {core}",
            f"ЖК {core}",
            f"Индивидуальный предприниматель {core}",
            f"Жеке кәсіпкер {core}",
            f"IP {core}",
            f"ИП  {core.upper()}",
        ]
        return rng.choice(variants)

    core = name.replace("ТОО ", "").replace("«", "").replace("»", "").strip()
    variants = [
        f'ТОО "{core}"',
        f"ЖШС «{core}»",
        f'LLP "{core}"',
        f"Т.О.О. «{core}»",
        f"Товарищество с ограниченной ответственностью «{core}»",
        f"ТОО   «{core.upper()}»",
        f'TOO "{core}"',
    ]
    return rng.choice(variants)


def _make_lookalike_name(rng: random.Random, base_name: str, style: str) -> str:
    """Build a lookalike variant of a known supplier name using the requested spoofing style."""
    if style == "latin":
        homoglyphs = {
            "А": "A",
            "В": "B",
            "С": "C",
            "Е": "E",
            "Н": "H",
            "К": "K",
            "М": "M",
            "О": "O",
            "Р": "P",
            "Т": "T",
            "Х": "X",
            "а": "a",
            "е": "e",
            "о": "o",
            "р": "p",
            "с": "c",
            "х": "x",
        }
        # Pick a position inside the company core (after legal form)
        start = base_name.find("«") + 1 if "«" in base_name else 4
        candidates = [i for i in range(start, len(base_name)) if base_name[i] in homoglyphs]
        idx = rng.choice(candidates)
        return base_name[:idx] + homoglyphs[base_name[idx]] + base_name[idx + 1 :]

    if style == "greek":
        greek_map = {
            "А": "\u0391",
            "Е": "\u0395",
            "К": "\u039a",
            "М": "\u039c",
            "О": "\u039f",
            "Р": "\u03a1",
            "Т": "\u03a4",
            "о": "\u03bf",
        }
        start = base_name.find("«") + 1 if "«" in base_name else 4
        candidates = [i for i in range(start, len(base_name)) if base_name[i] in greek_map]
        idx = rng.choice(candidates)
        return base_name[:idx] + greek_map[base_name[idx]] + base_name[idx + 1 :]

    if style == "kazakh":
        kz_map = {
            "К": "Қ",
            "к": "қ",
            "У": "Ұ",
            "у": "ұ",
            "Г": "Ғ",
            "г": "ғ",
            "А": "Ә",
            "а": "ә",
            "О": "Ө",
            "о": "ө",
            "И": "І",
            "и": "і",
            "Н": "Ң",
            "н": "ң",
        }
        start = base_name.find("«") + 1 if "«" in base_name else 4
        candidates = [i for i in range(start, len(base_name)) if base_name[i] in kz_map]
        idx = rng.choice(candidates)
        return base_name[:idx] + kz_map[base_name[idx]] + base_name[idx + 1 :]

    if style == "token_set":
        core = base_name.replace("ТОО ", "").replace("«", "").replace("»", "").strip()
        suffix = rng.choice(("Трейдинг Казахстан", "Групп Астана", "Сервис Плюс", "Опт Торг"))
        return f"ТОО «{core} {suffix}»"

    if style == "typo":
        core = base_name.replace("ТОО ", "").replace("«", "").replace("»", "").strip()
        return f"ТОО «{core}{core[-1]}»"

    # Hard low-similarity impersonation (abbreviated / altered stem below 85% similarity)
    hard_map = {
        "ТОО «Алатау Снаб»": "ТОО «Алатау Групп»",
        "ТОО «КазЛогистик Групп»": "ТОО «КазЛогистика Плюс»",
        "ТОО «НурМеталлПоставка»": "ТОО «НурМеталл Торг»",
        "ТОО «АстанаБетонСервис»": "ТОО «Астана Бетон Пром»",
    }
    return hard_map.get(base_name, "ТОО «Алатау Групп»")


def _validate_case(case: dict[str, Any], banks_path: Path) -> None:
    req = case["request"]
    assert case["label"] in ("legit", "attack")
    assert bin_iin_checksum_ok(req["recipient_bin"]), f"Bad BIN/IIN in {case['id']}"
    assert bin_kind(req["recipient_bin"]) is not None, f"Bad kind in {case['id']}"
    ok, err = iik_ok(req["recipient_iik"], check_bank_code=True, banks_path=banks_path)
    assert ok, f"Bad IIK in {case['id']}: {err}"
    assert bik_ok(req["recipient_bik"], path=banks_path), f"Bad BIK in {case['id']}"
    assert bik_matches_iik(req["recipient_bik"], req["recipient_iik"], path=banks_path), (
        f"BIK/IIK mismatch in {case['id']}"
    )
    assert req["amount_kzt"] > 0


def generate_eval_set(
    data_dir: Path = DATA_DIR,
    *,
    output_path: Path | None = None,
) -> Path:
    """Generate 400 deterministic labeled evaluation cases into data/eval_set.json."""
    base_dir = data_dir.resolve()
    banks_path = base_dir / "banks.json"
    banks = load_banks(banks_path)
    bik_by_code = {b["code"]: b["bik"] for b in banks}
    non_bcc_codes = [
        b["code"]
        for b in banks
        if b["code"] not in (BCC_BANK_CODE, "125") and not b.get("budget", False)
    ]

    history_raw = json.loads((base_dir / "history.json").read_text(encoding="utf-8"))
    registry: dict[str, str] = json.loads((base_dir / "registry.json").read_text(encoding="utf-8"))
    bcc_accounts: dict[str, dict[str, str]] = json.loads(
        (base_dir / "bcc_accounts.json").read_text(encoding="utf-8")
    )
    queue_raw: list[dict[str, Any]] = json.loads(
        (base_dir / "queue.json").read_text(encoding="utf-8")
    )
    bank_signals_path = base_dir / "bank_signals.json"
    bank_signals: dict[str, Any] = (
        json.loads(bank_signals_path.read_text(encoding="utf-8"))
        if bank_signals_path.exists()
        else {}
    )
    complaints_map: dict[str, dict[str, Any]] = bank_signals.get("complaints", {})
    fresh_inflows_map: dict[str, dict[str, Any]] = bank_signals.get("fresh_inflows", {})
    watchlist_map: dict[str, dict[str, Any]] = bank_signals.get("mule_watchlist", {})
    known_bins_map: dict[str, dict[str, Any]] = bank_signals.get("bank_known_bin", {})
    queue_iiks = {str(q["recipient_iik"]) for q in queue_raw}
    bankwide_iiks = set(complaints_map) | set(fresh_inflows_map) | set(watchlist_map)
    payments: list[dict[str, Any]] = history_raw["payments"]
    payer_id = str(history_raw["client"]["payer_id"] or CLIENT_PAYER_ID)

    # Aggregate supplier profiles from history.json
    by_bin: dict[str, list[dict[str, Any]]] = {}
    for p in payments:
        by_bin.setdefault(p["recipient_bin"], []).append(p)

    suppliers: list[dict[str, Any]] = []
    for sup_bin, hist in sorted(by_bin.items()):
        hist_sorted = sorted(hist, key=lambda x: (x["paid_at"], x["id"]))
        amounts = [float(x["amount_kzt"]) for x in hist_sorted]
        med = statistics.median(amounts)
        mad = statistics.median([abs(a - med) for a in amounts])
        last = hist_sorted[-1]
        suppliers.append(
            {
                "bin": sup_bin,
                "name": last["recipient_name"],
                "id_kind": bin_kind(sup_bin),
                "iik": last["recipient_iik"],
                "bik": last["recipient_bik"],
                "bank_code": last["recipient_iik"][4:7],
                "all_iiks": sorted({x["recipient_iik"] for x in hist_sorted}),
                "median": med,
                "mad": mad,
                "max_amount": max(amounts),
                "min_amount": min(amounts),
                "purpose_sample": last["purpose"],
                "oldest_purpose": hist_sorted[0]["purpose"],
            }
        )

    corp_suppliers = [s for s in suppliers if s["id_kind"] == "bin"]
    hist_names = [s["name"] for s in suppliers]
    hist_bins = {s["bin"] for s in suppliers}
    hist_iiks = {iik for s in suppliers for iik in s["all_iiks"]}

    all_amounts = sorted(float(p["amount_kzt"]) for p in payments)
    client_p90 = all_amounts[int(0.9 * (len(all_amounts) - 1))]

    # Find specific suppliers
    switched_sup = next(s for s in suppliers if len(s["all_iiks"]) > 1)
    seasonal_sups = [
        s
        for s in suppliers
        if s["name"]
        in (
            "ТОО «АстанаБетонСервис»",
            "ТОО «ЦементПром Караганда»",
            "ТОО «КазТеплоИзоляция»",
            "ТОО «НурМеталлПоставка»",
            "ТОО «ТазаСу Сервис»",
        )
    ]
    steady_sups = [
        s
        for s in suppliers
        if s["name"]
        in (
            "ТОО «Алатау Снаб»",
            "ТОО «КазЛогистик Групп»",
            "ТОО «СтепьЭнергоСервис»",
            "ТОО «АлматыОфисТрейд»",
            "ТОО «НомадКлауд Софт»",
        )
    ]

    # Third-party BCC accounts (non-client accounts in bcc_accounts.json)
    client_bin = history_raw["client"]["bin"]
    other_bcc_entries = [
        (iik, info) for iik, info in sorted(bcc_accounts.items()) if info["owner_bin"] != client_bin
    ]
    new_bcc_non_hist_entries = [
        (iik, info)
        for iik, info in other_bcc_entries
        if info["owner_bin"] not in hist_bins and info["opened_at"] >= "2026-03-22"
    ]
    non_bcc_hist_suppliers = [s for s in suppliers if s["bank_code"] != BCC_BANK_CODE]

    rng = random.Random(SEED)
    cases: list[dict[str, Any]] = []
    inv_no = 1001

    def add_case(
        *,
        label: str,
        kind: str,
        recipient_name: str,
        recipient_bin: str,
        recipient_iik: str,
        recipient_bik: str,
        amount_kzt: int,
        purpose: str,
        trusted: bool = False,
        kbe: str = "",
        knp: str = "",
        prior_checks: list[dict[str, Any]] | None = None,
    ) -> None:
        nonlocal inv_no
        case_id = f"EVAL-{len(cases) + 1:03d}"
        req_payload: dict[str, Any] = {
            "payer_id": payer_id,
            "recipient_name": recipient_name,
            "recipient_bin": recipient_bin,
            "recipient_iik": recipient_iik,
            "recipient_bik": recipient_bik,
            "amount_kzt": amount_kzt,
            "purpose": purpose,
        }
        if kbe:
            req_payload["kbe"] = kbe
        if knp:
            req_payload["knp"] = knp
        record: dict[str, Any] = {
            "id": case_id,
            "label": label,
            "kind": kind,
            "trusted": trusted,
            "request": req_payload,
        }
        if prior_checks:
            record["prior_checks"] = prior_checks
        _validate_case(record, banks_path)
        cases.append(record)
        inv_no += 1

    def fresh_bin(year_range: tuple[int, int] = (14, 24), entity_digit: int = 4) -> str:
        while True:
            yr = rng.randint(year_range[0], year_range[1])
            mo = rng.randint(1, 12)
            # Keep strictly outside 12 months of 2026-04 when requesting older BINs
            if year_range[1] <= 24 or (yr < 25) or (yr == 25 and mo <= 3):
                cand = generate_bin(rng, year=yr, month=mo, entity_digit=entity_digit)
                if cand not in registry and cand not in hist_bins:
                    return cand

    def fresh_young_bin() -> str:
        while True:
            # 2025-06 .. 2026-03 (1..10 months before DEMO_TODAY 2026-04-20)
            ym = rng.choice(
                [(25, 6), (25, 8), (25, 10), (25, 11), (25, 12), (26, 1), (26, 2), (26, 3)]
            )
            cand = generate_bin(rng, year=ym[0], month=ym[1])
            if cand not in registry and cand not in hist_bins:
                return cand

    def fresh_iin() -> str:
        while True:
            cand = generate_iin(rng)
            if cand not in registry and cand not in hist_bins:
                return cand

    def fresh_iik(bank_code: str) -> str:
        prefix = "KZT" if bank_code == BCC_BANK_CODE else "000"
        while True:
            cand = generate_iik(rng, bank_code, prefix=prefix, banks_path=banks_path)
            if cand not in hist_iiks and cand not in bcc_accounts and cand not in bankwide_iiks:
                return cand

    # Separate bank-wide signal pools for popular bank-known providers vs external droppers
    popular_branch_pairs: list[tuple[str, str, str, str]] = []
    popular_iiks: set[str] = set()
    for kbin, info in sorted(known_bins_map.items()):
        if kbin in hist_bins or kbin == client_bin:
            continue
        prov_name = registry.get(kbin, "")
        for biik in info.get("known_iiks", []):
            popular_iiks.add(biik)
            if prov_name and biik in fresh_inflows_map:
                bcode = biik[4:7]
                popular_branch_pairs.append((kbin, prov_name, biik, bik_by_code[bcode]))

    ext_complaints_1_2 = sorted(
        iik
        for iik, info in complaints_map.items()
        if iik not in queue_iiks
        and iik not in watchlist_map
        and iik not in fresh_inflows_map
        and 1 <= int(info.get("count", 0)) < 3
    )
    ext_complaints_3plus = sorted(
        iik
        for iik, info in complaints_map.items()
        if iik not in queue_iiks
        and iik not in watchlist_map
        and iik not in fresh_inflows_map
        and int(info.get("count", 0)) >= 3
    )
    ext_watchlist_iiks = sorted(iik for iik in watchlist_map if iik not in queue_iiks)
    ext_fresh_below = sorted(
        iik
        for iik, info in fresh_inflows_map.items()
        if iik not in queue_iiks
        and iik not in popular_iiks
        and iik not in complaints_map
        and iik not in watchlist_map
        and int(info.get("distinct_payers_7d", 0)) < 3
    )
    ext_fresh_3_4 = sorted(
        iik
        for iik, info in fresh_inflows_map.items()
        if iik not in queue_iiks
        and iik not in popular_iiks
        and iik not in complaints_map
        and iik not in watchlist_map
        and 3 <= int(info.get("distinct_payers_7d", 0)) < 5
    )
    ext_fresh_5plus = sorted(
        iik
        for iik, info in fresh_inflows_map.items()
        if iik not in queue_iiks
        and iik not in popular_iiks
        and iik not in complaints_map
        and iik not in watchlist_map
        and int(info.get("distinct_payers_7d", 0)) >= 5
    )
    ext_combined_comp_fresh = sorted(
        iik
        for iik in complaints_map
        if iik in fresh_inflows_map and iik not in watchlist_map and iik not in queue_iiks
    )

    # =========================================================================
    # LEGIT CASES (200 total)
    # =========================================================================

    # 1. legit_same (20): normal repeat payments to all 12 known suppliers
    for i in range(20):
        sup = suppliers[i % len(suppliers)]
        factor = rng.uniform(0.85, 1.18)
        amt = _round_kzt(sup["median"] * factor)
        add_case(
            label="legit",
            kind="legit_same",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=sup["iik"],
            recipient_bik=sup["bik"],
            amount_kzt=amt,
            purpose=f"Оплата по договору, счёт № {inv_no}",
        )

    # 2. legit_name_formatting_variant (15): legal form/quote/case variants on known (BIN, IIK)
    for i in range(15):
        sup = suppliers[i % len(suppliers)]
        amt = _round_kzt(sup["median"] * rng.uniform(0.90, 1.15))
        variant_name = _format_name_variant(rng, sup["name"], sup["id_kind"])
        add_case(
            label="legit",
            kind="legit_name_formatting_variant",
            recipient_name=variant_name,
            recipient_bin=sup["bin"],
            recipient_iik=sup["iik"],
            recipient_bik=sup["bik"],
            amount_kzt=amt,
            purpose=f"Оплата по акту выполненных работ № {inv_no}",
        )

    # 3. legit_seasonal_amount (25): 18 normal seasonal surges + 7 sharp bulk spikes
    for i in range(18):
        sup = seasonal_sups[i % len(seasonal_sups)]
        factor = rng.uniform(1.45, 2.25)
        amt = _round_kzt(sup["median"] * factor)
        add_case(
            label="legit",
            kind="legit_seasonal_amount",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=sup["iik"],
            recipient_bik=sup["bik"],
            amount_kzt=amt,
            purpose=f"Оплата сезонной партии материалов по счёту № {inv_no}",
        )
    for i in range(7):
        sup = steady_sups[i % len(steady_sups)]
        factor = rng.uniform(2.90, 3.70)
        amt = _round_kzt(sup["median"] * factor)
        add_case(
            label="legit",
            kind="legit_seasonal_amount",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=sup["iik"],
            recipient_bik=sup["bik"],
            amount_kzt=amt,
            purpose=f"Оплата годовой закупки оборудования по договору, счёт № {inv_no}",
        )

    # 4. legit_account_change_confirmed (20): 12 history-confirmed + 8 director-trusted
    for _ in range(12):
        amt = _round_kzt(switched_sup["median"] * rng.uniform(0.88, 1.16))
        add_case(
            label="legit",
            kind="legit_account_change_confirmed",
            recipient_name=switched_sup["name"],
            recipient_bin=switched_sup["bin"],
            recipient_iik=switched_sup["iik"],
            recipient_bik=switched_sup["bik"],
            amount_kzt=amt,
            purpose=f"Оплата аренды техники по доп. соглашению № 2, счёт № {inv_no}",
            trusted=False,
        )
    other_sups = [s for s in suppliers if s["bin"] != switched_sup["bin"]]
    for i in range(8):
        sup = other_sups[i % len(other_sups)]
        new_code = rng.choice([c for c in non_bcc_codes if c != sup["bank_code"]])
        new_iik = fresh_iik(new_code)
        amt = _round_kzt(sup["median"] * rng.uniform(0.90, 1.12))
        add_case(
            label="legit",
            kind="legit_account_change_confirmed",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=new_iik,
            recipient_bik=bik_by_code[new_code],
            amount_kzt=amt,
            purpose=f"Оплата по подтверждённому счёту № {inv_no}",
            trusted=True,
        )

    # 5. legit_account_change_unconfirmed (15): genuine first-time unconfirmed account change
    for i in range(15):
        sup = other_sups[i % len(other_sups)]
        if i % 3 == 0:
            new_code = (
                sup["bank_code"] if sup["bank_code"] != BCC_BANK_CODE else rng.choice(non_bcc_codes)
            )
        else:
            new_code = rng.choice([c for c in non_bcc_codes if c != sup["bank_code"]])
        new_iik = fresh_iik(new_code)
        amt = _round_kzt(sup["median"] * rng.uniform(0.90, 1.15))
        add_case(
            label="legit",
            kind="legit_account_change_unconfirmed",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=new_iik,
            recipient_bik=bik_by_code[new_code],
            amount_kzt=amt,
            purpose=f"Оплата по доп. соглашению к договору, счёт № {inv_no}",
        )

    # 6. legit_new_supplier (30): standard + brand/numeric names + large 1st + IEs + startups
    for i in range(10):
        name = _NEW_LEGIT_CORP_NAMES[i]
        assert _is_distinct_from_history(name, hist_names), f"Name too close: {name}"
        code = rng.choice(non_bcc_codes)
        add_case(
            label="legit",
            kind="legit_new_supplier",
            recipient_name=name,
            recipient_bin=fresh_bin(),
            recipient_iik=fresh_iik(code),
            recipient_bik=bik_by_code[code],
            amount_kzt=_round_kzt(rng.uniform(120_000, 1_800_000)),
            purpose=f"Оплата по договору поставки № {inv_no}",
        )
    # 5 legitimate brand compounds & numeric names (must NOT trigger mixed_script)
    for name in _NEW_LEGIT_BRAND_NUMERIC_NAMES:
        assert _is_distinct_from_history(name, hist_names), f"Name too close: {name}"
        code = rng.choice(non_bcc_codes)
        add_case(
            label="legit",
            kind="legit_new_supplier",
            recipient_name=name,
            recipient_bin=fresh_bin(),
            recipient_iik=fresh_iik(code),
            recipient_bik=bik_by_code[code],
            amount_kzt=_round_kzt(rng.uniform(150_000, 1_500_000)),
            purpose=f"Оплата по договору поставки № {inv_no}",
        )
    # 5 large first-time payments above client p90 (below 3x -> stays grey)
    for i in range(5):
        name = _NEW_LEGIT_CORP_NAMES[20 + i]
        assert _is_distinct_from_history(name, hist_names), f"Name too close: {name}"
        code = rng.choice(non_bcc_codes)
        add_case(
            label="legit",
            kind="legit_new_supplier",
            recipient_name=name,
            recipient_bin=fresh_bin(),
            recipient_iik=fresh_iik(code),
            recipient_bik=bik_by_code[code],
            amount_kzt=_round_kzt(client_p90 * rng.uniform(1.15, 1.65)),
            purpose=f"Аванс за поставку спецтехники по договору № {inv_no}",
        )
    # 5 new IE suppliers paid by IIN + 2 joint-venture IE (ИП(С)) with BIN 5th digit 6
    for i in range(7):
        name = _NEW_LEGIT_IE_NAMES[i]
        assert _is_distinct_from_history(name, hist_names), f"Name too close: {name}"
        code = rng.choice(non_bcc_codes)
        rec_id = fresh_iin() if i < 5 else fresh_bin(entity_digit=6)
        add_case(
            label="legit",
            kind="legit_new_supplier",
            recipient_name=name,
            recipient_bin=rec_id,
            recipient_iik=fresh_iik(code),
            recipient_bik=bik_by_code[code],
            amount_kzt=_round_kzt(rng.uniform(90_000, 450_000)),
            purpose=f"Оплата подрядных работ по акту № {inv_no}",
        )
    # 3 newly registered legitimate startups (young BIN + non-urgent/urgent wording)
    for i in range(3):
        name = _NEW_LEGIT_CORP_NAMES[25 + i]
        assert _is_distinct_from_history(name, hist_names), f"Name too close: {name}"
        code = rng.choice(non_bcc_codes)
        purpose = (
            f"Досрочно оплата аренды склада по счёту № {inv_no}"
            if i == 0
            else f"Оплата по счёту № {inv_no}, несрочно"
            if i == 1
            else f"Оплата первой партии комплектующих по счёту № {inv_no}, срочно"
        )
        add_case(
            label="legit",
            kind="legit_new_supplier",
            recipient_name=name,
            recipient_bin=fresh_young_bin(),
            recipient_iik=fresh_iik(code),
            recipient_bik=bik_by_code[code],
            amount_kzt=_round_kzt(rng.uniform(180_000, 750_000)),
            purpose=purpose,
        )

    # 7. legit_rebrand_same_account (15): supplier renamed while keeping exact known (BIN, IIK)
    rebrand_pool = [
        (sup, new_name) for sup in suppliers for new_name in _REBRAND_NAMES.get(sup["name"], ())
    ]
    for i in range(15):
        sup, new_name = rebrand_pool[i % len(rebrand_pool)]
        amt = _round_kzt(sup["median"] * rng.uniform(0.90, 1.12))
        add_case(
            label="legit",
            kind="legit_rebrand_same_account",
            recipient_name=new_name,
            recipient_bin=sup["bin"],
            recipient_iik=sup["iik"],
            recipient_bik=sup["bik"],
            amount_kzt=amt,
            purpose=f"Оплата по договору (после переименования компании), счёт № {inv_no}",
        )

    # 8. legit_urgent_known_supplier (15): known (BIN, IIK), normal amount, urgent note in purpose
    for i in range(15):
        sup = suppliers[i % len(suppliers)]
        amt = _round_kzt(sup["median"] * rng.uniform(0.88, 1.14))
        urgent = rng.choice(("срочно", "жедел", "шұғыл"))
        add_case(
            label="legit",
            kind="legit_urgent_known_supplier",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=sup["iik"],
            recipient_bik=sup["bik"],
            amount_kzt=amt,
            purpose=f"Оплата по счёту № {inv_no} ({urgent}, поставка на объект)",
        )

    # 9. legit_budget_payment (15): treasury KKMFKZ2A (070) & Gov4Citizens GCVPKZ2A (009)
    budget_codes = ["070", "009"]
    for i in range(15):
        b_code = budget_codes[i % len(budget_codes)]
        add_case(
            label="legit",
            kind="legit_budget_payment",
            recipient_name=_BUDGET_RECIPIENT_NAMES[i % len(_BUDGET_RECIPIENT_NAMES)],
            recipient_bin=fresh_bin(year_range=(10, 22)),
            recipient_iik=fresh_iik(b_code),
            recipient_bik=bik_by_code[b_code],
            amount_kzt=_round_kzt(rng.uniform(250_000, 6_500_000)),
            purpose=f"Налоговый платёж / соцотчисления за период, документ № {inv_no}",
            knp="911" if b_code == "070" else "010",
        )

    # 10. legit_popular_known_supplier (10): large bank-known suppliers receiving many first
    # payments on new branch IIKs — MUST NOT be flagged thanks to bank_known_bin exemption.
    assert len(popular_branch_pairs) >= 10, (
        f"Expected >= 10 popular bank_known_bin branch pairs, got {len(popular_branch_pairs)}"
    )
    for kbin, prov_name, branch_iik, branch_bik in popular_branch_pairs[:10]:
        assert _is_distinct_from_history(prov_name, hist_names), f"Popular name too close: {prov_name}"
        add_case(
            label="legit",
            kind="legit_popular_known_supplier",
            recipient_name=prov_name,
            recipient_bin=kbin,
            recipient_iik=branch_iik,
            recipient_bik=branch_bik,
            amount_kzt=_round_kzt(rng.uniform(110_000, 950_000)),
            purpose=f"Оплата коммунальных и телекоммуникационных услуг по счёту № {inv_no}",
        )

    # 11. legit_new_supplier_generic_word (20): new legitimate suppliers sharing generic words
    # (Сервис, Снаб, Групп, Трейд, Софт, Монтаж, Service) or IE surnames with different initials.
    assert len(_NEW_LEGIT_GENERIC_WORD_SPECS) == 20
    for name, id_kind in _NEW_LEGIT_GENERIC_WORD_SPECS:
        code = rng.choice(non_bcc_codes)
        rec_id = fresh_iin() if id_kind == "iin" else fresh_bin()
        amt = _round_kzt(rng.uniform(280_000, 1_450_000))
        add_case(
            label="legit",
            kind="legit_new_supplier_generic_word",
            recipient_name=name,
            recipient_bin=rec_id,
            recipient_iik=fresh_iik(code),
            recipient_bik=bik_by_code[code],
            amount_kzt=amt,
            purpose=f"Оплата услуг и поставки по договору, счёт № {inv_no}",
        )

    # =========================================================================
    # ATTACK CASES (200 total)
    # =========================================================================

    # 1. attack_iik_swap_same_bin (20): known supplier BIN + swapped attacker IIK
    for i in range(20):
        sup = suppliers[i % len(suppliers)]
        same_bank = i >= 12
        if same_bank and sup["bank_code"] != BCC_BANK_CODE:
            atk_code = sup["bank_code"]
        else:
            atk_code = rng.choice([c for c in non_bcc_codes if c != sup["bank_code"]])
        atk_iik = fresh_iik(atk_code)
        amt = _round_kzt(sup["median"] * rng.uniform(0.92, 1.25))
        purpose = (
            f"Оплата по счёту № {inv_no}, {rng.choice(_URGENT_TAIL)}"
            if i % 2 == 0
            else f"Оплата по договору поставки, счёт № {inv_no}"
        )
        add_case(
            label="attack",
            kind="attack_iik_swap_same_bin",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=atk_iik,
            recipient_bik=bik_by_code[atk_code],
            amount_kzt=amt,
            purpose=purpose,
        )

    # 2. attack_lookalike_name (20): homoglyphs, token_set, typo, variants/translit, K2, hard
    lookalike_styles = (
        ["latin"] * 2
        + ["kazakh"] * 2
        + ["greek"] * 2
        + ["token_set"] * 2
        + ["typo"] * 2
        + ["variant_translit"] * 4
        + ["k2_variant"] * 4
        + ["hard_evasion"] * 2
    )
    registry_other_bins = [
        b
        for b in sorted(registry)
        if b not in hist_bins
        and b != client_bin
        and b not in known_bins_map
        and bin_kind(b) == "bin"
    ]
    sup_by_name = {s["name"]: s for s in suppliers}
    vt_idx = 0
    k2_idx = 0
    for i, style in enumerate(lookalike_styles):
        if style == "variant_translit":
            orig_name, spoofed_name = _VARIANT_TRANSLIT_MAP[vt_idx % len(_VARIANT_TRANSLIT_MAP)]
            vt_idx += 1
            sup = sup_by_name[orig_name]
        elif style == "k2_variant":
            orig_name, spoofed_name = _K2_LOOKALIKE_VARIANTS[k2_idx % len(_K2_LOOKALIKE_VARIANTS)]
            k2_idx += 1
            sup = sup_by_name[orig_name]
        else:
            sup = corp_suppliers[i % len(corp_suppliers)]
            if style == "hard_evasion":
                sup = corp_suppliers[i % 2]
            spoofed_name = _make_lookalike_name(rng, sup["name"], style)
        if i % 3 == 0:
            atk_bin = registry_other_bins[i % len(registry_other_bins)]
        elif i % 3 == 1:
            atk_bin = fresh_young_bin()
        else:
            atk_bin = fresh_bin()
        atk_code = rng.choice(non_bcc_codes)
        amt = _round_kzt(sup["median"] * rng.uniform(0.95, 1.22))
        add_case(
            label="attack",
            kind="attack_lookalike_name",
            recipient_name=spoofed_name,
            recipient_bin=atk_bin,
            recipient_iik=fresh_iik(atk_code),
            recipient_bik=bik_by_code[atk_code],
            amount_kzt=amt,
            purpose=f"Оплата за поставку по договору, счёт № {inv_no}",
        )

    # 3. attack_unicode_and_digit_evasion (15): IPA, Cherokee, invisibles, digits-for-letters + 2 hard
    for i, (orig_name, evaded_name) in enumerate(_UNICODE_EVASION_CASES):
        sup = sup_by_name[orig_name]
        atk_code = rng.choice(non_bcc_codes)
        atk_bin = fresh_young_bin() if i % 2 == 0 else fresh_bin()
        add_case(
            label="attack",
            kind="attack_unicode_and_digit_evasion",
            recipient_name=evaded_name,
            recipient_bin=atk_bin,
            recipient_iik=fresh_iik(atk_code),
            recipient_bik=bik_by_code[atk_code],
            amount_kzt=_round_kzt(sup["median"] * rng.uniform(0.90, 1.15)),
            purpose=f"Оплата за материалы по счёту № {inv_no}",
        )

    # 4. attack_bcc_other_owner (15): BCC IIK owned by another company in bcc_accounts.json
    for i in range(15):
        bcc_iik, bcc_info = other_bcc_entries[i % len(other_bcc_entries)]
        owner_bin = bcc_info["owner_bin"]
        if i < 9:
            sup = next(
                s for s in suppliers[i % len(suppliers) :] + suppliers if s["bin"] != owner_bin
            )
            rec_name = sup["name"]
            rec_bin = sup["bin"]
            amt = _round_kzt(sup["median"] * rng.uniform(0.95, 1.25))
        else:
            rec_name = _DROP_SHELL_NAMES[i % len(_DROP_SHELL_NAMES)]
            rec_bin = fresh_bin()
            amt = _round_kzt(rng.uniform(400_000, 2_200_000))
        add_case(
            label="attack",
            kind="attack_bcc_other_owner",
            recipient_name=rec_name,
            recipient_bin=rec_bin,
            recipient_iik=bcc_iik,
            recipient_bik=BCC_BIK,
            amount_kzt=amt,
            purpose=f"Оплата по счёту № {inv_no}",
        )

    # 5. attack_iin_dropper (20): 10 with OPF + 6 with KBe=17 without OPF + 4 blind-spot droppers
    for i in range(10):
        code = rng.choice(non_bcc_codes)
        if i < 5:
            sup = corp_suppliers[i % len(corp_suppliers)]
            name = sup["name"]
            amt = _round_kzt(sup["median"] * rng.uniform(0.90, 1.25))
        else:
            name = _DROPPER_CORP_NAMES[(i - 5) % len(_DROPPER_CORP_NAMES)]
            amt = _round_kzt(rng.uniform(350_000, 1_900_000))
        add_case(
            label="attack",
            kind="attack_iin_dropper",
            recipient_name=name,
            recipient_bin=fresh_iin(),
            recipient_iik=fresh_iik(code),
            recipient_bik=bik_by_code[code],
            amount_kzt=amt,
            purpose=f"Оплата по счёту № {inv_no}",
        )
    # 6 droppers omitting OPF prefix but submitting corporate KBe=17
    for name in _DROPPER_KBE_ONLY_NAMES:
        code = rng.choice(non_bcc_codes)
        add_case(
            label="attack",
            kind="attack_iin_dropper",
            recipient_name=name,
            recipient_bin=fresh_iin(),
            recipient_iik=fresh_iik(code),
            recipient_bik=bik_by_code[code],
            amount_kzt=_round_kzt(rng.uniform(450_000, 1_800_000)),
            purpose=f"Оплата по счёту № {inv_no}",
            kbe="17",
        )
    # 4 blind-spot droppers: omit both OPF and KBe while using an individual IIN
    for i in range(4):
        code = rng.choice(non_bcc_codes)
        name = _DROPPER_NO_LEGAL_FORM_NAMES[i]
        assert _is_distinct_from_history(name, hist_names)
        add_case(
            label="attack",
            kind="attack_iin_dropper",
            recipient_name=name,
            recipient_bin=fresh_iin(),
            recipient_iik=fresh_iik(code),
            recipient_bik=bik_by_code[code],
            amount_kzt=_round_kzt(rng.uniform(450_000, 1_600_000)),
            purpose=f"Оплата строительных материалов по счёту № {inv_no}",
        )

    # 6. attack_amount_inflation (20): 14 heavy (>3x) + 6 stealth moderate (1.75x..2.25x)
    for i in range(14):
        sup = suppliers[i % len(suppliers)]
        factor = rng.uniform(3.25, 5.20)
        amt = _round_kzt(max(sup["median"] * factor, sup["median"] + 6.0 * max(sup["mad"], 1.0)))
        add_case(
            label="attack",
            kind="attack_amount_inflation",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=sup["iik"],
            recipient_bik=sup["bik"],
            amount_kzt=amt,
            purpose=f"Оплата по счёту № {inv_no} за расширенный объём поставки",
        )
    for i in range(6):
        sup = seasonal_sups[i % len(seasonal_sups)] if i < 4 else steady_sups[i % len(steady_sups)]
        factor = rng.uniform(1.75, 2.25)
        amt = _round_kzt(sup["median"] * factor)
        add_case(
            label="attack",
            kind="attack_amount_inflation",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=sup["iik"],
            recipient_bik=sup["bik"],
            amount_kzt=amt,
            purpose=f"Оплата по скорректированному счёту № {inv_no}",
        )

    # 7. attack_iik_reused_other_supplier (15): different BIN reusing another supplier's history IIK
    for i in range(15):
        victim = non_bcc_hist_suppliers[i % len(non_bcc_hist_suppliers)]
        fake_name = _DROP_SHELL_NAMES[i % len(_DROP_SHELL_NAMES)]
        assert _is_distinct_from_history(fake_name, hist_names)
        add_case(
            label="attack",
            kind="attack_iik_reused_other_supplier",
            recipient_name=fake_name,
            recipient_bin=fresh_bin() if i % 2 == 0 else fresh_young_bin(),
            recipient_iik=victim["iik"],
            recipient_bik=victim["bik"],
            amount_kzt=_round_kzt(rng.uniform(300_000, 1_800_000)),
            purpose=f"Оплата по договору субподряда № {inv_no}",
        )

    # 8. attack_duplicate_invoice (10): 8 within 90d from history + 2 blind spots (> 90d ago)
    for i in range(10):
        sup = suppliers[i % len(suppliers)]
        dup_purpose = sup["purpose_sample"] if i < 8 else sup["oldest_purpose"]
        add_case(
            label="attack",
            kind="attack_duplicate_invoice",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=sup["iik"],
            recipient_bik=sup["bik"],
            amount_kzt=_round_kzt(sup["median"] * rng.uniform(0.95, 1.05)),
            purpose=dup_purpose,
        )

    # 9. attack_structuring_72h (10): 5 large splits (>=3x med -> yellow), 3x40% (amp), 2x40% (stealth)
    for i in range(10):
        sup = steady_sups[i % len(steady_sups)]
        if i < 5:
            chunk_amt = _round_kzt(sup["median"] * 1.1)
            n_prior = 2
        elif i < 8:
            chunk_amt = _round_kzt(sup["median"] * 0.4)
            n_prior = 2
        else:
            chunk_amt = _round_kzt(sup["median"] * 0.4)
            n_prior = 1
        priors = [
            {
                "hours_ago": 10 + 12 * k,
                "request": {
                    "payer_id": payer_id,
                    "recipient_name": sup["name"],
                    "recipient_bin": sup["bin"],
                    "recipient_iik": sup["iik"],
                    "recipient_bik": sup["bik"],
                    "amount_kzt": chunk_amt,
                    "purpose": f"Частичная оплата по счёту № {inv_no + 1000 + k}",
                },
            }
            for k in range(n_prior)
        ]
        add_case(
            label="attack",
            kind="attack_structuring_72h",
            recipient_name=sup["name"],
            recipient_bin=sup["bin"],
            recipient_iik=sup["iik"],
            recipient_bik=sup["bik"],
            amount_kzt=chunk_amt,
            purpose=f"Частичная оплата по счёту № {inv_no}",
            prior_checks=priors,
        )

    # 10. attack_typo_free_valid_drop (20): 15 external shells (6 hit bank-wide signals, 5 urgent,
    # 4 genuinely unseen first-victim blind spots) + 5 new BCC shells.
    typo_free_bankwide_iiks = [
        ext_complaints_1_2[0],
        ext_complaints_3plus[0],
        ext_watchlist_iiks[0],
        ext_watchlist_iiks[1],
        ext_fresh_3_4[0],
        ext_fresh_5plus[0],
    ]
    non_urgent_indices = [i for i in range(15) if i % 3 != 0]
    bankwide_override_by_idx = dict(zip(non_urgent_indices[:6], typo_free_bankwide_iiks, strict=True))
    for i in range(15):
        name = _DROP_SHELL_NAMES[i]
        assert _is_distinct_from_history(name, hist_names), f"Drop name too close: {name}"
        use_young = i < 9
        use_urgent = i % 3 == 0
        use_high_amt = i % 4 == 0
        amt = (
            _round_kzt(client_p90 * rng.uniform(1.10, 1.55))
            if use_high_amt
            else _round_kzt(rng.uniform(350_000, 1_900_000))
        )
        purpose = (
            f"Оплата по договору № {inv_no}, {rng.choice(_URGENT_TAIL)}"
            if use_urgent
            else f"Оплата по договору поставки № {inv_no}"
        )
        if i in bankwide_override_by_idx:
            drop_iik = bankwide_override_by_idx[i]
            drop_code = drop_iik[4:7]
        else:
            drop_code = rng.choice(non_bcc_codes)
            drop_iik = fresh_iik(drop_code)
        add_case(
            label="attack",
            kind="attack_typo_free_valid_drop",
            recipient_name=name,
            recipient_bin=fresh_young_bin() if use_young else fresh_bin(),
            recipient_iik=drop_iik,
            recipient_bik=bik_by_code[drop_code],
            amount_kzt=amt,
            purpose=purpose,
        )
    for i in range(5):
        bcc_iik, bcc_info = new_bcc_non_hist_entries[i % len(new_bcc_non_hist_entries)]
        add_case(
            label="attack",
            kind="attack_typo_free_valid_drop",
            recipient_name=bcc_info["owner_name"],
            recipient_bin=bcc_info["owner_bin"],
            recipient_iik=bcc_iik,
            recipient_bik=BCC_BIK,
            amount_kzt=_round_kzt(rng.uniform(800_000, 2_400_000)),
            purpose=f"Оплата по договору поставки № {inv_no}",
        )

    # 11. attack_combined_bec (15): realistic multi-signal BEC attacks
    for i in range(15):
        sup = corp_suppliers[i % len(corp_suppliers)]
        style = ("latin", "kazakh", "token_set", "greek", "typo")[i % 5]
        spoofed_name = _make_lookalike_name(rng, sup["name"], style)
        if i % 3 == 0:
            bcc_iik, bcc_info = other_bcc_entries[i % len(other_bcc_entries)]
            atk_bin = registry_other_bins[i % len(registry_other_bins)]
            if atk_bin == bcc_info["owner_bin"]:
                atk_bin = fresh_young_bin()
            atk_iik = bcc_iik
            atk_bik = BCC_BIK
        else:
            atk_code = rng.choice(non_bcc_codes)
            atk_bin = (
                fresh_young_bin()
                if i % 2 == 0
                else registry_other_bins[i % len(registry_other_bins)]
            )
            atk_iik = fresh_iik(atk_code)
            atk_bik = bik_by_code[atk_code]
        amt = _round_kzt(sup["median"] * rng.uniform(3.1, 4.4))
        add_case(
            label="attack",
            kind="attack_combined_bec",
            recipient_name=spoofed_name,
            recipient_bin=atk_bin,
            recipient_iik=atk_iik,
            recipient_bik=atk_bik,
            amount_kzt=amt,
            purpose=f"Оплата по договору, счёт № {inv_no}, {rng.choice(_URGENT_TAIL)}",
        )

    # 12. attack_bankwide_external_drop (20): clean typo-free external-bank droppers caught
    # solely by BCC bank-wide signals (+ 2 honest below-threshold fresh-inflow blind spots).
    bankwide_attack_iiks: list[str] = (
        ext_complaints_1_2[:3]
        + ext_complaints_3plus[:3]
        + ext_watchlist_iiks[:5]
        + ext_fresh_3_4[:3]
        + ext_fresh_5plus[:3]
        + ext_combined_comp_fresh[:1]
        + ext_fresh_below[:2]
    )
    assert len(bankwide_attack_iiks) == 20, f"Expected 20 bankwide attack IIKs, got {len(bankwide_attack_iiks)}"
    for i, atk_iik in enumerate(bankwide_attack_iiks):
        name = _DROP_SHELL_NAMES[i % len(_DROP_SHELL_NAMES)]
        assert _is_distinct_from_history(name, hist_names), f"Drop name too close: {name}"
        atk_code = atk_iik[4:7]
        add_case(
            label="attack",
            kind="attack_bankwide_external_drop",
            recipient_name=name,
            recipient_bin=fresh_bin(),
            recipient_iik=atk_iik,
            recipient_bik=bik_by_code[atk_code],
            amount_kzt=_round_kzt(rng.uniform(420_000, 1_850_000)),
            purpose=f"Оплата за поставку строительного оборудования по счёту № {inv_no}",
        )

    assert len(cases) == 400, f"Expected 400 cases, got {len(cases)}"
    assert sum(1 for c in cases if c["label"] == "legit") == 200
    assert sum(1 for c in cases if c["label"] == "attack") == 200

    payload = {
        "seed": SEED,
        "payer_id": payer_id,
        "total_cases": len(cases),
        "cases": cases,
    }
    target = output_path or (base_dir / OUTPUT_FILENAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_dump_eval_json(payload), encoding="utf-8")
    return target


def main() -> None:
    path = generate_eval_set()
    print(f"Wrote eval_set: {path}")


if __name__ == "__main__":
    main()
