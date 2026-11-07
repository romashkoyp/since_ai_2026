#!/bin/bash
# One-command LUMI bootstrap for the SENTRY synthetic-data + training pipeline.
#
# Usage (from ANY LUMI shell, login node or compute shell — no need to be inside the repo yet):
#   export GITHUB_TOKEN=ghp_xxx        # a GitHub personal access token with repo read scope
#   bash retrofit/lumi/bootstrap_lumi.sh project_462001520
#
# What it does:
#   1. creates your scratch work dir /scratch/$ACCOUNT/$USER
#   2. clones (or updates) the TEAM repo `romashkoyp/since_ai_2026` there
#   3. builds the Python venv and installs deps inside `retrofit/` (skipped if already present)
#   4. rewrites the SLURM scripts with your project/user paths
#   5. submits the generation job (sbatch) and prints the job id + how to monitor
set -euo pipefail

ACCOUNT=${1:?usage: bash retrofit/lumi/bootstrap_lumi.sh project_462001520  (and GITHUB_TOKEN env if cloning fresh)}
REPO_URL=${REPO_URL:-https://github.com/romashkoyp/since_ai_2026.git}
SUBDIR=${SUBDIR:-retrofit}
WORK=/scratch/$ACCOUNT/$USER
BRANCH=${BRANCH:-main}

echo "[bootstrap] user=$USER account=$ACCOUNT work=$WORK repo=$REPO_URL subdir=$SUBDIR"
mkdir -p "$WORK"

if [ -d "$WORK/since_ai_2026/.git" ]; then
  echo "[bootstrap] repo exists, pulling latest ..."
  git -C "$WORK/since_ai_2026" fetch --all -q || true
  git -C "$WORK/since_ai_2026" reset --hard "origin/$BRANCH" -q
else
  if [ -z "${GITHUB_TOKEN:-}" ]; then
    read -rp "GitHub personal access token (only needed once): " GITHUB_TOKEN
  fi
  echo "[bootstrap] cloning $REPO_URL ..."
  git clone "https://${GITHUB_TOKEN}@${REPO_URL#https://}" "$WORK/since_ai_2026"
fi
cd "$WORK/since_ai_2026/$SUBDIR"

echo "[bootstrap] environment setup ..."
if [ ! -x .venv/bin/python ]; then
  bash lumi/setup_env.sh "$ACCOUNT" "$PWD"
else
  echo "[bootstrap] venv already present, skipping"
fi

echo "[bootstrap] rewriting SLURM scripts for account $ACCOUNT ..."
sed -i "s|project_46XXXXXXX|$ACCOUNT|g; s|/scratch/project_46XXXXXXX/<user>|$WORK|g" \
    lumi/sbatch_generate.sh lumi/sbatch_train.sh
mkdir -p logs

echo "[bootstrap] submitting GENERATION job ..."
GEN_ID=$(sbatch --parsable lumi/sbatch_generate.sh)
echo "  generation job id: $GEN_ID   (check: squeue -u $USER)"

cat <<'NEXT'

Next steps:
  squeue -u $USER                     # watch the queue; 'R' means running
  tail -f logs/gen_<jobid>.out        # progress output (use 'ls -t logs' to find it)
  when it finishes: sbatch lumi/sbatch_train.sh
NEXT
echo "[bootstrap] done."
