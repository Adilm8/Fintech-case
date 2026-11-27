# BCC Business Shield — Backend

Pre-signing verification service for SME supplier payments in Kazakhstan. Compares invoice requisites (BIN/IIN, IIK, BIK, optional KBe/KNP), supplier name, payment purpose, and amount against the client's 12-month payment history, short-term session memory, and BCC's internal account directory, returning a plain-language verdict (`green`, `yellow`, `red`, `grey`, or `invalid`) with localized explanations in Russian (`ru`), Kazakh (`kk`), and English (`en`).

All data is synthetic and loaded from deterministic JSON files under `data/` (`seed=42`). Demo mode uses no external database (prod mode uses local SQLite). Core payment verification makes zero outbound network calls; the only optional outbound API calls happen in `POST /api/invoice/extract` and `POST /api/explain` when `ANTHROPIC_API_KEY` is configured (both fall back locally without a key and never affect payment verdicts).

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
| `POST` | `/api/payments/check` | `lang=ru\|kk\|en`, `commit=false\|true` (default `false`), optional `X-Role: analyst` | Check payment requisites (`CheckRequest`) and return `CheckResult` (with `ruleset_version`). Dry run by default (`commit=false`): drafts, edits, and attack-console probes are not recorded in short-term memory. Passing `commit=true` signals intent to pay and records the check in short-term memory (deduplicated by canonical request SHA-256) for `duplicate_invoice` (90d), `structuring_72h` (72h), and `new_recipient_accumulated` (7d). Appends a privacy-preserving entry to `data/audit.jsonl`. |
| `GET` | `/api/payments/queue` | `lang=ru\|kk\|en`, optional `X-Role: analyst` | List payments awaiting signature (`Q-001`..`Q-010`) with computed `CheckResult` verdicts. |
| `GET` | `/api/history` | — | Return SME client info (`ТОО «ТехноСтрой Астана»`) and 12-month supplier payment history. |
| `POST` | `/api/approvals` | `lang=ru\|kk\|en`, optional `X-Role: analyst` | Submit `{ "check_request": ..., "accountant_note": "..." }` for director review (deduplicates pending requests). |
| `GET` | `/api/approvals` | `bin`, `iik`, `lang=ru\|kk\|en`, optional `X-Role: analyst` | List submitted approvals with optional BIN/IIK filters and localized check details. |
| `POST` | `/api/approvals/{id}/decision` | `lang=ru\|kk\|en`, optional `X-Role: analyst` | Record `{ "decision": "approved" \| "rejected", "director_comment": "...", "trust_account": bool }`. Comment (`>= 10` non-whitespace chars) is required (`422`) for `red` approvals and `trust_account: true`. `trust_account: true` is allowed on `yellow` account-change checks and on `red` checks when the only weighted signals are `iik_changed` + `bank_changed` (no blocking or other risk signals). Appends decision entry to `data/audit.jsonl`. |
| `POST` | `/api/invoice/extract` | `filename` query, raw file body (`Content-Type`) | Optional helper: extract payment form fields from a PDF/image invoice (`<= 10 MB`) and re-validate KZ checksums. Calls an external API only when `ANTHROPIC_API_KEY` is set; falls back locally to template/regex parsing otherwise. Verdict never depends on it. |
| `POST` | `/api/explain` | — | Optional helper: restate a computed `CheckResult` in 3–5 plain-language sentences (`ru`/`kk`/`en`). Calls an external API only when `ANTHROPIC_API_KEY` is set; falls back locally to a deterministic template otherwise. Verdict never depends on it. |
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
  - `lookalike_supplier` detects homoglyph clones, derivative/suffix variants (`Алатау Снабжение`, `АлатауСнабСервис`), Latin↔Cyrillic transliterations (`Alatau Snab`, `KazLogistik Grupp`), entity-wrapper clones (`Торговый дом Алатау`), initial-letter abbreviations (`А-Снаб`), English business-term translations (`Alatau Supply`), and distinctive-stem vowel swaps (`Алатоо Снаб`):
    - Exact or near-exact normalized matches (`similarity >= 95`) with a different BIN escalate directly to `block` (`red`, `100` pts) regardless of BIN age, because a legal entity's BIN does not change.
    - Generic vs. distinctive business and geographic tokens (e.g., `сервис`/`servis`/`service`, `снаб`/`snab`/`supply`, `монтаж`, `астана`, `караганда`) are classified once on lower-case Cyrillic form and carried over to transliterated/upper-case forms, preventing false alarms on legitimate new suppliers such as `ТОО «Астана Сервис»` or `ТОО «Монтаж Сервис»`.
    - For individual entrepreneurs (`ИП`/`ЖК`), initials must match (different initials such as `ИП Байжанова А.К.` vs. `ИП Байжанов К.Т.` are treated as distinct individuals and not flagged).
    - Payment amounts are compared against a matched lookalike supplier's history only when normalized name similarity is `>= 92`; otherwise they are compared against the client's overall payment profile (`p90`).
- **Pre-checks & budget fast-path**:
  - Validates BIN/IIN mod-11 checksum & date prefix, IIK ISO 13616 mod-97 checksum & bank code, and BIK↔IIK consistency.
  - Syntactically valid BCC (`856`) IIKs absent from `data/bcc_accounts.json` return `invalid` (`bcc_account_not_found`).
  - Payments to budget institutions marked `budget: true` in `data/banks.json` (Treasury `KKMFKZ2A` / `070`, State Corporation «Government for Citizens» `GCVPKZ2A` / `009`) with valid requisites return `green`.
- **Bank-verified BCC account & severity escalations**:
  - Known supplier BIN with a new BCC (`856`) IIK verified in `data/bcc_accounts.json` as belonging to the exact same BIN returns `green` (`bcc_owner_verified`) without leaking owner metadata; amount anomaly rules still run.
  - Known supplier + new IIK in a **different bank** + amount `>=` supplier median escalates to `red`.
  - Amount `>= 10×` supplier p90 or new recipient `> 10×` client p90 escalates to `red`; new recipient `> 3×` client p90 escalates to `yellow` (`send_to_director`); first payment with urgency cues escalates to `yellow` (bypassing the amplifier-only cap of 29).
  - Urgency detector matches Russian/Kazakh/English stems (`срочн*`, `шұғыл`, `жедел`, `urgent`, `asap`, `сегодня`, translit, spaced/dotted letters) while ignoring benign forms (`несрочно`, `досрочно`).
- **Bank-wide cross-client signals (`data/bank_signals.json`)**:
  - Closes the "typo-free external-bank dropper" blind spot using anonymized signals visible only at the bank level, loaded directly inside `app/risk/bank_signals.py` (`seed=42`, no third-party client names or payer BINs).
  - `iik_reported_by_clients`: triggers when other BCC clients have reported the recipient IIK as fraudulent (`1..2` reports → `primary` `60` pts; `>= 3` reports → `block` `red`).
  - `iik_on_watchlist`: triggers `block` `red` (`100` pts) when the recipient IIK matches the synthetic antifraud-center mule watchlist (NBRK antifraud-center style mock).
  - `fresh_iik_many_payers`: triggers when a fresh account (including accounts in external banks) receives first-time payments from `>= 3` unrelated BCC clients within 7 days (`primary` `50` pts; `>= 5` clients → `primary` `70` pts, `red`).
  - **`bank_known_bin` exemption**: `fresh_iik_many_payers` is automatically skipped when the recipient BIN has long-standing history in BCC (`>= 2` years in `bank_known_bin`), so legitimate high-inflow organizations (e.g., a new branch account of a major utility or telecom provider) are never falsely flagged.
  - **Anonymity & banking secrecy**: Client-facing messages (`ru`/`kk`/`en`) and evidence are strictly aggregated and bucketed (`"несколько"` / `"3+"` / `"5+"`), never disclosing third-party client names, payer BINs, exact counts, report dates, or cumulative inflow amounts; exact figures are surfaced only in `analyst_details` for `X-Role: analyst`.
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
  - Every `CheckResult` and `MetricsResponse` carries `ruleset_version` (configured in `app/risk/config.py`, currently `2026.11.26-r3`).
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
- `data/bank_signals.json` — Deterministic anonymized bank-wide signals (`complaints`, `fresh_inflows`, `mule_watchlist`, and `bank_known_bin` exemptions; no third-party client names or payer BINs).
- `data/history.json` — 12 months of deterministic history for `ТОО «ТехноСтрой Астана»`: **150 payments** across **12 suppliers** in 11 banks (with typical `knp` codes, seasonal spikes, advance/balance cycles, a mid-year legal account switch for `ТОО «ЕвразияКранМонтаж»`, and an IE supplier `ИП Байжанов К.Т.` paid by IIN).
- `data/queue.json` — **10 signing-queue items** (`Q-001`..`Q-010`) with current engine verdicts:
  - `Q-001` (`green`), `Q-002` (`yellow` — known supplier + new IIK in another bank, amount `700 000 ₸` below median; at/above median the same change is `red`), `Q-003` (`red`), `Q-004` (`grey`), `Q-005` (`green`), `Q-006` (`green`), `Q-007` (`invalid`), `Q-008` (`green`), `Q-009` (`red`), `Q-010` (`yellow`).
- `data/eval_set.json` — **400 labeled cases** (`200 legit`, `200 attack`, `seed=42`) across 23 scenario kinds (`11 legit`, `12 attack`), including budget payments, legitimate brand/numeric names, new legitimate suppliers with generic words or differing IE initials (`legit_new_supplier_generic_word`), established `bank_known_bin` popular suppliers with high first-payment inflows, Unicode & digit-in-word evasion, lookalike variants/transliteration/translation/wrapper/abbreviation clones, KBe=17 droppers, external-bank droppers caught by bank-wide signals, duplicate invoices, and 72-hour structuring.

## Evaluation Summary (`ruleset=2026.11.26-r3`)

Running `uv run python scripts/evaluate.py` on `data/eval_set.json` (`seed=42`, `n=400`, positive = `yellow` or `red`):

| Metric | Value |
|---|---|
| Detection rate (attack `yellow`/`red`) | **87.0%** (`174/200`) |
| — Stopped (`red`) | **50.0%** (`100/200`) |
| — Escalated (`yellow`) | **37.0%** (`74/200`) |
| False positive rate (legit `yellow`/`red`) | **11.5%** (`23/200`: `red=8`, `yellow=15`) |
| Precision / F1 / Accuracy | **88.3%** / **87.7%** / **87.8%** |
| Chronological `history_replay` (`n=150`) | `green=136`, `yellow=2`, `red=0`, `grey=12`, **alert rate 1.3%** (`2/150`) |

> **Synthetic Evaluation Notice**: `data/eval_set.json` is a synthetic dataset built by the same team that wrote the rule engine, using the synthetic payment history of a single SME client. Metrics from `scripts/evaluate.py` and `GET /api/metrics` illustrate engine behavior across representative scenarios, do **not** represent real banking fraud incidence, and cannot replace validation on real production payment logs. Known blind spots (brand-new external drops prior to complaints or multi-client inflows, moderate amount inflation without requisite changes, IIN droppers omitting both legal-form prefix and KBe, out-of-window `>90d` invoice repeats, low-sum structuring splits, and first-time unconfirmed legitimate account switches) are intentionally preserved in the dataset and reflected in the reported numbers.

## Prod Mode

Alongside the stateless in-memory demo (`app.main:app`), the backend includes a local production-like mode (`app.prod.app:app`) under `/api/v1/*` backed by SQLite (WAL mode, stdlib `sqlite3`), session-cookie authentication (`hashlib.scrypt`), role-based access control (`accountant`, `director`, `analyst`), a server-enforced pre-signing gate, a confirmed supplier directory, 1C/CSV batch import, and a SHA-256 hash-chained append-only audit log.

Demo mode remains the default and is completely unchanged: running `uv run uvicorn app.main:app --port 8000` or `uv run uvicorn app.asgi:app --port 8000` without `APP_MODE` serves the demo API (`/api/*`). Setting an unrecognized `APP_MODE` value fails fast at startup.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `APP_MODE` | `demo` | Application mode: `demo` or `prod` (any other value raises a startup error). |
| `SHIELD_DB_PATH` | `backend/var/shield.db` | SQLite database file path (`var/` is gitignored). |
| `SHIELD_SESSION_TTL_HOURS` | `12` | Session cookie lifetime in hours. |
| `SHIELD_COOKIE_SECURE` | `0` | Set to `1` to add the `Secure` cookie flag behind HTTPS. |
| `SHIELD_TODAY` | *(empty)* | Optional `YYYY-MM-DD` override pinning "today" for reproducible checks and seeding. |
| `SHIELD_SEED_PASSWORD` | *(empty)* | Password for seeded users; if unset, a random password is generated and printed once to stdout. |
| `SHIELD_PDF_FONT` | *(empty)* | Optional path to a Unicode TrueType (`.ttf`) font for Cyrillic/Kazakh PDF export (auto-detects system Arial/Segoe UI/DejaVu/Liberation fonts by default). |
| `ANTHROPIC_API_KEY` | *(empty)* | Optional key enabling external API calls in `/api/invoice/extract` and `/api/explain`; when unset, both fall back locally and never affect payment verdicts. |

> **Frontend demo login helpers**: Setting `NEXT_PUBLIC_DEMO_LOGINS=1` in the frontend environment shows role quick-fill buttons (`accountant`, `director`, `analyst`) on prod `/login` that populate only the login input; passwords are never hardcoded and must still be typed manually.

### Seeding and Running Prod Mode

Run from `backend/`:

```bash
# Seed SQLite DB (1 company, 3 users, 150 shifted signed payments, 12 suppliers)
# Add --with-queue to also import data/queue.json into the signing queue
APP_MODE=prod uv run python -m app.prod.seed --reset --with-queue

# Start the prod ASGI server
APP_MODE=prod uv run uvicorn app.asgi:app --port 8000
```

PowerShell equivalent:

```powershell
$env:APP_MODE="prod"
uv run python -m app.prod.seed --reset --with-queue
uv run uvicorn app.asgi:app --port 8000
```

- The seed command refuses to run unless `APP_MODE=prod` and never modifies files in `data/`.
- **Seed users**: `accountant` and `director` (scoped to `ТОО «ТехноСтрой Астана»`), plus `analyst` (bank-wide read-only view, no company).
- **Password & session security**: no plaintext passwords are stored in the repository or database (`hashlib.scrypt` with `n=2^15, r=8, p=1` and 16-byte random salt); login attempts are rate-limited (5 failures per 15 minutes per login → `429`); opaque tokens are issued via `HttpOnly; SameSite=Lax` cookie `shield_session` with only their SHA-256 hash stored in SQLite; all non-GET `/api/v1/*` requests require header `X-Shield-Request: 1`; demo `X-Role` headers are ignored in prod mode.
- **Sample import files**: `data/samples/sample_1c.txt` (`cp1251`, 1CClientBankExchange with 6 documents) and `data/samples/sample.csv` (`;` delimiter).

### Prod API Endpoints (`/api/v1/*`)

| Method | Path | Roles | Description |
|---|---|---|---|
| `GET` | `/api/v1/meta` | public | Runtime mode (`"prod"`) and active `ruleset_version`. |
| `POST` | `/api/v1/auth/login`, `/logout` | public / any | Session cookie login (`401`/`429`) and revocation (`204`). |
| `GET` | `/api/v1/auth/me` | any | Current authenticated `{user, company}`. |
| `GET`, `PUT` | `/api/v1/me` | any | Current user profile (`full_name`, `default_lang`, `company`) and profile update (audited). |
| `POST` | `/api/v1/me/password` | any | Change password (`scrypt`), revoke all other active sessions, and record audit entry. |
| `GET` | `/api/v1/company` | A, D | Company profile (`name`, `bin`, `iik`, `bik`) and company users with roles and active status. |
| `POST` | `/api/v1/company/users` | D | Invite a new company user (`accountant` \| `director`); returns a one-time `temporary_password`. |
| `PUT` | `/api/v1/company/users/{id}` | D | Update company user role or active flag (revokes sessions on deactivation; protects last active director with `409 last_director_protected`). |
| `GET`, `PUT` | `/api/v1/company/settings` | D | Company notification filter (`notify_on`: `red` \| `red_yellow`) and `approval_threshold_kzt` (payments `>= threshold` require director approval even when `green`, returning `409 threshold_requires_approval` in `/sign` and `/batch/sign-green`). |
| `GET`, `POST` | `/api/v1/notifications`, `/notifications/read` | any | Server-derived notifications (pending approvals, director decisions, `sign_denied`) filtered by `notify_on`, with per-user read state. |
| `GET`, `POST` | `/api/v1/payments` | A, D, N / A | Paginated payment list with full-scope `counts`, filters, search; create & verify manual payment (`201`). |
| `GET` | `/api/v1/payments/export` | A, D, N | Export check history (`format=csv` UTF-8 BOM for Excel with formula-injection neutralization prefixing `'` on free-text cells starting with `=`, `+`, `-`, `@`, `\t`, or `\r` while keeping numeric columns numeric; `format=pdf` A4 report «Что проверить перед подписью» with embedded Cyrillic TTF) filtered by `scope`, `from`, `to`. |
| `GET`, `PUT` | `/api/v1/payments/{id}` | A, D, N / A | View payment (`analyst_details` only for `analyst`); edit & recheck editable statuses (`checked`, `rejected`, `postponed`). |
| `POST` | `/api/v1/payments/{id}/sign` | A, D | Server-side signing gate (rechecks at sign time, enforces approval/ack rules — returns `409 identity_requires_approval` when `yellow`/`grey` carries any `IDENTITY_SIGNAL_IDS` signal so director approval is required — updates supplier directory atomically, logs `sign` / `sign_denied`). |
| `POST` | `/api/v1/payments/{id}/{recheck,send-to-director,postpone,resume,cancel}` | A | Lifecycle transitions and approval submission. |
| `POST` | `/api/v1/payments/import` | A | Import 1C (`utf-8`/`cp1251`/`cp866`) or CSV (`;` / `,`) batch (`application/octet-stream`, `≤ 2 MB`, `≤ 500` docs; tested on synthetic exports only). |
| `GET` | `/api/v1/batches` | A, D, N | List recent import batches. |
| `POST` | `/api/v1/payments/batch/{sign-green,send-to-director}` | A, D / A | Batch-sign verified `green` payments or batch-escalate `yellow`/`red`/`grey` payments. |
| `GET` | `/api/v1/approvals` | A, D, N | List approvals (`pending` first, excludes `superseded` by default). |
| `POST` | `/api/v1/approvals/{id}/decision` | D | Director approve/reject with optional `trust_account` (allowed on `yellow` account change and on `red` when only `iik_changed` + `bank_changed` with no blocking/other risk signals; comment `≥ 10` non-whitespace chars required). |
| `GET` | `/api/v1/suppliers`, `/suppliers/{id}` | A, D, N | Confirmed supplier directory, accounts, change chronology, and latest 50 payments. |
| `POST` | `/api/v1/suppliers/{id}/accounts/{account_id}/untrust` | D | Revoke director account trust with mandatory comment (`≥ 10` meaningful chars). |
| `GET` | `/api/v1/audit`, `/audit/verify` | D, N / N | Hash-chained SQLite audit trail and chain integrity check (`{ok, checked, broken_at}`). |
| `GET` | `/api/v1/metrics` | N | Cached evaluation dataset metrics (same schema as demo `/api/metrics`). |
| `POST` | `/api/invoice/extract`, `/api/explain` | any | Same optional invoice extraction and plain-language explanation helpers as demo mode, mounted behind prod session cookie + `X-Shield-Request: 1` header. Call an external API only when `ANTHROPIC_API_KEY` is set (local fallback otherwise); verdicts never depend on them. |

### Running Prod Tests

```bash
# Run prod-mode test suite only
uv run pytest -q tests/prod

# Run full test suite (demo + prod) and linter
uv run pytest -q
uv run ruff check .
```
