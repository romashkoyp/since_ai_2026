# client/

Frontend (**Client / UI Lead**) — React + TypeScript (Vite).

## Screens

1. **Fleet triage** — 12-pump matrix, summary KPIs, open alerts  
2. **Asset cockpit** — diagnosis, evidence, SOP, sparklines, what-if derate  
3. **Retrofit scorecard** — T0 vs T1, benchmark, BOM, payback  

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
