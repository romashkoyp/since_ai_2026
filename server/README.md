# server/

Backend API services (**Backend / API Lead**) — Python FastAPI.

## Owns

- API routes that serve alerts and assets for the cockpit
- Sample data wiring until `retrofit/` predictions are plugged in

## Run locally

Requires Python 3.12+ (3.12 recommended).

```bash
cd server
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

- Health: `GET http://localhost:8000/health`
- Alerts: `GET http://localhost:8000/api/alerts`
- Alert triage: `GET http://localhost:8000/api/alerts?severity=SEVERE&severity=MODERATE`
- Assets: `GET http://localhost:8000/api/assets`
- Docs: `http://localhost:8000/docs`

Every alert includes a derived `severity`: `SEVERE` for `MACHINE` confidence ≥ 0.75,
`MODERATE` for other alerts at confidence ≥ 0.50, `MINIMAL` below 0.50, and
`LOW_CONFIDENCE` for `UNKNOWN`. These presentation bands do not alter detector
confidence, fault type, or benchmark prediction CSVs.

## Docker

```bash
docker build -t since-ai-server .
docker run --rm -p 8000:8000 since-ai-server
```

## Do / Don't

- Edit only under `server/`
- Keep alert shapes aligned with `shared/contracts.schema.json`
- Do not move SENTRY / LUMI code here — that stays in `retrofit/`
