# server/

Backend API services (**Backend / API Lead**) — Python FastAPI.

## Owns

- REST API behind the operator dashboard (Fleet + Pump screens)
- Running the trained hybrid model (`../retrofit_engine/`, AI domain, used read-only) on uploaded pump data
- Storing each model run (MongoDB Atlas, or in memory when `MONGODB_URI` is empty)

## How data flows

```text
POST /api/analyses (datasheet + telemetry [+ baseline, context, snapshots, events])
  -> retrofit_engine.predict()            physics rules decide WHEN, rules + ML decide WHAT
  -> src/analysis.py                      per pump: status tile, open alerts, cockpit (evidence, trends, sandbox)
  -> stored as one immutable run          the dashboard always shows the LATEST run
GET /api/fleet/summary, /api/assets, /api/alerts, /api/cockpit/{id}   <- read the latest run
```

At startup an empty store is filled with `seed/demo_run.json`, so the dashboard shows real model output at once.

## Run locally

Requires Python 3.12+. Run from `server/`; the model package is found in the repo root automatically.

```bash
cd server
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn src.main:app --reload --port 8000
python -m pytest -q
```

Docs: `http://localhost:8000/docs`

## Endpoints

Full guide with request/response examples, error codes and the severity and sandbox rules: [API.md](API.md).

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | status, database (`connected`/`disabled`), model version |
| GET | `/api/fleet/summary` | headline counts for the Fleet screen |
| GET | `/api/assets` | one status tile per pump (`severity`: act_now / attention / sensor / ok) |
| GET | `/api/alerts?asset_id=&event_class=&severity=` | alerts of the latest run (`shared/contracts.schema.json` shape); repeat `severity` for triage, e.g. `?severity=SEVERE&severity=MODERATE` |
| GET | `/api/alerts/{asset_id}?severity=` | alerts for one pump (404 if none) |
| GET | `/api/cockpit/{asset_id}` | diagnosis, evidence, SOP, sensor trends, mitigation sandbox |
| GET | `/api/scorecard` | retrofit business case (static) |
| GET | `/api/model` | installed model, required datasheet columns, upload limit |
| POST | `/api/analyses` | multipart upload → run the model → `201` run summary |
| GET | `/api/analyses`, `/api/analyses/latest`, `/api/analyses/{run_id}` | run summaries |
| GET | `/api/analyses/{run_id}/alerts.csv` | alerts in the organisers' template CSV |
| GET/POST | `/retrofit/*` | the engine's own stateless endpoints (Kaleb's router) |

Every alert includes a derived `severity`: `SEVERE` for `MACHINE` confidence ≥ 0.75,
`MODERATE` for other alerts at confidence ≥ 0.50, `MINIMAL` below 0.50, and
`LOW_CONFIDENCE` for `UNKNOWN`. These presentation bands do not alter detector
confidence, fault type, or benchmark prediction CSVs. (Not the same as a pump's `severity` in `/api/assets`,
which is its triage level from the urgency of its open alerts.)

Upload errors: `415` wrong file type, `413` too large, `422` bad content (message says what to fix),
`503` model not available.

Upload fields and formats are described in `../retrofit_engine/README.md`. `events` (optional) is a ground-truth
table (`asset_id, fault_type, onset_utc, end_utc`); when given, each alert gets `true_fault_type` / `correct`.

## Settings (environment)

| Variable | Default | Meaning |
|---|---|---|
| `MONGODB_URI`, `MONGODB_DB` | empty, `since_ai` | Atlas connection; empty = in-memory runs |
| `CORS_ORIGINS` | localhost + VM | comma-separated |
| `MAX_UPLOAD_MB` | 200 | per uploaded file |
| `ACTIVE_ALERT_HOURS` | 48 | an alert is "open" if raised this long before the pump's last reading |
| `ENERGY_PRICE_EUR_KWH` | 0.15 | sandbox energy saving |
| `COOLING_MIN_FLOW_FRACTION` | 0.8 | share of today's flow the cooled system needs (sandbox cooling margin) |
| `SEED_RUN_PATH` | `seed/demo_run.json` | run loaded into an empty store |

## Rebuild the demo seed run

After a new model is exported into `retrofit_engine/model/`:

```bash
python ../retrofit/make_dataset.py --tier full --output /tmp/retrofit_full     # or use the organisers' data/full
python -m scripts.build_seed_run --data /tmp/retrofit_full/public
```

The seed run is a model run on the simulator's public train + validation data. The model was trained on data
from the same simulator, so its scores here are optimistic.

## Docker

The image is built from the **repo root** because it ships `retrofit_engine/`:

```bash
docker build -f server/Dockerfile -t since-ai-server .
docker run --rm -p 8000:8000 since-ai-server
```

## Notes

- `src/data/fault_actions.json` is a copy of `joice_physics_rules/dashboard_data/fault_actions.json`
  (plain-language names, urgency and steps per fault type). Copy it again if that file changes.
- The mitigation sandbox (`src/sandbox.py`) uses pump affinity laws. Its risk value is the model's confidence
  that the fault is present, scaled by speed; it is not a failure probability. The cockpit's `sandbox_note`
  says this and lists the assumptions it made for each pump.

## Do / Don't

- Edit only under `server/`
- Keep alert shapes aligned with `shared/contracts.schema.json`
- Do not move SENTRY / LUMI code here — that stays in `retrofit/`; the model package stays in `retrofit_engine/`
