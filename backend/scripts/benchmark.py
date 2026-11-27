"""Performance benchmark for the payment risk engine, profile builder, and 1C importer.

Run from ./backend as:
    uv run python scripts/benchmark.py

Does not write to the production SQLite database or var/ directory; reads the demo
JSON store in memory and writes only data/samples/benchmark_1c_500.txt.
"""

from __future__ import annotations

import math
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        _reconfigure(encoding="utf-8")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.prod.importers.onec import parse_1c
from app.risk.config import BCC_BANK_CODE, DEMO_TODAY
from app.risk.engine import check_payment
from app.risk.profiles import build_profiles
from app.schemas import CheckRequest
from app.store import Store
from app.validators.kz import (
    bik_matches_iik,
    bik_ok,
    bin_iin_checksum_ok,
    bin_kind,
    iik_check,
)
from scripts.generate_data import generate_bin, generate_iik, generate_iin

BENCHMARK_SEED: int = 2026
QUEUE_RUNS: int = 100
PROFILE_RUNS: int = 100
ONEC_PAYMENT_COUNT: int = 500
ONEC_SAMPLE_PATH: Path = BACKEND_ROOT / "data" / "samples" / "benchmark_1c_500.txt"

_NEW_BRAND_ROOTS: tuple[str, ...] = (
    "Каспий",
    "Алтай",
    "Иртыш",
    "Тараз",
    "Сарыарка",
    "Байконур",
    "Жетысу",
    "Тулпар",
    "Беркут",
    "Арман",
    "Болашак",
    "Дала",
    "Орда",
    "Самрук",
    "Медеу",
    "Шымбулак",
    "Аксай",
    "Коктем",
    "Керуен",
    "Сункар",
)
_NEW_BUSINESS_SUFFIXES: tuple[str, ...] = (
    "Строй",
    "Снаб",
    "Логистик",
    "Техно",
    "Металл",
    "Сервис",
    "Инжиниринг",
    "Энерго",
    "Комплект",
    "Трейд",
)
_IE_SURNAMES: tuple[str, ...] = (
    "Ахметов",
    "Сериков",
    "Омаров",
    "Сулейменов",
    "Нургалиев",
    "Касымов",
    "Жумабаев",
    "Есенов",
    "Искаков",
    "Муратов",
)
_IE_INITIALS: tuple[str, ...] = (
    "А.С.",
    "Б.К.",
    "Е.Т.",
    "Д.М.",
    "Н.А.",
    "Р.Е.",
    "Т.Б.",
    "М.Ж.",
)
_PURPOSE_TEMPLATES: tuple[str, ...] = (
    "Оплата по счету № {inv} за строительные материалы по договору № {ctr}-А",
    "Оплата транспортно-экспедиционных услуг по счету № {inv}",
    "Аванс 30% за поставку оборудования по договору № {ctr}-П, счет № {inv}",
    "Оплата аренды спецтехники по акту № {inv}",
    "Оплата за комплектующие и расходные материалы по счету № {inv}",
)


def _percentile(sorted_values: list[float], pct: float) -> float:
    pos = pct * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def _build_queue_requests(store: Store) -> list[CheckRequest]:
    requests: list[CheckRequest] = []
    for raw in store.queue:
        requests.append(
            CheckRequest(
                payer_id=raw.get("payer_id"),
                recipient_name=raw["recipient_name"],
                recipient_bin=raw["recipient_bin"],
                recipient_iik=raw["recipient_iik"],
                recipient_bik=raw["recipient_bik"],
                amount_kzt=raw["amount_kzt"],
                purpose=raw.get("purpose", ""),
                kbe=raw.get("kbe", ""),
                knp=raw.get("knp", ""),
            )
        )
    return requests


def _extract_known_suppliers(store: Store) -> list[dict[str, Any]]:
    history = store.get_client_history(store.default_payer_id)
    by_bin: dict[str, list[dict[str, Any]]] = {}
    for p in history:
        by_bin.setdefault(p["recipient_bin"], []).append(p)

    suppliers: list[dict[str, Any]] = []
    for sup_bin, items in by_bin.items():
        last = items[-1]
        median_amt = float(statistics.median(float(p["amount_kzt"]) for p in items))
        is_ie = bin_kind(sup_bin) == "iin"
        suppliers.append(
            {
                "name": str(last["recipient_name"]),
                "bin": sup_bin,
                "iik": str(last["recipient_iik"]),
                "bik": str(last["recipient_bik"]),
                "knp": str(last.get("knp") or "710"),
                "kbe": "19" if is_ie else "17",
                "median_amount": median_amt,
            }
        )
    return suppliers


def _generate_new_suppliers(
    rng: random.Random,
    store: Store,
    *,
    count: int = 60,
    used_bins: set[str],
    used_iiks: set[str],
) -> list[dict[str, Any]]:
    """Generate deterministic synthetic new suppliers with valid KZ BIN/IIN, IIK, and BIK."""
    eligible_banks = [
        b for b in store.banks if b["code"] != BCC_BANK_CODE and not b.get("budget", False)
    ]
    new_suppliers: list[dict[str, Any]] = []

    for idx in range(count):
        bank = eligible_banks[idx % len(eligible_banks)]
        is_ie = idx % 4 == 3
        while True:
            if is_ie:
                sup_bin = generate_iin(rng, year=rng.randint(75, 96))
            else:
                sup_bin = generate_bin(rng, year=rng.randint(12, 24), entity_digit=4)
            if sup_bin not in used_bins:
                used_bins.add(sup_bin)
                break

        while True:
            sup_iik = generate_iik(rng, bank["code"], prefix="000", banks_path=store.banks_path)
            if sup_iik not in used_iiks:
                used_iiks.add(sup_iik)
                break

        if is_ie:
            surname = _IE_SURNAMES[idx % len(_IE_SURNAMES)]
            initials = _IE_INITIALS[(idx // len(_IE_SURNAMES)) % len(_IE_INITIALS)]
            name = f"ИП {surname} {initials}"
            kbe = "19"
            knp = "859"
            base_amt = float(rng.randrange(120_000, 650_000, 10_000))
        else:
            root = _NEW_BRAND_ROOTS[idx % len(_NEW_BRAND_ROOTS)]
            suffix = _NEW_BUSINESS_SUFFIXES[
                (idx // len(_NEW_BRAND_ROOTS) + idx) % len(_NEW_BUSINESS_SUFFIXES)
            ]
            name = f"ТОО «{root} {suffix}»"
            kbe = "17"
            knp = "710" if idx % 3 != 0 else "859"
            base_amt = float(rng.randrange(250_000, 2_400_000, 25_000))

        new_suppliers.append(
            {
                "name": name,
                "bin": sup_bin,
                "iik": sup_iik,
                "bik": bank["bik"],
                "knp": knp,
                "kbe": kbe,
                "median_amount": base_amt,
            }
        )

    return new_suppliers


def generate_benchmark_1c_file(
    store: Store,
    output_path: Path = ONEC_SAMPLE_PATH,
    *,
    count: int = ONEC_PAYMENT_COUNT,
    seed: int = BENCHMARK_SEED,
) -> Path:
    """Generate a deterministic cp1251 1CClientBankExchange file with valid KZ requisites."""
    rng = random.Random(seed)
    known = _extract_known_suppliers(store)
    used_bins = {s["bin"] for s in known}
    used_iiks = {s["iik"] for s in known}
    new_suppliers = _generate_new_suppliers(
        rng,
        store,
        count=60,
        used_bins=used_bins,
        used_iiks=used_iiks,
    )
    alt_banks = [
        b for b in store.banks if b["code"] != BCC_BANK_CODE and not b.get("budget", False)
    ]

    payer_iik = str(store.client["iik"])
    doc_date = DEMO_TODAY.strftime("%d.%m.%Y")

    lines: list[str] = [
        "1CClientBankExchange",
        "ВерсияФормата=1.03",
        "Кодировка=Windows",
        "Отправитель=1С:Бухгалтерия для Казахстана",
        "Получатель=BCC Business",
        f"ДатаСоздания={doc_date}",
        "ВремяСоздания=10:00:00",
        f"ДатаНачала={doc_date}",
        f"ДатаКонца={doc_date}",
        f"РасчСчет={payer_iik}",
        "СекцияРасчСчет",
        f"ДатаНачала={doc_date}",
        f"ДатаКонца={doc_date}",
        f"РасчСчет={payer_iik}",
        "КонецРасчСчет",
    ]

    for idx in range(count):
        doc_no = 5001 + idx
        use_known = rng.random() < 0.65
        supplier = rng.choice(known) if use_known else rng.choice(new_suppliers)

        rec_name = supplier["name"]
        rec_bin = supplier["bin"]
        rec_iik = supplier["iik"]
        rec_bik = supplier["bik"]
        rec_kbe = supplier["kbe"]
        rec_knp = supplier["knp"]

        # Apply occasional realistic perturbations on known suppliers (amount spike or new bank)
        factor = rng.uniform(0.85, 1.15)
        if use_known and idx % 29 == 0:
            alt_bank = rng.choice([b for b in alt_banks if b["bik"] != rec_bik])
            rec_iik = generate_iik(rng, alt_bank["code"], prefix="000", banks_path=store.banks_path)
            rec_bik = alt_bank["bik"]
        elif use_known and idx % 37 == 0:
            factor = 3.4

        amount = round(supplier["median_amount"] * factor, -2)
        if amount <= 0:
            amount = 100_000.0

        # Validate every generated requisite against the repo's KZ validators
        assert bin_iin_checksum_ok(rec_bin) and bin_kind(rec_bin) is not None, rec_bin
        iik_valid, iik_err, _ = iik_check(rec_iik, check_bank_code=True, banks_path=store.banks_path)
        assert iik_valid, f"Invalid IIK {rec_iik}: {iik_err}"
        assert bik_ok(rec_bik, path=store.banks_path), rec_bik
        assert bik_matches_iik(rec_bik, rec_iik, path=store.banks_path), (rec_bik, rec_iik)

        purpose_tpl = _PURPOSE_TEMPLATES[idx % len(_PURPOSE_TEMPLATES)]
        purpose = purpose_tpl.format(inv=doc_no, ctr=10 + (idx % 90))

        lines.extend(
            [
                "СекцияДокумент=Платежное поручение",
                f"Номер={doc_no}",
                f"Дата={doc_date}",
                f"Сумма={amount:.2f}",
                f"ПлательщикИИК={payer_iik}",
                f"Получатель={rec_name}",
                f"ПолучательБИН_ИИН={rec_bin}",
                f"ПолучательИИК={rec_iik}",
                f"ПолучательБИК={rec_bik}",
                f"ПолучательКБЕ={rec_kbe}",
                f"КодНазначенияПлатежа={rec_knp}",
                f"НазначениеПлатежа={purpose}",
                "КонецДокумента",
            ]
        )

    lines.append("КонецФайла")
    payload = ("\r\n".join(lines) + "\r\n").encode("cp1251")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return output_path


def benchmark_queue(
    store: Store,
    *,
    runs: int = QUEUE_RUNS,
) -> dict[str, Any]:
    """Time check_payment over the 10 demo queue items x runs using the current engine."""
    requests = _build_queue_requests(store)
    for req in requests:
        check_payment(req, store, include_recent_memory=False, record_in_memory=False)

    per_item_ms: list[float] = []
    per_run_ms: list[float] = []
    t_total_start = time.perf_counter()
    for _ in range(runs):
        t_run_start = time.perf_counter()
        for req in requests:
            t0 = time.perf_counter()
            check_payment(req, store, include_recent_memory=False, record_in_memory=False)
            per_item_ms.append((time.perf_counter() - t0) * 1000.0)
        per_run_ms.append((time.perf_counter() - t_run_start) * 1000.0)
    total_ms = (time.perf_counter() - t_total_start) * 1000.0

    per_item_ms.sort()
    per_run_ms.sort()
    return {
        "items": len(requests),
        "runs": runs,
        "calls": len(per_item_ms),
        "total_ms": total_ms,
        "item_p50_ms": _percentile(per_item_ms, 0.50),
        "item_p95_ms": _percentile(per_item_ms, 0.95),
        "run_p50_ms": _percentile(per_run_ms, 0.50),
        "run_p95_ms": _percentile(per_run_ms, 0.95),
    }


def benchmark_profile_build(
    store: Store,
    *,
    runs: int = PROFILE_RUNS,
) -> dict[str, Any]:
    """Time build_profiles on the demo history over repeated runs."""
    history = store.get_client_history(store.default_payer_id)
    # Warm up helper resolution and confusables table
    sample = build_profiles(history, banks_by_bik=store.banks_by_bik)

    durations_ms: list[float] = []
    t_total_start = time.perf_counter()
    for _ in range(runs):
        t0 = time.perf_counter()
        build_profiles(history, banks_by_bik=store.banks_by_bik)
        durations_ms.append((time.perf_counter() - t0) * 1000.0)
    total_ms = (time.perf_counter() - t_total_start) * 1000.0
    durations_ms.sort()
    return {
        "history_len": len(history),
        "suppliers": len(sample.suppliers),
        "runs": runs,
        "total_ms": total_ms,
        "p50_ms": _percentile(durations_ms, 0.50),
        "p95_ms": _percentile(durations_ms, 0.95),
    }


def benchmark_onec_500(store: Store, sample_path: Path = ONEC_SAMPLE_PATH) -> dict[str, Any]:
    """Generate 500-payment 1C file, time parse_1c, and time checking every line."""
    generate_benchmark_1c_file(store, output_path=sample_path)
    raw_bytes = sample_path.read_bytes()

    t_parse_start = time.perf_counter()
    parsed = parse_1c(raw_bytes)
    parse_total_ms = (time.perf_counter() - t_parse_start) * 1000.0

    assert len(parsed.docs) == ONEC_PAYMENT_COUNT, (
        f"Expected {ONEC_PAYMENT_COUNT} parsed docs, got {len(parsed.docs)}"
    )
    assert len(parsed.errors) == 0, f"Unexpected parse errors: {parsed.errors[:3]}"

    payer_id = store.default_payer_id
    requests = [
        CheckRequest(
            payer_id=payer_id,
            recipient_name=doc.recipient_name,
            recipient_bin=doc.recipient_bin,
            recipient_iik=doc.recipient_iik,
            recipient_bik=doc.recipient_bik,
            amount_kzt=float(doc.amount_kzt or 0.0),
            purpose=doc.purpose,
            kbe=doc.kbe,
            knp=doc.knp,
        )
        for doc in parsed.docs
    ]

    verdicts: dict[str, int] = {"green": 0, "yellow": 0, "red": 0, "grey": 0, "invalid": 0}
    per_line_ms: list[float] = []
    t_check_start = time.perf_counter()
    for req in requests:
        t0 = time.perf_counter()
        result = check_payment(req, store, include_recent_memory=False, record_in_memory=False)
        per_line_ms.append((time.perf_counter() - t0) * 1000.0)
        verdicts[result.verdict] += 1
    check_total_ms = (time.perf_counter() - t_check_start) * 1000.0
    per_line_ms.sort()

    n_docs = len(parsed.docs)
    return {
        "path": str(sample_path.relative_to(BACKEND_ROOT)).replace("\\", "/"),
        "bytes": len(raw_bytes),
        "encoding": parsed.encoding,
        "docs": n_docs,
        "parse_total_ms": parse_total_ms,
        "parse_per_line_ms": parse_total_ms / n_docs,
        "check_total_ms": check_total_ms,
        "check_per_line_ms": check_total_ms / n_docs,
        "check_p50_ms": _percentile(per_line_ms, 0.50),
        "check_p95_ms": _percentile(per_line_ms, 0.95),
        "verdicts": verdicts,
    }


def _print_table(
    queue_stats: dict[str, Any],
    profile_stats: dict[str, Any],
    onec_stats: dict[str, Any],
) -> None:
    rows: list[tuple[str, str, str, str, str, str]] = [
        (
            "check_payment (queue item)",
            f"{queue_stats['items']}x{queue_stats['runs']}={queue_stats['calls']}",
            f"{queue_stats['total_ms']:.2f}",
            f"{queue_stats['total_ms'] / queue_stats['calls']:.3f}",
            f"{queue_stats['item_p50_ms']:.3f}",
            f"{queue_stats['item_p95_ms']:.3f}",
        ),
        (
            "check_payment (10-item queue)",
            f"{queue_stats['runs']} runs",
            f"{queue_stats['total_ms']:.2f}",
            f"{queue_stats['total_ms'] / queue_stats['runs']:.3f}",
            f"{queue_stats['run_p50_ms']:.3f}",
            f"{queue_stats['run_p95_ms']:.3f}",
        ),
        (
            "build_profiles (demo history)",
            f"{profile_stats['runs']} runs",
            f"{profile_stats['total_ms']:.2f}",
            f"{profile_stats['total_ms'] / profile_stats['runs']:.3f}",
            f"{profile_stats['p50_ms']:.3f}",
            f"{profile_stats['p95_ms']:.3f}",
        ),
        (
            "parse_1c (500 payments)",
            f"{onec_stats['docs']} lines",
            f"{onec_stats['parse_total_ms']:.2f}",
            f"{onec_stats['parse_per_line_ms']:.3f}",
            "-",
            "-",
        ),
        (
            "check_payment (1C 500 lines)",
            f"{onec_stats['docs']} lines",
            f"{onec_stats['check_total_ms']:.2f}",
            f"{onec_stats['check_per_line_ms']:.3f}",
            f"{onec_stats['check_p50_ms']:.3f}",
            f"{onec_stats['check_p95_ms']:.3f}",
        ),
    ]

    header = (
        f"{'Benchmark':32s} | {'Workload':12s} | {'Total (ms)':>10s} | "
        f"{'Mean (ms)':>9s} | {'p50 (ms)':>9s} | {'p95 (ms)':>9s}"
    )
    sep = "-" * len(header)
    print(header)
    print(sep)
    for name, workload, total_s, mean_s, p50_s, p95_s in rows:
        print(
            f"{name:32s} | {workload:12s} | {total_s:>10s} | "
            f"{mean_s:>9s} | {p50_s:>9s} | {p95_s:>9s}"
        )
    print(sep)
    v = onec_stats["verdicts"]
    print(
        f"Demo history: {profile_stats['history_len']} payments, "
        f"{profile_stats['suppliers']} suppliers"
    )
    print(
        f"1C sample   : {onec_stats['path']} ({onec_stats['bytes']} bytes, "
        f"encoding={onec_stats['encoding']}, docs={onec_stats['docs']})"
    )
    print(
        f"1C verdicts : green={v['green']}, yellow={v['yellow']}, red={v['red']}, "
        f"grey={v['grey']}, invalid={v['invalid']}"
    )


def main() -> None:
    store = Store()
    queue_stats = benchmark_queue(store)
    profile_stats = benchmark_profile_build(store)
    onec_stats = benchmark_onec_500(store)
    _print_table(queue_stats, profile_stats, onec_stats)


if __name__ == "__main__":
    main()
