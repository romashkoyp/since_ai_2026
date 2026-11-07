#!/bin/bash
#SBATCH --job-name=sentry-gen
#SBATCH --account=project_46XXXXXXX           # <- your project number from lumi.csc.fi
#SBATCH --partition=standard                  # exclusive node, billed 128 core-h per hour
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=128
#SBATCH --mem=224G
#SBATCH --time=01:30:00
#SBATCH --output=logs/gen_%j.out

cd /scratch/project_46XXXXXXX/<user>/since_ai_2026/retrofit    # bootstrap rewrites $ACCOUNT and $USER
source .venv/bin/activate

# 1 thread per worker process is critical: 128 workers * N BLAS threads would thrash the node
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

mkdir -p logs
srun python sentry/lumi_generate.py \
    --n-pumps 6000 --seed-base 200000 \
    --workers 120 --shard-size 50 --healthy-frac 0.3 \
    --out /scratch/project_46XXXXXXX/<user>/shards
