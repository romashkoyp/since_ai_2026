# Vendored from the RETROFIT AI 2026 benchmark (src/retrofit_sim/dataset.py, features_1min), MIT License,
# Since AI Hackathon 2026. Turns raw readings (e.g. 1 Hz) into the 1-minute summaries the models use.
import numpy as np
import pandas as pd

FEATURE_CHANNELS = ["motor_speed_rpm", "motor_current_a", "motor_power_kw", "suction_pressure_kpa",
                    "discharge_pressure_kpa", "flow_m3_h", "fluid_temp_c", "bearing_temp_c", "motor_winding_temp_c",
                    "vibration_rms_mm_s", "vibration_accel_rms_g", "vibration_crest_factor", "ambient_temp_c",
                    "valve_position_pct"]


def features_1min(tele: pd.DataFrame) -> pd.DataFrame:
    df = tele.copy()
    df["minute"] = df["timestamp_utc"].dt.floor("min")
    g = df.groupby(["asset_id", "minute"], observed=True, sort=True)
    parts = []
    for c in FEATURE_CHANNELS:
        if df[c].notna().any():
            agg = g[c].agg(["mean", "std", "min", "max", "count"])
            agg.columns = [f"{c}__{s}" for s in agg.columns]
            parts.append(agg.astype({f"{c}__count": "int16"}))
    out = pd.concat(parts, axis=1)
    out["operating_mode"] = _group_mode(df, ["asset_id", "minute"], "operating_mode").values
    out["running_fraction"] = (df["operating_mode"] == "RUNNING").groupby(
        [df["asset_id"], df["minute"]], observed=True).mean().astype("float32").values
    out["quality_any"] = _group_or(df, ["asset_id", "minute"], "quality_flags").values
    out["rows"] = g.size().astype("int16").values
    out = out.reset_index().rename(columns={"minute": "window_start_utc"})
    for c in out.columns:
        if out[c].dtype == "float64":
            out[c] = out[c].astype("float32")
    return out


def _group_mode(df, keys, col):
    d = pd.get_dummies(df[col].astype(str))
    for k in keys:
        d[k] = df[k].values
    return d.groupby(keys, observed=True, sort=True).sum().idxmax(axis=1)


def _group_or(df, keys, col):
    q = df[col].astype(np.int64)
    acc = None
    for bit in (1, 2, 4, 8, 16):
        b = ((q & bit) > 0).groupby([df[k] for k in keys], observed=True, sort=True).max().astype(np.int16) * bit
        acc = b if acc is None else acc + b
    return acc.astype("int16")
