# BCC Business Shield — Backend

Pre-signing verification service for SME supplier payments in Kazakhstan. Compares invoice requisites (BIN/IIN, IIK, BIK), supplier name, and payment amount against the client's payment history and BCC's internal account registry, returning a plain-language verdict (`green`, `yellow`, `red`, `grey`, or `invalid`) with localized explanations in Russian (`ru`), Kazakh (`kk`), and English (`en`).

All data is synthetic and stored in memory from deterministic JSON files under `data/` (`seed=42`). No external database, authentication, or runtime network calls are used.

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

# Run the risk engine over data/eval_set.json and print metrics (or --json)
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

| Method | Path | Query Params | Description |
|---|---|---|---|
| `POST` | `/api/payments/check` | `lang=ru\|kk\|en` | Check payment requisites (`CheckRequest`) and return `CheckResult`. |
| `GET` | `/api/payments/queue` | `lang=ru\|kk\|en` | List payments awaiting signature (`Q-001`..`Q-010`) with computed `CheckResult` verdicts. |
| `GET` | `/api/history` | — | Return SME client info (`ТОО «ТехноСтрой Астана»`) and 12-month supplier payment history. |
| `POST` | `/api/approvals` | `lang=ru\|kk\|en` | Submit `{ "check_request": ..., "accountant_note": "..." }` for director review (deduplicates pending requests). |
| `GET` | `/api/approvals` | `bin`, `iik`, `lang=ru\|kk\|en` | List submitted approvals with optional BIN/IIK filters and localized check details. |
| `POST` | `/api/approvals/{id}/decision` | `lang=ru\|kk\|en` | Record `{ "decision": "approved" \| "rejected", "director_comment": "...", "trust_account": bool }`. Comment (`>= 10` non-whitespace chars) is required (`422`) for `red` approvals and `trust_account: true`. |
| `GET` | `/api/metrics` | — | Return cached evaluation metrics over `data/eval_set.json` (computed at startup, language-independent). |
| `POST` | `/api/demo/reset` | — | Clear approvals and trusted accounts and reload JSON datasets. |

## Localization (`lang`)

- Supported values: `ru` (default), `kk` (Kazakh, Cyrillic), `en` (English). Any other `lang` value returns HTTP `422`.
- All message templates live in `app/i18n.py`; validators, rules, and the engine produce message keys and parameters rendered via `app.i18n.t()`.
- **Backwards compatibility**: `headline_ru`, `signals[*].reason_ru`, `next_action.text_ru`, and `errors[*].message_ru` always contain the original Russian text. The localized equivalents are returned in `headline`, `signals[*].reason`, `next_action.text`, and `errors[*].message` (matching `*_ru` when `lang=ru`).
- `GET /api/metrics` does not depend on `lang` — evaluation relies strictly on structured verdict enums (`yellow`/`red` vs `green`/`grey`/`invalid`).

## Synthetic Data Structure (`data/`)

All BIN/IIN/IIK values pass Kazakhstan checksums (mod-11 for BIN/IIN, ISO 13616 mod-97 for IIK) and bank-code/BIK consistency against the National Bank of Kazakhstan catalog in `data/banks.json`:

- `data/banks.json` — Official KZ bank 3-digit codes, 8-char BIKs, and bank names.
- `data/registry.json` — Synthetic taxpayer registry mapping BIN/IIN to company or IE names.
- `data/bcc_accounts.json` — Internal BCC (`856` / `KCJBKZKX`) account directory with owner BIN and account opening date.
- `data/history.json` — 12 months of deterministic history for `ТОО «ТехноСтрой Астана»`: **150 payments** across **12 suppliers** in 11 banks, including seasonal construction volume spikes, 30%/70% and 40%/60% advance/balance cycles, a mid-year legal bank-account switch (`ТОО «ЕвразияКранМонтаж»`), small and large suppliers, and an individual entrepreneur paid by IIN (`ИП Байжанов К.Т.`).
- `data/queue.json` — **10 signing-queue items**:
  - `Q-001`..`Q-004`: core demo scenarios (`green`, `yellow`, `red`, `grey`).
  - `Q-005`..`Q-010`: legitimate large seasonal payment (`green`), payment after a mid-year legal account change (`green`), IIK checksum typo (`invalid`), regular IE paid by IIN (`green`), Kazakh-letter lookalike clone + young BIN (`red`), and legal entity billed to an individual IIN (`yellow`).
- `data/eval_set.json` — **400 labeled cases** (`200 legit`, `200 attack`, `seed=42`) grouped by `kind` (`legit_same`, `legit_name_formatting_variant`, `legit_seasonal_amount`, `legit_account_change_confirmed`, `legit_account_change_unconfirmed`, `legit_new_supplier`, `legit_rebrand_same_account`, `legit_urgent_known_supplier`, `attack_iik_swap_same_bin`, `attack_lookalike_name`, `attack_bcc_other_owner`, `attack_iin_dropper`, `attack_amount_inflation`, `attack_iik_reused_other_supplier`, `attack_typo_free_valid_drop`, `attack_combined_bec`).

## Evaluation Disclaimer

> **Synthetic Evaluation Notice**: `data/eval_set.json` is a synthetic dataset built by the same team that wrote the rule engine, using the synthetic payment history of a single SME client. Metrics from `scripts/evaluate.py` and `GET /api/metrics` illustrate engine behavior across modeled scenarios, do **not** represent real banking fraud incidence, and cannot replace validation on real production payment logs. Known blind spots (such as typo-free drops in external banks without history, moderate amount inflation without requisite changes, IIN droppers omitting legal-form prefixes, and first-time unconfirmed legitimate account switches) are intentionally preserved in the dataset and reflected in the reported numbers.
