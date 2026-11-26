# BCC Business Shield — Backend

Pre-signing verification service for SME supplier payments in Kazakhstan. Compares invoice requisites (BIN/IIN, IIK, BIK), supplier name, and payment amount against the client's payment history and BCC's internal account registry, returning a plain-language Russian verdict (`green`, `yellow`, `red`, `grey`, or `invalid`).

All data is synthetic and stored in-memory from JSON files under `data/`. No external database, authentication, or runtime network calls are used.

## Prerequisites

- Python 3.13 managed via [uv](https://docs.astral.sh/uv/)

## Setup & Commands

Run all commands from the `backend/` directory:

```bash
# Install dependencies
uv sync

# (Re)generate deterministic synthetic datasets in data/ (seed=42)
uv run python scripts/generate_data.py

# Start the API server (CORS enabled for http://localhost:3000)
uv run uvicorn app.main:app --port 8000

# Run tests
uv run pytest -q

# Lint and format
uv run ruff check .
uv run ruff format .
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/payments/check` | Check payment requisites (`CheckRequest`) and return `CheckResult`. |
| `GET` | `/api/payments/queue` | List payments awaiting signature with precomputed `CheckResult` verdicts. |
| `GET` | `/api/history` | Return SME client info and historical supplier payments. |
| `POST` | `/api/approvals` | Submit `{ "check_request": ..., "accountant_note": "..." }` for director review. |
| `GET` | `/api/approvals` | List all submitted approvals. |
| `POST` | `/api/approvals/{id}/decision` | Record `{ "decision": "approved" \| "rejected", "director_comment": "...", "trust_account": bool }`. Comment is required (`422`) when verdict is `red`; approving with `trust_account: true` trusts `(BIN, IIK)` for future checks. |
| `POST` | `/api/demo/reset` | Clear approvals and trusted accounts and reload JSON datasets. |
