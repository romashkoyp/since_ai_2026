# SENTRY runner: builds per-asset detector inputs, runs the engine, writes prediction CSVs.
import argparse
import os

import numpy as np
import pandas as pd

from .detect import AssetSentry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_split(data_root: str, split: str, tier: str = ""):
    data = os.path.join(data_root, tier) if tier else data_root
    assets = pd.read_csv(os.path.join(data, "assets.csv"))
    assets = assets[assets.split == split]
    feats = None
    if tier == "full" or os.path.isdir(os.path.join(data, "telemetry")):
        feats = pd.read_parquet(os.path.join(data, "features_1min.parquet"))
        feats["window_start_utc"] = pd.to_datetime(feats["window_start_utc"])
    ctx = pd.read_csv(os.path.join(data, "operating_context.csv"))
    snap = None
    snap_path = os.path.join(data, "vibration_snapshots.parquet")
    if os.path.exists(snap_path):
        snap = pd.read_parquet(snap_path)
    return assets, feats, ctx, snap


def run_asset(asset_row, feats, ctx, snap) -> pd.DataFrame:
    aid = asset_row.asset_id
    f = feats[feats.asset_id == aid].sort_values("window_start_utc").set_index("window_start_utc")
    context = ctx[ctx.asset_id == aid]
    s = None
    if snap is not None:
        s = snap[snap.asset_id == aid]
        if len(s) == 0:
            s = None
    engine = AssetSentry(asset_row, f, context, snap_df=s, ffill_sparse=90)
    return engine.run()


def run_split(split: str, out_csv: str, data_root: str):
    assets, feats, ctx, snap = load_split(data_root, split)
    frames = []
    for _, row in assets.iterrows():
        print("running", row.asset_id, f"tier={row.instrumentation_tier} control={row.control}", flush=True)
        df = run_asset(row, feats, ctx, snap)
        frames.append(df)
        print(f"  -> {len(df)} alerts", flush=True)
    out = pd.concat(frames, ignore_index=True) if len(frames) else pd.DataFrame(
        columns=["asset_id", "alert_time_utc", "event_class", "fault_type", "confidence", "evidence", "recommended_action"])
    out.to_csv(out_csv, index=False)
    print("saved", out_csv, len(out), "alerts")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "full"))
    ap.add_argument("--split", required=True, choices=["train", "validation", "test"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    run_split(args.split, args.out, args.data)
