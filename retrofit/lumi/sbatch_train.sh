#!/bin/bash
#SBATCH --job-name=sentry-train
#SBATCH --account=project_46XXXXXXX
#SBATCH --partition=small                     # by-resource: you pay only for what you request
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=112G                            # small partition per-core memory cap
#SBATCH --time=02:00:00
#SBATCH --output=logs/train_%j.out

cd /scratch/project_46XXXXXXX/<user>/since_ai_2026/retrofit    # bootstrap rewrites $ACCOUNT and $USER
source .venv/bin/activate
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK

mkdir -p logs
srun python sentry/lumi_train.py fit \
    --shards /scratch/project_46XXXXXXX/<user>/shards \
    --out /scratch/project_46XXXXXXX/<user>/mlmodel \
    --threads $SLURM_CPUS_PER_TASK
