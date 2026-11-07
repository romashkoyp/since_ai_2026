"""Make upload files for the website demo from the official challenge data.

    python -m retrofit_engine.tools.make_demo_files --data "C:/.../RETROFIT_AI_PARTICIPANTS_2026/data/full" --pumps PUMP-08 PUMP-09 --out demo_files

Writes: datasheet.csv, baseline.csv (first 30 h, so it holds >= 24 h of steady running), telemetry.csv (the rest), context.csv,
        snapshots.parquet (vibration, if any). Telemetry files are 1-minute summaries (small enough to upload);
        add --raw-hours N to also write telemetry_raw.csv with N hours of 1-second readings for one pump.
"""
import argparse, glob
from pathlib import Path

import pandas as pd

p = argparse.ArgumentParser()
p.add_argument("--data", required=True)
p.add_argument("--pumps", nargs="+", default=["PUMP-08", "PUMP-09"])
p.add_argument("--out", default="demo_files")
p.add_argument("--baseline-hours", type=float, default=30)
p.add_argument("--raw-hours", type=float, default=0)
a = p.parse_args()
D, out = Path(a.data), Path(a.out); out.mkdir(parents=True, exist_ok=True)

assets = pd.read_csv(D / "assets.csv"); assets = assets[assets.asset_id.isin(a.pumps)]
keep = ["asset_id", "control", "motor_rated_rpm", "pump_rated_flow_m3_h", "pump_rated_head_m", "pump_shutoff_head_m",
        "npsh3_at_bep_m", "fluid", "motor_rated_current_a", "motor_rated_kw", "profile", "bearing_bpfo_order",
        "impeller_vanes", "site", "system"]
assets[[c for c in keep if c in assets]].to_csv(out / "datasheet.csv", index=False)

f = pd.read_parquet(D / "features_1min.parquet"); f = f[f.asset_id.isin(a.pumps)].copy()
f["window_start_utc"] = pd.to_datetime(f.window_start_utc, utc=True)
start = f.groupby("asset_id").window_start_utc.transform("min")
is_base = f.window_start_utc < start + pd.Timedelta(hours=a.baseline_hours)
fmt = lambda d: d.assign(window_start_utc=d.window_start_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
fmt(f[is_base]).to_csv(out / "baseline.csv", index=False)
fmt(f[~is_base]).to_csv(out / "telemetry.csv", index=False)

c = pd.read_csv(D / "operating_context.csv"); c[c.asset_id.isin(a.pumps)].to_csv(out / "context.csv", index=False)
s = pd.read_parquet(D / "vibration_snapshots.parquet"); s = s[s.asset_id.isin(a.pumps)]
if len(s):
    s.to_parquet(out / "snapshots.parquet", index=False)
if a.raw_hours > 0:
    pump = a.pumps[0]
    r = pd.read_parquet(glob.glob(str(D / "telemetry" / f"asset_id={pump}"))[0]); r.insert(0, "asset_id", pump)
    r = r[r.timestamp_utc < r.timestamp_utc.min() + pd.Timedelta(hours=a.raw_hours)]
    r.assign(timestamp_utc=r.timestamp_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")).drop(
        columns=["sensor_source", "sample_interval_s"], errors="ignore").to_csv(out / "telemetry_raw.csv", index=False)
for fp in sorted(out.iterdir()):
    print(f"{fp.name:22s} {fp.stat().st_size / 1e6:6.1f} MB")
