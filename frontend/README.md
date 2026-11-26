# Business Shield — Frontend

Pre-signing supplier payment verification UI built with Next.js 16, Tailwind CSS v4, and shadcn/ui.

## Pages

- `/` — **Payments to Sign**: summary tiles, search (`/` shortcut, `Escape` clear), verdict filter chips, payment queue (cards on phones, table on desktop), New Payment dialog/sheet, and the full-page Payment Check screen.
- `/approvals` — **Approvals**: director's desk with summary tiles, pending approval cards (with 10-char comment enforcement for red verdicts / trusted accounts), and resolved history.
- `/attack` — **Attack Console**: interactive sandbox starting from a demo payment with quick-attack actions (homoglyph swap, other-bank KZ IBAN with mod-97 checksum, foreign-owned BCC account, 4× amount, urgency text), live 300ms debounced checks, and character-level Unicode diffs.
- `/metrics` — **Metrics**: synthetic evaluation summary tiles, per-kind detection bars (`GET /api/metrics`), and evaluation disclaimer.

## Internationalization (`src/i18n`)

Supported languages: Russian (`ru`, default), Kazakh (`kk`), and English (`en`), switched via the `РУС / ҚАЗ / ENG` header control and persisted in `localStorage`.

- `src/i18n/ru.ts` — canonical dictionary defining the `Dictionary` TypeScript type.
- `src/i18n/kk.ts`, `src/i18n/en.ts` — typed translations that must satisfy `Dictionary` at compile time.
- `src/i18n/index.tsx` — SSR-safe `LangProvider`, `useT()` hook (`t`, `lang`, `setLang`, `formatMoney`, `formatDate`, `interpolate`, `plural`, `formatTrustedBanner`), and `<html lang>` sync.

## API `lang` Parameter

Every request in `src/lib/api.ts` automatically appends `?lang=<lang>` (using the active language from `src/i18n`) and refetches queue, approvals, open payment check, attack console, and metrics data when the user switches language. Backend responses with optional localized fields (`headline`, `reason`, `text`, `disclaimer`) are resolved via `pickHeadline`, `pickReason`, `pickActionText`, and `pickDisclaimer` in `src/lib/format.ts`, falling back cleanly to their `*_ru` equivalents.

## Requirements

- Node.js 20+
- Backend API running at `http://localhost:8000` (see `NEXT_PUBLIC_API_URL`)

## Setup & Run

1. Copy environment variables:

```bash
cp .env.example .env.local
```

2. Install dependencies:

```bash
npm install
```

3. Run the development server (port 3000):

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser. Make sure the FastAPI backend is running on port 8000.

## Production Build

```bash
npm run build
npm run start
```

## Prod mode

When `NEXT_PUBLIC_APP_MODE` is unset or set to `demo`, the application runs in demo mode without changes and prod-only routes return `404`.

To enable production mode with authentication, roles, persistent payments, and server-side signing control:

1. Set the environment variables (for example, in `.env.local`):

```bash
NEXT_PUBLIC_APP_MODE=prod
BACKEND_URL=http://localhost:8000
```

2. Run the backend in prod mode (`APP_MODE=prod`) on `BACKEND_URL` and start the frontend dev server (`npm run dev`). Next.js proxies `/api/v1/*` same-origin to `${BACKEND_URL}/api/v1/*` via `next.config.ts` rewrites, keeping session cookies (`shield_session`) same-origin and attaching `X-Shield-Request: 1` on non-GET requests.

### Prod Screens & Roles

- `/login` — Sign-in form for company employees (`accountant`, `director`) and bank antifraud analysts (`analyst`).
- `/payments` — Payments queue with status tabs (`To sign`, `With director`, `Rejected`, `Postponed`, `Signed`), traffic-light verdict counters, manual payment creation, 1C (`1CClientBankExchange`) / CSV batch import, and batch actions (`Sign all green`, `Send rest to director`).
- `/payments/[id]` — Full verification breakdown, approval status, and action panel driven strictly by server-provided `permissions` (including pre-sign verdict re-check handling and `AnalystDetailsCard` for the `analyst` role only).
- `/director` — Director approval desk with decision dialog (mandatory comment enforcement for red verdicts / trusted accounts, `can_trust` toggle from the server, and direct signing after approval); read-only for `accountant` and `analyst`.
- `/suppliers` & `/suppliers/[id]` — Confirmed suppliers directory with search, 90-day requisites-change filter and badges, confirmed accounts list (with trust revocation for `director`), change timeline, and recent payments.
- `/audit` — Append-only audit log for `director` and `analyst` (with hash-chain integrity verification for `analyst`).
- `/analytics` — Evaluation metrics view for `analyst`.

