"""Make the files for the dashboard's "Analyse data" dialog from a RETROFIT dataset folder.

Same data as retrofit_engine/tools/make_demo_files.py, but smaller and complete:
  * Parquet by default (1-minute summaries, identical model results, ~3-4x smaller than CSV;
    e.g. 9 pumps x 7 days: 55 MB as CSV -> ~22 MB). Keep 1-minute rows: the detector needs them
    (15-minute persistence, per-minute data-gap checks, 24 h baseline of steady minutes).
  * all pumps unless --pumps is given
  * events.csv: the known faults for those pumps (train + validation merged) -> Correct / Wrong in the UI

    cd server
    python -m scripts.make_upload_files --data /tmp/retrofit_full/public --out ~/Desktop/zerofault_upload
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DATASHEET_COLUMNS = ["asset_id", "control", "motor_rated_rpm", "pump_rated_flow_m3_h", "pump_rated_head_m",
                     "pump_shutoff_head_m", "npsh3_at_bep_m", "fluid", "motor_rated_current_a", "motor_rated_kw",
                     "profile", "bearing_bpfo_order", "impeller_vanes", "vibration_alarm_mm_s", "min_speed_ratio",
                     "site", "system"]
# dialog field -> file written
FIELDS = {"Pump datasheet": "datasheet.csv", "Telemetry to check": "telemetry", "Healthy baseline": "baseline",
          "Operating context": "context", "Vibration snapshots": "snapshots.parquet",
          "Known faults (to score)": "events.csv"}


def _size(n: int) -> str:
    """decimal units, like Finder and the upload dialog"""
    return f"{n} bytes" if n < 1000 else f"{n / 1e3:.0f} KB" if n < 999_500 else f"{n / 1e6:.1f} MB"


def _write(df: pd.DataFrame, path_no_ext: Path, fmt: str) -> Path:
    if fmt == "parquet":
        path = path_no_ext.with_suffix(".parquet")
        df.to_parquet(path, index=False, compression="zstd")
    else:
        path = path_no_ext.with_suffix(".csv")
        df.to_csv(path, index=False)
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, type=Path, help="dataset folder with assets.csv and features_1min.parquet")
    p.add_argument("--out", required=True, type=Path, help="output folder (created if missing)")
    p.add_argument("--pumps", nargs="*", help="asset IDs to include (default: every pump in the dataset)")
    p.add_argument("--baseline-hours", type=float, default=30.0,
                   help="first N hours per pump go to the baseline file (needs >= 24 h of steady running)")
    p.add_argument("--format", choices=["parquet", "csv"], default="parquet",
                   help="telemetry / baseline / context format (default parquet: same data, much smaller)")
    a = p.parse_args()
    d, out = a.data.expanduser(), a.out.expanduser()
    out.mkdir(parents=True, exist_ok=True)

    assets = pd.read_csv(d / "assets.csv")
    pumps = a.pumps or sorted(assets["asset_id"])
    unknown = sorted(set(pumps) - set(assets["asset_id"]))
    if unknown:
        raise SystemExit(f"not in {d / 'assets.csv'}: {unknown}")
    assets = assets[assets["asset_id"].isin(pumps)]
    written: dict[str, Path] = {}

    sheet = assets[[c for c in DATASHEET_COLUMNS if c in assets]]
    written["Pump datasheet"] = out / "datasheet.csv"
    sheet.to_csv(written["Pump datasheet"], index=False)

    feats = pd.read_parquet(d / "features_1min.parquet")
    feats = feats[feats["asset_id"].isin(pumps)].copy()
    feats["window_start_utc"] = pd.to_datetime(feats["window_start_utc"], utc=True)
    start = feats.groupby("asset_id")["window_start_utc"].transform("min")
    is_base = feats["window_start_utc"] < start + pd.Timedelta(hours=a.baseline_hours)
    iso = lambda df: df.assign(window_start_utc=df["window_start_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    written["Healthy baseline"] = _write(iso(feats[is_base]), out / "baseline", a.format)
    written["Telemetry to check"] = _write(iso(feats[~is_base]), out / "telemetry", a.format)

    ctx_file = d / "operating_context.csv"
    if ctx_file.exists():
        ctx = pd.read_csv(ctx_file)
        written["Operating context"] = _write(ctx[ctx["asset_id"].isin(pumps)], out / "context", a.format)

    snap_file = d / "vibration_snapshots.parquet"
    if snap_file.exists():
        snaps = pd.read_parquet(snap_file)
        snaps = snaps[snaps["asset_id"].isin(pumps)]
        if len(snaps):
            written["Vibration snapshots"] = out / "snapshots.parquet"
            snaps.to_parquet(written["Vibration snapshots"], index=False)

    event_files = [f for f in (d / "events_train.csv", d / "events_validation.csv") if f.exists()]
    if event_files:
        events = pd.concat([pd.read_csv(f) for f in event_files], ignore_index=True)
        written["Known faults (to score)"] = out / "events.csv"
        events[events["asset_id"].isin(pumps)].to_csv(written["Known faults (to score)"], index=False)

    total = sum(f.stat().st_size for f in written.values())
    print(f"{len(pumps)} pumps -> {out}  ({_size(total)} in total)\n")
    print(f"{'Upload dialog field':28s} {'file':22s} size")
    for field in FIELDS:
        if field in written:
            f = written[field]
            print(f"{field:28s} {f.name:22s} {_size(f.stat().st_size):>9s}")


if __name__ == "__main__":
    main()
