"""Vibration snapshot features for RETROFIT AI.
For each 1-s vibration recording: 1x, 2x, vane-pass amplitudes, bearing (BPFO)
envelope amplitude, high-frequency RMS and crest factor.
Run from the RETROFIT_AI_PARTICIPANTS_2026 folder:  python3 vibration_features.py
Output: vibration_features.csv
"""
import numpy as np, pandas as pd
from scipy.signal import butter, sosfiltfilt, hilbert

D = "data/full"
snap = pd.read_parquet(f"{D}/vibration_snapshots.parquet")
assets = pd.read_csv(f"{D}/assets.csv").set_index("asset_id")

def amp_at(freqs, spec, f, tol=0.03):
    m = (freqs > f * (1 - tol)) & (freqs < f * (1 + tol))
    return float(spec[m].max()) if m.any() else np.nan

rows = []
for _, s in snap.iterrows():
    a = assets.loc[s.asset_id]
    x = np.asarray(s.samples, dtype=float); x -= x.mean()
    fs = s.sample_rate_hz; f1 = s.rpm_at_capture / 60.0
    win = np.hanning(len(x))
    spec = np.abs(np.fft.rfft(x * win)) * 2 / win.sum()
    freqs = np.fft.rfftfreq(len(x), 1 / fs)
    # envelope spectrum around the ~2.8 kHz housing resonance -> bearing impacts
    bp = butter(4, [2000, 3600], btype="band", fs=fs, output="sos")
    env = np.abs(hilbert(sosfiltfilt(bp, x))); env -= env.mean()
    espec = np.abs(np.fft.rfft(env * win)) * 2 / win.sum()
    hp = butter(4, 4000, btype="high", fs=fs, output="sos")
    rows.append(dict(
        asset_id=s.asset_id, time=s.timestamp_utc, rpm=s.rpm_at_capture,
        a_1x=amp_at(freqs, spec, f1),
        a_2x=amp_at(freqs, spec, 2 * f1),
        a_vane=amp_at(freqs, spec, a.impeller_vanes * f1),
        env_bpfo=amp_at(freqs, espec, a.bearing_bpfo_order * f1),
        hf_rms=float(np.sqrt(np.mean(sosfiltfilt(hp, x) ** 2))),
        crest=float(np.abs(x).max() / np.sqrt(np.mean(x ** 2)))))

features = pd.DataFrame(rows).sort_values(["asset_id", "time"])
features.to_csv("vibration_features.csv", index=False)
print(f"Saved vibration_features.csv ({len(features)} snapshots)\n")
summary = features.groupby("asset_id").agg(
    snapshots=("rpm", "size"),
    bearing_click_start=("env_bpfo", "first"),
    bearing_click_max=("env_bpfo", "max"))
summary["growth_x"] = (summary.bearing_click_max / summary.bearing_click_start).round(1)
print(summary.round(4))
