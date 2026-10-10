# Campus League frontend

React + Vite + TypeScript. The API contract is in
[`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md).

```bash
npm install
npm run dev
```

By default (`VITE_USE_MOCK_API=true` in `.env`, or no `.env` at all) the app
runs entirely against a built-in mock API, backed by `localStorage`, and
needs no backend.

## Run against the real backend

1. Start the backend first — see [`backend/README.md`](../backend/README.md).
   From `backend/`, with its virtualenv active and the database up:

   ```bash
   python manage.py seed_demo --reset
   python manage.py runserver
   ```

2. From `frontend/`:

   ```bash
   cp .env.example .env
   npm install
   npm run dev
   ```

   `.env.example` already points `VITE_API_BASE_URL` at `/api` (proxied by
   Vite to `http://127.0.0.1:8000/api` — see `vite.config.ts`; the backend
   sends no CORS headers by design, so a direct browser request would be
   blocked) and sets `VITE_USE_MOCK_API=false`.

3. Log in with `member01@skyline.test` / `skyline-demo-2026`.
