"""Build server/seed/demo_run.json: the model run the dashboard shows before anyone uploads data.

Runs the same code path as POST /api/analyses on a RETROFIT dataset folder (the organisers' data/full, or one made
by the simulator: `python retrofit/make_dataset.py --tier full --output <dir>` -> use <dir>/public).

    cd server
    python -m scripts.build_seed_run --data <dataset>/public
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.analysis import AnalysisInputs, run_analysis
from src.settings import SERVER_DIR, get_settings


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, type=Path, help="folder with assets.csv and features_1min.parquet")
    p.add_argument("--pumps", nargs="*", help="subset of asset IDs (default: all)")
    p.add_argument("--baseline-hours", type=float, default=30.0,
                   help="first N hours per pump become the baseline (needs >= 24 h of steady running)")
    p.add_argument("--out", type=Path, default=SERVER_DIR / "seed" / "demo_run.json")
    a = p.parse_args()

    d = a.data
    assets = pd.read_csv(d / "assets.csv")
    feats = pd.read_parquet(d / "features_1min.parquet")
    feats["window_start_utc"] = pd.to_datetime(feats["window_start_utc"], utc=True)
    if a.pumps:
        assets, feats = assets[assets.asset_id.isin(a.pumps)], feats[feats.asset_id.isin(a.pumps)]

    start = feats.groupby("asset_id")["window_start_utc"].transform("min")
    is_base = feats["window_start_utc"] < start + pd.Timedelta(hours=a.baseline_hours)
    optional = {
        "context": d / "operating_context.csv",
        "snapshots": d / "vibration_snapshots.parquet",
    }
    extra = {k: (pd.read_parquet(f) if f.suffix == ".parquet" else pd.read_csv(f)) for k, f in optional.items()
             if f.exists()}
    event_files = [f for f in (d / "events_train.csv", d / "events_validation.csv") if f.exists()]
    events = pd.concat([pd.read_csv(f) for f in event_files], ignore_index=True) if event_files else None

    record = run_analysis(
        AnalysisInputs(datasheet=assets, telemetry=feats[~is_base], baseline=feats[is_base], events=events, **extra),
        get_settings(), source="seed", label=f"demo dataset ({d.parent.name or d.name})",
    )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(record.model_dump(mode="json"), separators=(",", ":")), encoding="utf-8")
    s = record.summary
    correct = sum(1 for x in record.alerts if x.correct)
    print(f"{a.out}: {s.pumps} pumps, {s.alerts} alerts ({correct} match ground truth), "
          f"{s.ml_overrides} ML overrides, {a.out.stat().st_size / 1e6:.2f} MB")
    for note in s.notes:
        print("  note:", note)


if __name__ == "__main__":
    main()
