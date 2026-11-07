# retrofit — RETROFIT AI: SENTRY rules-based detector + LUMI data-gen/ML pipeline

Independent domain of the `since_ai_2026` monorepo (see repo root `README.md` for team rules, git
flow, and agent rules). **Do not edit files outside `retrofit/` unless you own this domain.**

## What is here

- The RETROFIT AI 2026 challenge package — a synthetic 12-pump benchmark (`src/retrofit_sim/`,
  `configs/fleet_public.yaml`, `make_dataset.py`) — plus our own additions:
- `sentry/` — **the rules-based detector ("SENTRY")**, its physics module, snapshot analyzer,
  regime residuals, and the LUMI-parallel **synthetic-data generator + LightGBM trainer**
  (`lumi_generate.py`, `ml_features.py`, `lumi_train.py`) → beats baseline B1 (58.2 train / 78.0
  validation) with **66.5 train / 87.7 validation** on the official event-based scorer.
- `lumi/` — one-shot bootstrap + SLURM scripts for running the full **generate → train →
  score → predict** cycle on the **LUMI** supercomputer from scratch (see `lumi/README.md`).
- `analysis/` — diagnostic scripts, technical model deep-dive report, detector design doc,
  figures, and a few measured diagnostic dumps. All re-runnable from any checkout
  (`ROOT = Path(__file__).resolve().parents[1]`).

## Local re-run (laptop)

```bash
cd retrofit
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python sentry/run.py --data data/full --split validation --out build/predictions_sentry_validation.csv
# then score:
python -m retrofit_sim score --predictions build/predictions_sentry_validation.csv \
    --events data/full/events_validation.csv --assets data/full/assets.csv \
    --benign data/full/benign_windows_train_validation.csv --split validation
```

## LUMI re-run

```bash
export GITHUB_TOKEN=ghp_xxx
bash retrofit/lumi/bootstrap_lumi.sh project_462001520        # bootstrap + sbatch the GENERATION job
# then: sbatch lumi/sbatch_train.sh
```

Details: `lumi/README.md`, `sentry/README.md` (scorer output, current measured decision
thresholds, and known limitations).

## Layout (monorepo rule: only our domain is touched)

```text
retrofit/
├── make_dataset.py, requirements.txt, pyproject.toml  (challenge package files)
├── src/retrofit_sim/   (challenge simulator + scorer)
├── configs/            (fleet_public.yaml)
├── sentry/             (our detector + LUMI ML pipeline)
├── lumi/               (SLURM + bootstrap scripts)
└── analysis/           (reports + diagnostics, re-runnable)
```
