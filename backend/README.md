# BCC Business Shield — Backend

Pre-signing verification service for SME supplier payments in Kazakhstan. Compares invoice requisites (BIN/IIN, IIK, BIK, optional KBe/KNP), supplier name, payment purpose, and amount against the client's 12-month payment history, short-term session memory, and BCC's internal account directory, returning a plain-language verdict (`green`, `yellow`, `red`, `grey`, or `invalid`) with localized explanations in Russian (`ru`), Kazakh (`kk`), and English (`en`).

All data is synthetic and loaded from deterministic JSON files under `data/` (`seed=42`). No external database or runtime network calls are used.

## Prerequisites

- Python 3.13 managed via [uv](https://docs.astral.sh/uv/)

## Setup & Commands

Run all commands from the `backend/` directory:

```bash
# Install dependencies
uv sync

# (Re)generate deterministic synthetic datasets in data/ (seed=42)
uv run python scripts/generate_data.py

# (Re)generate the 400-case labeled evaluation set (data/eval_set.json, seed=42)
uv run python scripts/generate_eval.py

# Run the risk engine over data/eval_set.json + chronological history replay
uv run python scripts/evaluate.py
uv run python scripts/evaluate.py --json

# Start the API server (CORS enabled for localhost and private LAN origins)
uv run uvicorn app.main:app --port 8000

# Run tests
uv run pytest -q

# Lint and format
uv run ruff check .
uv run ruff format .
```

## API Endpoints

| Method | Path | Query / Headers | Description |
|---|---|---|---|
| `POST` | `/api/payments/check` | `lang=ru\|kk\|en`, optional `X-Role: analyst` | Check payment requisites (`CheckRequest`) and return `CheckResult` (with `ruleset_version`). Appends a privacy-preserving entry to `data/audit.jsonl`. |
| `GET` | `/api/payments/queue` | `lang=ru\|kk\|en`, optional `X-Role: analyst` | List payments awaiting signature (`Q-001`..`Q-010`) with computed `CheckResult` verdicts. |
| `GET` | `/api/history` | — | Return SME client info (`ТОО «ТехноСтрой Астана»`) and 12-month supplier payment history. |
| `POST` | `/api/approvals` | `lang=ru\|kk\|en`, optional `X-Role: analyst` | Submit `{ "check_request": ..., "accountant_note": "..." }` for director review (deduplicates pending requests). |
| `GET` | `/api/approvals` | `bin`, `iik`, `lang=ru\|kk\|en`, optional `X-Role: analyst` | List submitted approvals with optional BIN/IIK filters and localized check details. |
| `POST` | `/api/approvals/{id}/decision` | `lang=ru\|kk\|en`, optional `X-Role: analyst` | Record `{ "decision": "approved" \| "rejected", "director_comment": "...", "trust_account": bool }`. Comment (`>= 10` non-whitespace chars) is required (`422`) for `red` approvals and `trust_account: true`. Appends decision entry to `data/audit.jsonl`. |
| `GET` | `/api/metrics` | `lang=ru\|kk\|en` | Return cached evaluation metrics over `data/eval_set.json` (split into `stopped` / `escalated`), localized `by_kind` labels and disclaimer, and chronological `history_replay` over the client's 12-month history. |
| `GET` | `/api/audit` | `limit=100` (`1..1000`) | Return latest append-only audit log entries from `data/audit.jsonl` (no plaintext PII). |
| `POST` | `/api/demo/reset` | — | Clear approvals, trusted accounts, and short-term session memory and reload JSON datasets. |

## Risk Rules, Banking Secrecy & Analyst View

- **Banking secrecy**: Client responses (`POST /api/payments/check`, `GET /api/payments/queue`, `/api/approvals*`, `/api/metrics`, `/api/audit`) never expose third-party BCC account holder names, BINs, or exact account opening dates for recipients the client has not previously paid (`bcc_account_other_owner` and `new_bcc_account` return redacted reason and evidence text).
- **Analyst view (`X-Role: analyst`)**: Passing header `X-Role: analyst` populates `CheckResult.analyst_details` with internal BCC owner metadata (`owner_name`, `owner_bin`, `opened_at`, `age_days`), unredacted signal details, and exact character positions (`positions`) of suspicious mixed-script / digit-for-letter characters.
- **Unicode & lookalike defense**:
  - Strips combining marks (`Mn`/`Me`), format controls (`Cf`), Hangul/Braille fillers, and variation selectors before NFKC normalization.
  - Skeleton mapping from `data/confusables_subset.json` (Unicode TR39-style subset covering Latin, Greek, IPA `ɑ`, Cherokee `Ꮯ`, Kazakh Cyrillic, and confusable digits `0`/`3`/`6`/`4`/`1`).
  - `mixed_script_name` flags homoglyphs and confusable digits embedded inside Cyrillic words (e.g., `Ка3Л0гистик`) while sparing legitimate brand compounds (`ЭкоSTAR`, `QazaqСтрой`) and normal numbers (`Алматы-2`, `Строй 2020`, `Бетон М350`, `1С`).
  - `lookalike_supplier` detects homoglyph clones, derivative/suffix variants (`Алатау Снабжение`, `АлатауСнабСервис`), and Latin↔Cyrillic transliterations (`Alatau Snab`, `KazLogistik Grupp`).
- **Pre-checks & budget fast-path**:
  - Validates BIN/IIN mod-11 checksum & date prefix, IIK ISO 13616 mod-97 checksum & bank code, and BIK↔IIK consistency.
  - Syntactically valid BCC (`856`) IIKs absent from `data/bcc_accounts.json` return `invalid` (`bcc_account_not_found`).
  - Payments to budget institutions marked `budget: true` in `data/banks.json` (Treasury `KKMFKZ2A` / `070`, State Corporation «Government for Citizens» `GCVPKZ2A` / `009`) with valid requisites return `green`.
- **Bank-verified BCC account & severity escalations**:
  - Known supplier BIN with a new BCC (`856`) IIK verified in `data/bcc_accounts.json` as belonging to the exact same BIN returns `green` (`bcc_owner_verified`) without leaking owner metadata; amount anomaly rules still run.
  - Known supplier + new IIK in a **different bank** + amount `>=` supplier median escalates to `red`.
  - Amount `>= 10×` supplier p90 or new recipient `> 10×` client p90 escalates to `red`; new recipient `> 3×` client p90 escalates to `yellow` (`send_to_director`); first payment with urgency cues escalates to `yellow` (bypassing the amplifier-only cap of 29).
  - Urgency detector matches Russian/Kazakh/English stems (`срочн*`, `шұғыл`, `жедел`, `urgent`, `asap`, `сегодня`, translit, spaced/dotted letters) while ignoring benign forms (`несрочно`, `досрочно`).
- **Optional Kazakhstan payment codes (`kbe`, `knp`)**:
  - `kbe="17"` paired with an individual IIN triggers `kbe_mismatch` (`40` pts, catches droppers even without a legal-form prefix in the name).
  - Unusual `knp` for a known supplier triggers `knp_unusual` (`15` pts amplifier).
- **Short-term memory & SHA-256 deduplication**:
  - `duplicate_invoice`: parses invoice numbers (`счёт № 214`, `сч. 214`, `№ 214`) and flags repeated payments to the same supplier within 90 days across `history.json` and recent checks (`yellow`).
  - `new_recipient_accumulated`: tracks cumulative 7-day volume to the same new recipient across checks.
  - `structuring_72h`: detects `>= 3` payments to the same supplier within 72 hours (amplifier at `20` pts, escalating to `primary` `40` pts when cumulative sum reaches `>= 3×` supplier median).
  - Re-checking the exact same payment form (including switching `lang`) is deduplicated via canonical request `sha256` (excluding `lang`) so repeat UI checks never self-trigger memory rules.
- **Context-aware `next_action`**: Adapts advice to the dominant risk driver (amount-only spike, duplicate invoice, account change / impersonation, or naming the exact invalid field: BIN/IIN, IIK, or BIK).
- **Append-only audit log & ruleset versioning**:
  - Every `CheckResult` and `MetricsResponse` carries `ruleset_version` (configured in `app/risk/config.py`, currently `2026.11.26-r1`).
  - Every `POST /api/payments/check` and `POST /api/approvals/{id}/decision` appends a JSON line to `data/audit.jsonl` (gitignored) containing only `timestamp`, `check_id`, `request_sha256`, `ruleset_version`, `verdict`, `signal_ids`, `action`, and optional `approval_id` — never plaintext company names, BINs, IIKs, amounts, or purposes.

## Localization (`lang`)

- Supported values: `ru` (default), `kk` (Kazakh, Cyrillic), `en` (English). Any other `lang` returns HTTP `422`.
- All user-facing templates live in `app/i18n.py`: headlines, signals, `next_action`, validation errors, `evidence` (`field_label`, `expected`, `actual`), `/api/metrics` `by_kind` labels, and the evaluation disclaimer.
- **Backwards compatibility**: `headline_ru`, `signals[*].reason_ru`, `next_action.text_ru`, `errors[*].message_ru`, and `disclaimer_ru` always retain the Russian text alongside the localized fields (`headline`, `reason`, `text`, `message`, `disclaimer`).

## Synthetic Data Structure (`data/`)

All BIN/IIN/IIK values pass Kazakhstan checksums (mod-11 for BIN/IIN, ISO 13616 mod-97 for IIK) and bank-code/BIK consistency against the National Bank of Kazakhstan catalog in `data/banks.json`:

- `data/banks.json` — Official KZ bank 3-digit codes, 8-char BIKs, names, and `budget: true` flags (`KKMFKZ2A`/`070`, `GCVPKZ2A`/`009`).
- `data/confusables_subset.json` — Confusable character skeleton map (Latin, Greek, IPA, Cherokee, Kazakh Cyrillic, confusable digits).
- `data/registry.json` — Synthetic taxpayer registry mapping BIN/IIN to company or IE names.
- `data/bcc_accounts.json` — Internal BCC (`856` / `KCJBKZKX`) account directory with owner BIN and account opening date.
- `data/history.json` — 12 months of deterministic history for `ТОО «ТехноСтрой Астана»`: **150 payments** across **12 suppliers** in 11 banks (with typical `knp` codes, seasonal spikes, advance/balance cycles, a mid-year legal account switch for `ТОО «ЕвразияКранМонтаж»`, and an IE supplier `ИП Байжанов К.Т.` paid by IIN).
- `data/queue.json` — **10 signing-queue items** (`Q-001`..`Q-010`) with current engine verdicts:
  - `Q-001` (`green`), `Q-002` (`red` — known supplier + new IIK in another bank + amount `820 000 ₸ >=` median `820 000 ₸`), `Q-003` (`red`), `Q-004` (`grey`), `Q-005` (`green`), `Q-006` (`green`), `Q-007` (`invalid`), `Q-008` (`green`), `Q-009` (`red`), `Q-010` (`yellow`).
- `data/eval_set.json` — **400 labeled cases** (`200 legit`, `200 attack`, `seed=42`) across 20 scenario kinds (`9 legit`, `11 attack`), including budget payments, legitimate brand/numeric names, Unicode & digit-in-word evasion, lookalike variants/transliteration, KBe=17 droppers, duplicate invoices, and 72-hour structuring.

## Evaluation Summary (`ruleset=2026.11.26-r1`)

Running `uv run python scripts/evaluate.py` on `data/eval_set.json` (`seed=42`, `n=400`, positive = `yellow` or `red`):

| Metric | Value |
|---|---|
| Detection rate (attack `yellow`/`red`) | **85.5%** (`171/200`) |
| — Stopped (`red`) | **47.5%** (`95/200`) |
| — Escalated (`yellow`) | **38.0%** (`76/200`) |
| False positive rate (legit `yellow`/`red`) | **11.5%** (`23/200`: `red=5`, `yellow=18`) |
| Precision / F1 / Accuracy | **88.1%** / **86.8%** / **87.0%** |
| Chronological `history_replay` (`n=150`) | `green=136`, `yellow=2`, `red=0`, `grey=12`, **alert rate 1.3%** (`2/150`) |

> **Synthetic Evaluation Notice**: `data/eval_set.json` is a synthetic dataset built by the same team that wrote the rule engine, using the synthetic payment history of a single SME client. Metrics from `scripts/evaluate.py` and `GET /api/metrics` illustrate engine behavior across representative scenarios, do **not** represent real banking fraud incidence, and cannot replace validation on real production payment logs. Known blind spots (clean typo-free drops in external banks without history, moderate amount inflation without requisite changes, IIN droppers omitting both legal-form prefix and KBe, out-of-window `>90d` invoice repeats, low-sum structuring splits, and first-time unconfirmed legitimate account switches) are intentionally preserved in the dataset and reflected in the reported numbers.
