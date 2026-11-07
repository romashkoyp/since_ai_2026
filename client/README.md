# client/

Frontend (**Client / UI Lead**) — React + TypeScript (Vite).

## Owns

- Operator cockpit UI (fleet strip + alert list)
- Fetching `/api/alerts` and `/api/assets` from the Python API

## Run locally

```bash
cd client
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` and `/health` to `http://localhost:8000`
(start the server first).

Optional: set `VITE_API_BASE_URL` in a local `.env` to call the API without the proxy.

## Docker

Built via root `docker-compose.yml` (nginx serves the SPA and proxies API to `server`).

## Do / Don't

- Put UI under `client/src/`
- Keep types in sync with `shared/contracts.schema.json`
- Do not alter `shared/` or `retrofit/` from this domain
