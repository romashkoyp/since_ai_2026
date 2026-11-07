# client/

Frontend (**Client / UI Lead**) — React + TypeScript (Vite).

## Screens

1. **Overview (fleet triage)** — health %, status filters, pump cards + actions  
2. **Pump details (unified asset cockpit)** — docs Screen 2: diagnosis, evidence, SOP/sign-off, trends/spectrum, mitigation simulator (NPSH / risk / energy / cooling margin); alert triage defaults to **Moderate + Severe**, with toggles for **Minimal** and **Low confidence** (`UNKNOWN`)
3. **Savings & value (scorecard)** — T0 vs T1, benchmark %, BOM, payback  

Demo cockpit numbers for **PUMP-08** follow `docs/ui_images/screen2_unified_asset_cockpit.jpg` / `docs/ui_description.md`.  


Data from FastAPI: `/api/assets`, `/api/fleet/summary`, `/api/cockpit/{id}`, `/api/scorecard`, `/api/alerts`.

## Run locally

```bash
cd client
npm install
npm run dev
```

Open `http://localhost:5173` with the API on `:8000`.

## Docker

```bash
docker build --build-arg VITE_API_BASE_URL="http://BE_PUBLIC_IP:8000" -t since-ai-client .
```
