# SENTRY on LUMI — Step-by-step guide

Measured facts to plan with (single-core, this laptop):

| Task | Runtime |
|---|---|
| Generate 1 synthetic 7-day pump (30 channels + counterfactuals + labels + snapshot spectra) | ~11 s |
| ML training (LightGBM, 163 k rows, 66 features) | ~24 s |
| **Every pump is independent → perfectly parallel over cores/nodes** | linear scaling |

## Step-by-step sequence

### 0. Ship the repo to LUMI
```bash
# from the repo folder on your PC (Git available):
scp -r . <username>@lumi.csc.fi:/scratch/project_46<YOURS>/<username>/sentry-lumi
# alternatively upload via the Files app: https://www.lumi.csc.fi → Files → Home dir → Upload
```

### 1. Environment setup (once, ~3 min)
In the LUMI web shell (https://www.lumi.csc.fi → "Clusters" → "LUMI Shell"):
```bash
cd /scratch/project_46<YOURS>/<username>/sentry-lumi
bash lumi/setup_env.sh project_46<YOURS> .
```
(The script loads `LUMI/24.03` + `cray-python`, builds `.venv`, and installs numpy scipy pandas
pyarrow pyyaml scikit-learn lightgbm.)

### 2. First submit — GENERATE (one exclusive node, 128 cores)
```bash
sbatch lumi/sbatch_generate.sh        # open the file and replace project/user placeholders first
squeue -u $USER                        # watch the queue
scancel <job-id>                       # if anything goes wrong
```
Expected wall clock: 6000 pumps × ~11 s ÷ 120 workers ≈ **9–12 min** once running.
Output: `/scratch/project_46<YOURS>/<user>/shards/` ≈ 2–6 GB total (no raw telemetry).

### 3. Second submit — TRAIN (small partition, 64 cores, billed by usage)
```bash
sbatch lumi/sbatch_train.sh
```
Expected wall clock: a few minutes. Output: `mlmodel/` (lgb_model.txt, bundle.pkl, report.json).
*Before scoring against the challenge scorer, the model bundle must be downloaded back to the
laptop (or apply inside LUMI via a third short job).*

### 4. Back at home, rebuild the trained SENTRY-ML stream & score
```bash
python sentry/lumi_train.py apply --model build/mlmodel --data data/full \
    --assets PUMP-08 PUMP-09 --out build/predictions_ml_validation.csv
python -m retrofit_sim score --predictions build/predictions_ml_validation.csv \
    --events data/full/events_validation.csv --assets data/full/assets.csv \
    --benign data/full/benign_windows_train_validation.csv --split validation
```
Compare against the rules-only SENTRY result (87.7).

## LUMI first-time notes

- **Billing** — check with `lumi-allocations` or `lumi-workspaces` (login node). CPU usage is
  billed in **core-hours**: the standard partition is charged 128 core-h per hour for a whole
  node even if your job uses fewer; use `small` for partial-node jobs.
- **Storage** — `/scratch` quota; check with `csc-workspaces`. Delete old shards regularly.
- **Module system** — `module load LUMI/24.03` first, then `cray-python`. Don't pip-install into
  the system Python; always use the `.venv` created by the setup script. Never rely on
  `--system-site-packages`.
- **The three *_NUM_THREADS=1 lines matter** — LightGBM/NumPy on 128 concurrent workers would try
  multithreading inside each worker and completely thrash the node.
- **Never tune on the hidden test assets.** Training data comes from your own synthetic shards.
  The official scorer runs at `python -m retrofit_sim score ...` for validation only; test
  predictions are a frozen one-shot output.
- **Job limits** — `standard` walltime max 2 days (bench/gen typically minutes anyway).
- **Puhuri** — if your allocation is via Puhuri, quota echo appears with a delay in
  `lumi-workspaces`; don't panic if the numbers lag.

## What to keep in mind about the trained model

- Over-fitting concern: the trained diagnosis head learns the *generator's* fingerprints.
  The rules+physics backbone (SENTRY) stays as the primary alert system; the trained classifier
  is a diagnosis head on top of physics-aligned features, therefore interpretable and more
  defensible for the jury.
