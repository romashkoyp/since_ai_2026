# 2026-11-07 - RETROFIT AI domain added: `retrofit/` (PR #2)

This file documents (for the team log / pitch notes) what was added to the repo in
**PR #2 (`feat/retrofit-sentry-lumi`)** and why. **The root `README.md` (team workflow) was left
untouched**; nothing in it changed. All content that would normally go into a README lives here.

---

## 1. New domain folder: `retrofit/`

The RETROFIT AI 2026 cooling-water-pump domain is now a full sub-folder inside the monorepo
(58 files, 1.2 MB of code + reports only - **no** data, no binaries). Using the team
monorepo + owning-domain rule from the team `README.md`:

```text
since_ai_2026/
└── retrofit/                  # our domain, nobody else edits here
    ├── sentry/                # rules-based detector ("SENTRY") + LUMI data-gen/ML pipeline
    ├── lumi/                  # one-shot bootstrap + SLURM scripts for LUMI
    ├── analysis/              # re-runnable diagnostic scripts, reports, figures
    ├── src/                   # challenge simulator + scorer (src/retrofit_sim/*)
    ├── configs/               # fleet_public.yaml (challenge fleet config)
    └── README.md              # re-run instructions (local + LUMI)
```

### 1.1 Measured benchmark performance (official event-based scorer)

| Split | Baseline B1 | SENTRY (rules) | Delta |
|---|---|---|---|
| train (7 pumps) | 58.2 | **66.5** | +8.3 |
| validation (2 pumps) | 78.0 | **87.7** | **+9.7** |

Validation detail: recall 8/9, precision 1.00 (0 false alerts), fault-type recall **0.778**
(B1: 0.444), median lead 13.3 h. Train detail: recall 0.731, precision 0.792, fault-type 0.423.

### 1.2 What's inside `sentry/`

| File | Purpose |
|---|---|
| `sentry/regime.py` | Causal regime-conditioned robust baselines + per-channel noise floors |
| `sentry/physics.py` | Vectorized pump-curve + NPSH margin estimator (reuses the simulator's own physics) |
| `sentry/snapshots.py` | 10.24 kHz vibration-snapshot analyzer (Hilbert envelope, BPFO/BPFI demod) |
| `sentry/detect.py` | Detection rule cascade + alert manager (burst discipline, storm/voltage-sag vetoes) |
| `sentry/run.py` | Per-split runner (train / validation / test) |
| `sentry/lumi_generate.py` | LUMI-parallel **synthetic-data generator** (in-memory pumps, compact feature tables) |
| `sentry/ml_features.py` | Canonical ML feature builder (shared by training and inference) |
| `sentry/lumi_train.py` | LightGBM diagnosis-head trainer + trained-model inference |

Snapshot envelope features: `BPFO`, `BPFI`, `1x`, `2x`, `3x` + the auto-learned 2.6-3.0 kHz
housing-resonance band (details in `retrofit/analysis/DEEP_DIVE_REPORT.md`).

### 1.3 LUMI integration

`retrofit/lumi/bootstrap_lumi.sh` does one full pipeline run on LUMI:

```bash
export GITHUB_TOKEN=ghp_xxx
bash retrofit/lumi/bootstrap_lumi.sh project_462001520
#  - clones THIS repo, builds venv inside retrofit/, rewrites the sbatch_* account & path,
#  - sbatches `lumi/sbatch_generate.sh` (production data generator, ~10-15 min on 1 node)
#  - then `sbatch lumi/sbatch_train.sh` (LightGBM training on 6,000 pumps)
```

Note: the earlier private `lukskrp/sentry-lumi-payload` mirror is still usable (bootstrap's
`REPO_URL` var overrides), but the default is now the team repo. Archive/delete that mirror when
convenient.

---

## 2. Root `.gitignore`: co-scoped rules (untouched team rules + new retrofit/ rules)

The `.gitignore` change is co-scoped; the team file keeps its own rules intact and now also
excludes, inside `retrofit/`:

```gitignore
retrofit/.venv/
retrofit/build/
retrofit/logs/
retrofit/data/
retrofit/shards/
retrofit/mlmodel/
retrofit/src/retrofit_sim.egg-info/
retrofit/*.pkl
retrofit/**/*.pkl
retrofit/**/*.npz
```

This keeps ~110 MB of benchmark data, model bundles, and shards out of the tree while allowing
all source, scripts, and diagnostics to be commit-hygienic.

---

## 3. What is NOT in the repo (by design)

- The ~110 MB `data/full/` challenge telemetry - regenerated on demand with
  `python make_dataset.py --tier full --output build/full` and by `retrofit/lumi/bootstrap_lumi.sh`
  on LUMI.
- Trained model bundles (`mlmodel/bundle.pkl`, `mlmodel/lgb_model.txt`) - generated at runtime;
  `*.pkl` is ignored.
- Shard intermediate files (`shards/shard_*.parquet`, `shards/meta_*.parquet`) - generated at
  runtime by `lumi_generate.py`; ignored.
- Logs and `.venv` - ignored.

---

## 4. How to re-run locally (laptop, from inside `retrofit/`)

```bash
cd retrofit
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate
pip install -r requirements.txt
python sentry/run.py --data data/full --split validation --out build/predictions_sentry_validation.csv
# then score:
python -m retrofit_sim score --predictions build/predictions_sentry_validation.csv \
    --events data/full/events_validation.csv --assets data/full/assets.csv \
    --benign data/full/benign_windows_train_validation.csv --split validation
```

## 5. How to run on LUMI (full generate -> train -> score -> predict pipeline)

See `retrofit/lumi/README.md` step-by-step. Summary:

```bash
export GITHUB_TOKEN=ghp_xxx
bash retrofit/lumi/bootstrap_lumi.sh project_462001520     # generate + sbatch, ~10-15 min on 1 node
sbatch lumi/sbatch_train.sh                                # LightGBM train, ~2-5 min
```

---

## 6. Next steps (aligned with the team `plan.md` roadmap)

- **P2 Streamlit dashboard** (alert card, fleet triage, what-if sandbox, replay) - pieces are
  reusable from `sentry/` and the `analysis/` scripts.
- **Trained diagnosis layer** on LUMI-generated synthetic data (P3): `sentry/lumi_train.py fit`
  against `shards/` from `lumi_generate.py`. Measured plan: gate AUC ~0.999 on the held-out pump
  fold for a smoke model; waiting on the full 6,000-pump LUMI run.
- **Baseline comparison table + pitch deck** (P4): `analysis/DETECTOR_DESIGN.md`,
  `analysis/DEEP_DIVE_REPORT.md`, and `analysis/figs/*.png` are already on hand.
