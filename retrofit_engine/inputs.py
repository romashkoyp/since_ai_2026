"""Turning uploaded files into the tables the engine needs."""
from __future__ import annotations

import io
import json

import numpy as np
import pandas as pd

from ._vendor.minute_features import FEATURE_CHANNELS, features_1min
from .config import ASSET_DEFAULTS, CONTROLS, MIN_HISTORY_HOURS, REQUIRED_ASSET_COLUMNS

UTC_NS = "datetime64[ns, UTC]"


def ts(s):
    """parse to UTC with one fixed resolution (mixed resolutions break pandas merges)"""
    return pd.to_datetime(s, utc=True, format="ISO8601").astype(UTC_NS)


def read_table(data, filename: str = "") -> pd.DataFrame:
    """CSV, parquet or JSON (list of records) from bytes, a path or a file-like object."""
    name = str(filename or (data if isinstance(data, str) else "")).lower()
    if isinstance(data, (bytes, bytearray)):
        data = io.BytesIO(data)
    if name.endswith(".parquet"):
        return pd.read_parquet(data)
    if name.endswith(".json"):
        raw = data.read() if hasattr(data, "read") else open(data, "rb").read()
        return pd.DataFrame(json.loads(raw))
    return pd.read_csv(data)


# ------------------------------------------------------------------ telemetry
def is_minute_format(df: pd.DataFrame) -> bool:
    return "window_start_utc" in df and any(c.endswith("__mean") for c in df.columns)


def to_minutes(df: pd.DataFrame, datasheet: pd.DataFrame | None, label: str, notes: list) -> pd.DataFrame:
    """accept raw readings (any rate) or ready 1-minute summaries; return 1-minute summaries"""
    if df is None or df.empty:
        raise ValueError(f"{label}: file is empty")
    if is_minute_format(df):
        out = df.copy()
    else:
        if "asset_id" not in df or "timestamp_utc" not in df:
            raise ValueError(f"{label}: needs columns 'asset_id' and 'timestamp_utc' (raw readings) "
                             f"or 'asset_id', 'window_start_utc' and '<sensor>__mean' columns (1-minute summaries)")
        raw = df.copy()
        raw["timestamp_utc"] = pd.to_datetime(raw["timestamp_utc"], utc=True, format="ISO8601")
        known = [c for c in FEATURE_CHANNELS if c in raw]
        if not known:
            raise ValueError(f"{label}: no known sensor columns; expected some of {FEATURE_CHANNELS}")
        for c in FEATURE_CHANNELS:
            raw[c] = pd.to_numeric(raw[c], errors="coerce").astype("float32") if c in raw else np.float32("nan")
        if "operating_mode" not in raw:
            rated = None
            if datasheet is not None and "motor_rated_current_a" in datasheet and datasheet["motor_rated_current_a"].notna().all():
                rated = raw["asset_id"].map(dict(zip(datasheet.asset_id, datasheet.motor_rated_current_a)))
            thr = 0.1 * rated if rated is not None else 1.0
            raw["operating_mode"] = np.where((raw["motor_current_a"] > thr) | (raw["motor_speed_rpm"] > 50), "RUNNING", "STOPPED")
            notes.append(f"{label}: no operating_mode column, derived from motor current / speed")
        raw["quality_flags"] = pd.to_numeric(raw.get("quality_flags", 0), errors="coerce").fillna(0).astype("int64") \
            if "quality_flags" in raw else 0
        out = features_1min(raw.sort_values(["asset_id", "timestamp_utc"]))
        notes.append(f"{label}: raw readings aggregated to 1-minute summaries")
    out["window_start_utc"] = ts(out["window_start_utc"])
    out["asset_id"] = out["asset_id"].astype(str)
    return out.sort_values(["asset_id", "window_start_utc"]).reset_index(drop=True)


def merge_baseline(baseline: pd.DataFrame | None, telemetry: pd.DataFrame, notes: list):
    """Put the baseline period in front of the monitored data. Returns (combined, monitored_from per pump)."""
    mon_from = telemetry.groupby("asset_id")["window_start_utc"].min()
    if baseline is None:
        notes.append(f"no baseline file: the first ~{MIN_HISTORY_HOURS} h of steady running in the telemetry are "
                     f"used as each pump's normal; alerts start after that")
        return telemetry, None
    b_end = baseline.groupby("asset_id")["window_start_utc"].max() + pd.Timedelta(minutes=1)
    tele = telemetry.copy()
    cut = tele["asset_id"].map(b_end)
    overlap = cut.notna() & (tele["window_start_utc"] < cut)
    if overlap.any():
        notes.append(f"telemetry overlapping the baseline period was ignored ({int(overlap.sum())} minutes)")
        tele = tele[~overlap]
    for a in sorted(set(tele.asset_id) - set(baseline.asset_id)):
        notes.append(f"{a}: no baseline rows; its first ~{MIN_HISTORY_HOURS} h of telemetry are used as normal")
    for a, g in baseline.groupby("asset_id"):
        run_h = float((g.get("running_fraction", pd.Series(1.0, index=g.index)) >= 0.99).sum()) / 60
        if run_h < MIN_HISTORY_HOURS:
            notes.append(f"{a}: baseline has only {run_h:.1f} h of steady running (want >= {MIN_HISTORY_HOURS} h); "
                         f"the start of the monitored data also counts as normal")
    combined = pd.concat([baseline, tele], ignore_index=True).sort_values(["asset_id", "window_start_utc"])
    mon_from = tele.groupby("asset_id")["window_start_utc"].min()
    return combined.reset_index(drop=True), mon_from


# ------------------------------------------------------------------ datasheet
def tier_from_channels(ch: str) -> str:
    s = set(str(ch).split("|"))
    if "vibration_rms_mm_s" not in s and "suction_pressure_kpa" not in s:
        return "T0_LEGACY"
    if "flow_m3_h" in s or "motor_winding_temp_c" in s:
        return "T2_FULL"
    return "T1_RETROFIT"


def prepare_datasheet(sheet: pd.DataFrame, feat: pd.DataFrame, notes: list) -> pd.DataFrame:
    a = sheet.copy()
    a.columns = [c.strip() for c in a.columns]
    missing = [c for c in REQUIRED_ASSET_COLUMNS if c not in a]
    if missing:
        raise ValueError(f"datasheet is missing columns {missing}; required: {REQUIRED_ASSET_COLUMNS}")
    a["asset_id"] = a["asset_id"].astype(str)
    a["control"] = a["control"].astype(str).str.strip().str.upper()
    bad = sorted(set(a["control"]) - CONTROLS)
    if bad:
        raise ValueError(f"datasheet: unknown control type(s) {bad}; allowed {sorted(CONTROLS)}")
    for c in REQUIRED_ASSET_COLUMNS[2:]:
        if c != "fluid":
            a[c] = pd.to_numeric(a[c], errors="coerce")
            if a[c].isna().any():
                raise ValueError(f"datasheet: '{c}' must be a number for every pump")
    for c, v in ASSET_DEFAULTS.items():
        if c not in a:
            a[c] = v
            if v is not None and c != "split":
                notes.append(f"datasheet: '{c}' not given, default {v} used")
    derived = {}
    for aid, g in feat.groupby("asset_id"):
        derived[aid] = "|".join(sorted(c for c in FEATURE_CHANNELS if f"{c}__mean" in g and g[f"{c}__mean"].notna().any()))
    if "channels_available" not in a:
        a["channels_available"] = a["asset_id"].map(derived)
    else:
        a["channels_available"] = a["channels_available"].fillna(a["asset_id"].map(derived))
    if "instrumentation_tier" not in a:
        a["instrumentation_tier"] = a["channels_available"].map(tier_from_channels)
        notes.append("datasheet: instrumentation_tier derived from the sensors present in the telemetry")
    rng = feat.groupby("asset_id")["window_start_utc"].agg(["min", "max"])
    a["window_start_utc"] = a["asset_id"].map(rng["min"]).astype(str)
    a["window_end_utc"] = a["asset_id"].map(rng["max"] + pd.Timedelta(minutes=1)).astype(str)
    no_data = sorted(set(a["asset_id"]) - set(feat["asset_id"]))
    if no_data:
        notes.append(f"datasheet pumps without telemetry (skipped): {no_data}")
    no_sheet = sorted(set(feat["asset_id"]) - set(a["asset_id"]))
    if no_sheet:
        notes.append(f"telemetry pumps without a datasheet row (skipped): {no_sheet}")
    return a[a["asset_id"].isin(feat["asset_id"])].reset_index(drop=True)
