# `retrofit/mlmodel/` — trained model artifacts

Put **trained ML model files** here (or under `retrofit/build/mlmodel/` — same idea).

This folder is for **weights / bundles only**. Training and inference code stays in `sentry/`.

## What belongs here

| File / pattern | Example | Notes |
| --- | --- | --- |
| LightGBM / booster text | `lgb_model.txt` | From `sentry/lumi_train.py fit` |
| Pickled bundle | `bundle.pkl` | Features + thresholds + metadata |
| Other formats | `.joblib`, `.onnx`, `.pt` | OK if needed by your trainer |

## What does **not** belong here

| Put it instead in… | Why |
| --- | --- |
| `sentry/` | Training / feature / inference **code** |
| `lumi/` | SLURM / bootstrap scripts |
| `analysis/` | Reports, notebooks, diagnostic CSVs |
| `client/` / `server/` / `shared/` | Wrong domain — never store weights there |

## Recommended layout

```text
retrofit/mlmodel/
├── README.md          ← this file (tracked in git)
├── lgb_model.txt      ← ignored
├── bundle.pkl         ← ignored
└── …                  ← other large artifacts (ignored)
```

Alternate path used by the trainer today:

```bash
# fit → writes into build/mlmodel (also gitignored via retrofit/build/)
python sentry/lumi_train.py fit --shards <gen_out_dir> --out build/mlmodel

# apply
python sentry/lumi_train.py apply --model build/mlmodel --data data/full \
    --split validation --out build/predictions_ml_validation.csv
```

Either `mlmodel/` or `build/mlmodel/` is fine. Prefer one team convention and stick to it.

## Git policy

Large artifacts are **not** committed:

- Root `.gitignore` ignores `retrofit/mlmodel/**` (except this README) and `*.pkl` / `*.npz`
- Share models via LUMI output, team drive, or regenerate with `lumi_train.py fit`

## How the rest of the monorepo should use this

1. **AI team** trains in `retrofit/`, writes artifacts here (or `build/mlmodel/`).
2. **API (`server/`)** should call retrofit inference or load precomputed alerts — do **not** copy weight files into `server/`.
3. **UI (`client/`)** only consumes API JSON — no model files in the frontend.

## Monorepo boundary

`retrofit/` owns detector / sim / ML. Do not edit `client/`, `server/`, `db/`, or `shared/` when adding a model unless Sync Lead agrees on a contract change.
