# SENTRY module: causal regime-normalised residuals per channel.
# Baseline = rolling 12 h robust median + MAD per speed regime, computed causally
# (3-min buckets, RUNNING minutes only). MADs are floored by the documented instrument
# noise (TECHNICAL_MODEL §10: pressure 0.25 % span, current 0.4 % of 0-2x rated, etc.)
# because bucket-count smallness can collapse a raw MAD toward 0 (wireless sparse channels).
import numpy as np
import pandas as pd

BUCKET = "3min"
BUCKETS_PER_BASE = 240  # 12 h of 3-min buckets
MIN_BUCKETS = 24        # 72 min of buckets before baseline trusted
Z_CAP = 50.0

# absolute noise floors [channel units]. Keyed by channel name.
NOISE_FLOOR = {
    "discharge_pressure_kpa": 4.0,     # 0.25 % of 1600 kPa span
    "suction_pressure_kpa": 1.75,      # 0.25 % of 700 kPa span
    "flow_m3_h": None,                 # 0.5 % of BEP flow (needs q_bep)
    "motor_current_a": None,           # 0.4 % of 0-2x rated (needs rated current)
    "motor_power_kw": None,            # 0.4 % of 0-2x rated (needs rated kW)
    "motor_speed_rpm": 5.0,
    "fluid_temp_c": 0.3,
    "bearing_temp_c": 0.25,
    "motor_winding_temp_c": 0.3,
    "ambient_temp_c": 0.3,
    "vibration_rms_mm_s": 0.03,
    "vibration_accel_rms_g": 0.005,
    "vibration_crest_factor": 0.05,
    "valve_position_pct": 0.3,
}


def noise_floor_for(channel: str, asset_row) -> float:
    if channel in NOISE_FLOOR:
        v = NOISE_FLOOR[channel]
        if v is not None:
            return v
    if channel == "flow_m3_h":
        return 0.005 * float(asset_row.pump_rated_flow_m3_h)
    if channel == "motor_current_a":
        return 0.008 * float(asset_row.motor_rated_current_a)
    if channel == "motor_power_kw":
        return 0.008 * float(asset_row.motor_rated_kw)
    return 0.3


def _bucketize(t_1min, x, valid, bin_codes):
    df = pd.DataFrame({"t": t_1min, "x": x, "v": valid, "b": bin_codes})
    df = df[df.v & (df.b >= 0)]
    if len(df) == 0:
        return None
    pb = df.groupby([df.t.dt.floor(BUCKET), "b"])["x"].median().reset_index()
    pb.columns = ["t", "b", "x"]
    return pb


def baseline_series(x_1min, valid_1min, r_1min, t_1min, rated_rpm, use_bins=True):
    """Return (med, mad) 1-min arrays for one channel, regime-conditioned, causal."""
    n = len(x_1min)
    med = np.full(n, np.nan)
    mad = np.full(n, np.nan)
    if valid_1min.sum() < 30:
        return med, mad
    if use_bins and rated_rpm and rated_rpm > 0 and np.isfinite(r_1min[valid_1min]).any() and np.nanmax(r_1min) > 0:
        qs = np.nanquantile(r_1min[valid_1min], [0.25, 0.5, 0.75])
        bins = np.searchsorted(qs, r_1min)
        bin_codes = np.where(valid_1min, bins, -1)
    else:
        bin_codes = np.where(valid_1min, 0, -1)
    buckets = _bucketize(t_1min, x_1min, valid_1min, bin_codes)
    if buckets is None or len(buckets) < MIN_BUCKETS:
        xv = np.where(valid_1min, x_1min, np.nan)
        med = pd.Series(xv).expanding(min_periods=45).median().values
        mad = pd.Series(np.abs(xv - med)).expanding(min_periods=45).median().values * 1.4826
        return med, mad
    tt = pd.DatetimeIndex(t_1min)
    for b, g in buckets.groupby("b"):
        s = g.set_index("t")["x"].sort_index()
        win = s.rolling(BUCKETS_PER_BASE, min_periods=MIN_BUCKETS)
        m = win.median()
        d = (s - m).abs().rolling(BUCKETS_PER_BASE, min_periods=MIN_BUCKETS).median() * 1.4826
        mask = bin_codes == b
        mm = m.reindex(tt.union(m.index)).sort_index().ffill(limit=BUCKETS_PER_BASE).reindex(tt)
        dd = d.reindex(tt.union(d.index)).sort_index().ffill(limit=BUCKETS_PER_BASE).reindex(tt)
        med[mask] = mm.values[mask]
        mad[mask] = dd.values[mask]
    return med, mad


def build_residuals(feats: pd.DataFrame, channels, asset_row, ffill_sparse=0):
    """Causal regime residuals z per channel. feats: index = 1-min timestamps."""
    rated_rpm = float(asset_row.motor_rated_rpm)
    q_bep = float(asset_row.pump_rated_flow_m3_h)
    run = (feats["operating_mode"] == "RUNNING") & (feats["running_fraction"] > 0.9) & (feats["rows"] >= 55)
    speed_col = "motor_speed_rpm__mean"
    has_speed = speed_col in feats.columns and feats[speed_col].notna().sum() > 500
    r = (feats[speed_col] / rated_rpm).values.astype(float) if has_speed else np.zeros(len(feats))
    # speed-condition bins fail when speed pinned at minimum (cold seawater): fall back on spread
    t = feats.index
    out = pd.DataFrame(index=feats.index)
    for c in channels:
        col = f"{c}__mean"
        if col not in feats.columns:
            continue
        x = feats[col].values.astype(float)
        valid = run.values & ~np.isnan(x)
        m, d = baseline_series(x, valid, r, t, rated_rpm)
        floor = noise_floor_for(c, asset_row)
        # deterministic binary channels never from this: make sure floor >= reading scale
        sig = np.maximum(d, floor)
        z = np.clip((x - m) / np.maximum(sig, 1e-9), -Z_CAP, Z_CAP)
        out[f"{c}__z"] = z
        out[f"{c}__mad"] = sig
        out[f"{c}__lvl"] = m
    if ffill_sparse:
        for c in channels:
            col = f"{c}__z"
            if col in out.columns:
                out[col] = out[col].ffill(limit=ffill_sparse)
    return out


def rolling_noise_ratio(feats, res, channel: str, win=60):
    """Rolling mean of per-minute std / noise-floor MAD (res = residuals frame)."""
    col_s = f"{channel}__std"
    if col_s not in feats.columns or f"{channel}__mad" not in res.columns:
        return None
    noise = res[f"{channel}__mad"].values
    spread = feats[col_s].rolling(win, min_periods=max(6, win // 4)).mean().values
    return spread / np.maximum(noise, 1e-9)


def frozen_range_units(feats, res, channel: str, win=60):
    """Max-min of channel mean over last win minutes in noise-floor units (res = residuals)."""
    if f"{channel}__mean" not in feats.columns or f"{channel}__mad" not in res.columns:
        return None
    x = feats[f"{channel}__mean"]
    rng = x.rolling(win, min_periods=max(8, win // 6)).max() - x.rolling(win, min_periods=1).min()
    return (rng / np.maximum(res[f"{channel}__mad"].values, 1e-9)).values
    """Max-min of channel mean over last win minutes, in noise-floor units."""
    if f"{channel}__mean" not in feats.columns:
        return None
    x = feats[f"{channel}__mean"]
    rng = x.rolling(win, min_periods=max(8, win // 6)).max() - x.rolling(win, min_periods=1).min()
    return (rng / np.maximum(feats[f"{channel}__mad"].values, 1e-9)).values
