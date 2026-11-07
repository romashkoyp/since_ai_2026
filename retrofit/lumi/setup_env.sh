#!/bin/bash
# LUMI environment setup for SENTRY generation + LightGBM training.
# Run once on a LUMI login node (or in the Open OnDemand web shell).
set -e
PROJ=${1:?usage: bash lumi/setup_env.sh project_46XXXXXXX /scratch/project_46XXXXXXX/<user>/sentry-lumi}
SRC=${2:?}
cd "$SRC"

module load LUMI/24.03 2>/dev/null || module load LUMI 2>/dev/null || true
module load partition/C 2>/dev/null || true
module load cray-python 2>/dev/null || module load Python 2>/dev/null || true

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install numpy scipy pandas pyarrow pyyaml scikit-learn lightgbm

python - <<'LAG'
import numpy, scipy, pandas, pyarrow, lightgbm
print("env OK:", numpy.__version__, scipy.__version__, pandas.__version__, pyarrow.__version__, lightgbm.__version__)
LAG
echo "Setup done in $SRC. Verify: source .venv/bin/activate && python -c 'import lightgbm'"
