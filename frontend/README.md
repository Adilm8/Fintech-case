# BCC Business Shield — Frontend

Pre-signing supplier payment verification UI for BCC Business internet banking.

## Requirements

- Node.js 24+
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
