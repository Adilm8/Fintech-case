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
