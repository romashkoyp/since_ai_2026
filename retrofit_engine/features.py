"""Features: identical to the training scripts (build_training_table.py / train_diagnostician.py).
If you change anything here, retrain the model and bump ENGINE_FEATURE_VERSION in config.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
from ._vendor import baselines as B
from scipy.signal import butter, hilbert, sosfiltfilt

from .config import SENSOR_TYPES
from .physics import diag2

UTC_NS = "datetime64[ns, UTC]"
CH = list(B.CH)
LAST_COLS = ([f"z_{c}" for c in CH] + [f"zs_{c}" for c in CH] +
             ["since_start", "prev_stop_min", "speed_ratio", "sea_state_hs_m", "suction_static_head_m",
              "ph_Ht", "ph_q", "ph_fH", "ph_dH", "ph_dP", "ph_dfH", "ph_dfH6h", "ph_sigma", "ph_iP_res",
              "r_bpfo", "r_1x", "r_2x", "r_hf", "b_idx", "r_bidx"])
TREND_COLS = [f"z_{c}" for c in CH] + ["ph_dH", "ph_dP", "ph_dfH", "ph_sigma", "b_idx"]
WINDOWS = (30, 180, 720)
TIERS = ["T0_LEGACY", "T1_RETROFIT", "T2_FULL"]
CONTROLS = ["FIXED_SPEED", "VFD_PRESSURE", "VFD_TEMPERATURE", "FLOW_VALVE"]
META = ["seed_folder", "role", "asset_key", "asset_id", "tier", "t", "sample_kind", "event_id", "label_type", "label_class"]


def class_of(ft: str) -> str:
    return "NONE" if ft == "NO_FAULT" else ("SENSOR" if ft in SENSOR_TYPES else "MACHINE")


# ------------------------------------------------------------------ vibration snapshots (Joice's code)
def vibration_features(snaps: pd.DataFrame | None, assets: pd.DataFrame) -> pd.DataFrame:
    cols = ["asset_id", "time", "rpm", "a_1x", "a_2x", "a_vane", "env_bpfo", "hf_rms", "crest"]
    if snaps is None or len(snaps) == 0:
        return pd.DataFrame(columns=cols)
    A = assets.set_index("asset_id")

    def amp_at(freqs, spec, f, tol=0.03):
        m = (freqs > f * (1 - tol)) & (freqs < f * (1 + tol))
        return float(spec[m].max()) if m.any() else np.nan

    rows = []
    for _, s in snaps.iterrows():
        a = A.loc[s.asset_id]
        x = np.asarray(s.samples, dtype=float); x -= x.mean()
        fs = s.sample_rate_hz; f1 = s.rpm_at_capture / 60.0
        win = np.hanning(len(x))
        spec = np.abs(np.fft.rfft(x * win)) * 2 / win.sum()
        freqs = np.fft.rfftfreq(len(x), 1 / fs)
        env = np.abs(hilbert(sosfiltfilt(butter(4, [2000, 3600], btype="band", fs=fs, output="sos"), x))); env -= env.mean()
        espec = np.abs(np.fft.rfft(env * win)) * 2 / win.sum()
        hp = butter(4, 4000, btype="high", fs=fs, output="sos")
        rows.append(dict(asset_id=s.asset_id, time=s.timestamp_utc, rpm=s.rpm_at_capture,
                         a_1x=amp_at(freqs, spec, f1), a_2x=amp_at(freqs, spec, 2 * f1),
                         a_vane=amp_at(freqs, spec, a.impeller_vanes * f1),
                         env_bpfo=amp_at(freqs, espec, a.bearing_bpfo_order * f1),
                         hf_rms=float(np.sqrt(np.mean(sosfiltfilt(hp, x) ** 2))),
                         crest=float(np.abs(x).max() / np.sqrt(np.mean(x ** 2)))))
    return pd.DataFrame(rows, columns=cols).sort_values(["asset_id", "time"])


def snapshot_ratios(vib: pd.DataFrame) -> pd.DataFrame:
    if len(vib):
        s = diag2.snap_ratios(vib)
        s["time"] = pd.to_datetime(s["time"], utc=True).astype(UTC_NS)
        return s
    return pd.DataFrame({"asset_id": pd.Series(dtype=str), "time": pd.Series(dtype=UTC_NS),
                         **{k: pd.Series(dtype=float) for k in ("r_bpfo", "r_1x", "r_2x", "r_hf", "b_idx", "r_bidx")}})


# ------------------------------------------------------------------ per-moment features (same as training)
def features_at(g: pd.DataFrame, j: int, asset, k: float = 6.0) -> dict:
    """All features for pump frame g (sorted, index 0..n-1) at row j, using rows <= j only."""
    f = {}
    row = g.iloc[j]
    for c in LAST_COLS:
        f[c] = float(row[c]) if c in g and pd.notna(row[c]) else np.nan
    for c in CH:
        f[f"flat_{c}"] = float(bool(row.get(f"flat_{c}", False)) if pd.notna(row.get(f"flat_{c}", np.nan)) else 0.0)
    for w in WINDOWS:
        win = g.iloc[max(0, j - w):j + 1]
        f[f"gap_frac_{w}"] = float(win["gap"].astype(float).mean())
        f[f"steady_frac_{w}"] = float(win["steady"].astype(float).mean())
        for c in TREND_COLS:
            if c not in g:
                continue
            x = win[c].astype(float)
            if x.notna().sum() < 3:
                f[f"{c}_d{w}"] = f[f"{c}_std{w}"] = f[f"{c}_absmax{w}"] = np.nan
                continue
            f[f"{c}_d{w}"] = x.iloc[-5:].median() - x.iloc[:5].median()
            f[f"{c}_std{w}"] = x.std()
            f[f"{c}_absmax{w}"] = x.abs().max()
    zc = {c: abs(f.get(f"z_{c}", np.nan)) for c in CH if pd.notna(f.get(f"z_{c}", np.nan))}
    if zc:
        top = max(zc, key=zc.get)
        x = g[f"z_{top}"].iloc[max(0, j - 360):j + 1].astype(float).ffill().fillna(0).values
        total = abs(x[-1] - np.median(x[:20])) if len(x) >= 30 else np.nan
        jump = np.nanmax(np.abs(x[10:] - x[:-10])) if len(x) > 10 else np.nan
        f["top_jump_ratio"] = float(jump / total) if total and total > 1e-6 else np.nan
        cpl = [abs(f.get(f"z_{x}", np.nan)) for x in B.COUPLED.get(top, []) if pd.notna(f.get(f"z_{x}", np.nan))]
        f["top_coupled_ratio"] = float(max(cpl) / zc[top]) if cpl and zc[top] > 1e-6 else np.nan
    for t in TIERS:
        f[f"tier_{t}"] = float(asset.instrumentation_tier == t)
    for c in CONTROLS:
        f[f"ctl_{c}"] = float(asset.control == c)
    chans = str(asset.channels_available)
    for c, col in B.CH.items():
        f[f"has_{c}"] = float(col in chans)
    try:
        cls, ft, conf, _, _ = diag2.diagnose2(g, j, k, asset.control)
    except Exception:
        cls, ft, conf = "MACHINE", "UNKNOWN", 0.0
    f["rule_type"], f["rule_class"], f["rule_conf"] = ft, cls, float(conf)
    return f


def make_X(df: pd.DataFrame, columns: list | None = None) -> pd.DataFrame:
    """numeric features + one-hot of the rule verdict, aligned to the model's training columns"""
    X = df.drop(columns=[c for c in META if c in df] + ["rule_type", "rule_class"])
    X = pd.concat([X, pd.get_dummies(df["rule_type"].fillna("UNKNOWN"), prefix="rule").astype(float)], axis=1)
    X = X.apply(pd.to_numeric, errors="coerce").astype(float)
    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.0)
    return X
