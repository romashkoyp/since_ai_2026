# SENTRY ML feature builder — shared by lumi_generate.py, lumi_train.py and the
# trained-model inference path, so the feature definition is identical everywhere.
#
# CANONICAL fixed schema across all pumps (missing values = NaN), so every pump's
# feature matrix has exactly the same columns regardless of tier/channel availability.
import numpy as np
import pandas as pd

from .regime import build_residuals, frozen_range_units, rolling_noise_ratio

DEV_CHANNELS = ["suction_pressure_kpa", "motor_current_a", "motor_power_kw",
                "discharge_pressure_kpa", "flow_m3_h"]
SNAP_COLS = ["e_bpfo_snr", "e_bpfi_snr", "s1x", "s2x", "s3x"]
EXCLUDE_RANGE = {"ambient_temp_c"}
FFILL_SNAP_MIN = 480          # snapshots arrive every ~4 h; carry forward twice that


def _canonical_channels():
    from retrofit_sim.generate import ALL_TELEMETRY_COLUMNS
    return [c for c in ALL_TELEMETRY_COLUMNS]


def feature_columns():
    ch = _canonical_channels()
    cols = ["running_fraction", "rows"]
    cols += [f"z_{c}" for c in ch]
    cols += [f"dev2h_{c}" for c in DEV_CHANNELS if c in ch]
    cols += [f"frozenrange_{c}" for c in ch if c not in EXCLUDE_RANGE]
    cols += [f"noiseratio_{c}" for c in ch if c not in EXCLUDE_RANGE]
    cols += [f"snap_{c}" for c in SNAP_COLS]
    cols += ["tier", "control", "profile"]
    return cols


def _dev_series(x_1min, run, index):
    """(rolling 2 h median - rolling trailing 12 h median) per 1-min step."""
    xv = pd.Series(np.where(run, x_1min, np.nan), index=index)
    m2 = xv.rolling(120, min_periods=30).median()
    m12 = xv.rolling(720, min_periods=240).median()
    return (m2 - m12).values


def build_ml_features(asset_row_dict, feats_1min: pd.DataFrame, snap_metrics=None):
    """Build the canonical ML feature frame for one pump.

    asset_row_dict : dict from assets.csv row (needs motor_rated_rpm and ratings)
    feats_1min     : DataFrame indexed by window_start_utc with __mean/__std/__count cols
    snap_metrics   : optional rows from sentry.snapshots.snapshot_metrics(...)
    Returns (features_df, channels)
    """
    arow = pd.Series(asset_row_dict)
    f = feats_1min.sort_index()
    index = f.index
    channels = [c[:-6] for c in f.columns if c.endswith("__mean")]
    res = build_residuals(f, channels, arow, ffill_sparse=90)
    run = ((f["operating_mode"] == "RUNNING") & (f["running_fraction"] > 0.9)
           & (f["rows"] >= 55)).values
    run60 = pd.Series(run.astype(float)).rolling(60, min_periods=10).mean().values >= 0.8

    out = pd.DataFrame(index=index)
    out["running_fraction"] = f["running_fraction"].astype("float32")
    out["rows"] = f["rows"].astype("float32")
    noise = {}
    for c in channels:
        out[f"z_{c}"] = res[f"{c}__z"].values if f"{c}__z" in res.columns else np.nan
        noise[c] = res[f"{c}__mad"].values if f"{c}__mad" in res.columns else None
    for c in DEV_CHANNELS:
        if f"{c}__mean" in f.columns and noise.get(c) is not None:
            x = f[f"{c}__mean"].values.astype(float)
            out[f"dev2h_{c}"] = _dev_series(x, run, index) / np.maximum(noise[c], 1e-9)
    for c in channels:
        if c in EXCLUDE_RANGE:
            continue
        rng = frozen_range_units(f, res, c, win=60)
        if rng is not None:
            out[f"frozenrange_{c}"] = rng
        nr = rolling_noise_ratio(f, res, c, win=60)
        if nr is not None:
            out[f"noiseratio_{c}"] = nr

    # snapshot envelope features carried forward (snapshots every ~4 h, ffill 8 h)
    snap_piece = None
    if snap_metrics is not None and len(snap_metrics):
        sm = snap_metrics.copy()
        sm["window_start_utc"] = pd.to_datetime(sm["timestamp_utc"], utc=True)
        sm = sm.sort_values("window_start_utc").set_index("window_start_utc")
        avail = [c for c in SNAP_COLS if c in sm.columns]
        if avail:
            snap_piece = sm[avail].reindex(index.union(sm.index)).sort_index().ffill(limit=FFILL_SNAP_MIN * 2).reindex(index)
            for c in avail:
                out[f"snap_{c}"] = snap_piece[c].values

    # scalar descriptors (one-hot encoded at training time; never floats!)
    out["tier"] = str(arow.get("instrumentation_tier", "T2_FULL"))
    out["control"] = str(arow.get("control", "FIXED_SPEED"))
    out["profile"] = str(arow.get("profile", "INDUSTRIAL_CW"))

    # canonicalize to the fixed schema (missing channels for this tier -> NaN)
    canon = feature_columns()
    out = out.reindex(columns=canon)
    # keep strings pandas-object, cast everything else float32
    for c in out.columns:
        if out[c].dtype == "float64":
            out[c] = out[c].astype("float32")
    return out, channels


def build_labels(events_df, benign_df, index):
    """Per-minute labels.

    Events use *_ms columns as produced by G.events_for (ISO strings are also accepted).
    gate    : 1 inside the scoring window of a scored event
              [max(onset, detectable-6h) .. end (+30 min for short/perishable/sensor events)]
    label   : fault_type at that minute (earliest active event wins) else NONE/BENIGN
    benign  : 1 inside a benign window and not in any event window
    Machine events with observable=False are excluded (the benchmark excludes them too).
    """
    n = len(index)
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Series(index), utc=True))
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    gate = np.zeros(n, dtype=np.int8)
    lab = np.full(n, "NONE", dtype=object)
    benign = np.zeros(n, dtype=np.int8)
    earliest = [pd.Timestamp("2100-01-01", tz="UTC")] * n

    def put(mask, labv, onset):
        for pos in np.nonzero(mask)[0]:
            if onset < earliest[pos]:
                earliest[pos] = onset
                lab[pos] = labv

    perishable = {"CAVITATION", "AIR_ENTRAINMENT"}

    def ts_of(v):
        if pd.isna(v):
            return None
        return pd.Timestamp(int(v), unit="ms", tz="UTC")

    if events_df is not None and len(events_df):
        for e in events_df.to_dict("records"):
            observable = bool(e.get("observable")) or e.get("event_class") == "SENSOR"
            if not observable:
                continue
            onset = ts_of(e.get("onset_ms")) or (pd.Timestamp(e["onset_utc"], tz="UTC") if e.get("onset_utc") else idx[0])
            det = ts_of(e.get("detectable_ms"))
            end = ts_of(e.get("end_ms")) or (pd.Timestamp(e["end_utc"], tz="UTC") if e.get("end_utc") else idx[-1])
            ws = max(onset, (det - pd.Timedelta("6h")) if det is not None else onset)
            pad = pd.Timedelta("30min") if (e["fault_type"] in perishable or e.get("event_class") == "SENSOR") else pd.Timedelta(0)
            m = (idx >= ws) & (idx <= (end if end is not None else idx[-1]) + pad)
            put(m, e["fault_type"], onset)
            gate[m] = 1
    if benign_df is not None and len(benign_df):
        for b in benign_df.to_dict("records"):
            st = ts_of(b.get("start_ms")) or (pd.Timestamp(b["start_utc"], tz="UTC") if b.get("start_utc") else None)
            en = ts_of(b.get("end_ms")) or (pd.Timestamp(b["end_utc"], tz="UTC") if b.get("end_utc") else idx[-1])
            if st is not None:
                m = (idx >= st) & (idx <= (en if en is not None else idx[-1])) & (gate == 0)
                benign[m] = 1
    lab = np.where((gate == 0) & (benign == 1), "BENIGN", lab)
    return gate, lab, benign
