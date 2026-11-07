# Stage 3b: PUMP-04 vibration snapshot spectral analysis
# Bearing-defect detection at BPFO and the 2.8 kHz housing resonance from 10.24 kHz waveforms
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT + r"\data\full"
rng = np.random.default_rng(0)

assets = pd.read_csv(DATA + r"\assets.csv")
a4 = assets[assets.asset_id == "PUMP-04"].iloc[0]
snap = pd.read_parquet(DATA + r"\vibration_snapshots.parquet")
s4 = snap[snap.asset_id == "PUMP-04"].sort_values("timestamp_utc").reset_index(drop=True)
print(f"PUMP-04: bearing={a4.bearing_designation}, bpfo_order={a4.bearing_bpfo_order}, bpfi_order={a4.bearing_bpfi_order}, "
      f"vanes={a4.impeller_vanes}, rated_rpm={a4.motor_rated_rpm}, alarm={a4.vibration_alarm_mm_s} mm/s, trip={a4.vibration_trip_mm_s} mm/s")
print(f"{len(s4)} snapshots, first={s4.timestamp_utc.iloc[0]}, last={s4.timestamp_utc.iloc[-1]}, "
      f"sample_rate={s4.sample_rate_hz.iloc[0]}, n_samples={s4.n_samples.iloc[0]}")

fs = float(s4.sample_rate_hz.iloc[0])
N = int(s4.n_samples.iloc[0])
freqs = np.fft.rfftfreq(N, d=1.0 / fs)


def spec_db(x, bw_bins=3):
    x = np.asarray(x, dtype=float)
    w = np.hanning(len(x))
    S = np.abs(np.fft.rfft(x * w)) * 2 / np.sum(np.hanning(0) + w)  # hann-normalized
    S[1:-1] = S[1:-1]; S[0] /= 2
    db = 20 * np.log10(S + 1e-12)
    return db


def band(obj, f0, f1):
    """mean spectrum level (dB) in band from pre-computed db spectrum."""
    m = (freqs >= f0) & (freqs <= f1)
    return float(np.mean(obj[f"db"][:, m])) if "db" in obj else None


# Pre-compute all spectra at once
X = np.stack(s4.samples.apply(lambda s: np.asarray(s, dtype=float)).values)
w = np.hanning(N)
S = np.abs(np.fft.rfft(X * w, axis=1)) * 2 / N * 2  # amplitude-ish normalization
S[:, 0] /= 2; S[:, -1] /= 2
db = 20 * np.log10(S + 1e-12)

rows = []
for i, r in s4.iterrows():
    rpm = r.rpm_at_capture
    f1x = rpm / 60.0
    fbpfo, fbpfi = a4.bearing_bpfo_order * f1x, a4.bearing_bpfi_order * f1x
    fpv = a4.impeller_vanes * f1x
    base = db[i, (freqs >= 100) & (freqs <= 4000)]
    def bl(f, half=4.0):
        m = (freqs >= f - half) & (freqs <= f + half)
        return float(np.max(db[i, m]))
    offset = (r.timestamp_utc - s4.timestamp_utc.iloc[0]).total_seconds() / 86400
    flat = np.std(X[i, :-1] - X[i, 1:])  # rough noise/impulse proxy
    rows.append({
        "day": offset, "time": r.timestamp_utc, "rpm": rpm,
        "f1x": f1x, "fBPFO": fbpfo, "fVP": fpv,
        "pk_2p8k": float(db[i, (freqs >= 2700) & (freqs <= 2900)].max()),
        "mean_BPFO": bl(fbpfo), "mean_BPFI": bl(fbpfi), "VP": bl(fpv),
        "broad": float(np.mean(base)),
    })

t = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print()
print("Snapshot bands over time (day=days since window start). 2.8k=resonance peak, BPFO/BPFI=defect line peaks, VP=vane pass, broad=mean 100-4000 Hz")
print(t[["day", "rpm", "pk_2p8k", "mean_BPFO", "mean_BPFI", "VP", "broad"]].round(1).to_string(index=False))

# Phase comparison: early (day<1) vs peak (day 4.3-5.4) vs after bearing repair (if any snapshots past 5.45)
phases = [("early day<1", t.day < 1.0), ("pre-peak 3-4.3d", (t.day >= 3.0) & (t.day < 4.3)),
          ("peak bearing 4.5-5.45d", (t.day >= 4.5) & (t.day < 5.45)), ("post 5.45d+", t.day >= 5.45)]
print()
print("=" * 100)
print("PHASE-AVERAGED SPECTRUM LEVELS (dB, max-in-band around each feature)")
print("=" * 100)
print(f"{'phase':24s} {'2.6-3.0k res':>14s} {'BPFO line':>11s} {'BPFI line':>11s} {'vane pass':>11s} {'broad 100-4k':>13s}")
for name, m in phases:
    if m.sum() == 0:
        print(f"{name:24s} {'-':>14s}")
        continue
    D = db[m.values]
    f1xs = np.array(t.rpm[m.values]) / 60.0
    out = []
    for fset in [(2700, 2900)]:
        mm = (freqs >= fset[0]) & (freqs <= fset[1])
        out.append(float(np.mean(D[:, mm].max(axis=1))))
    def line(order):
        vals = []
        for j in range(len(f1xs)):
            f = order * f1xs[j]
            m2 = (freqs >= f - 4) & (freqs <= f + 4)
            vals.append(D[j, m2].max())
        return float(np.mean(vals))
    br = D[:, (freqs >= 100) & (freqs <= 4000)].mean(axis=1)
    print(f"{name:24s} {out[0]:14.1f} {line(a4.bearing_bpfo_order):11.1f} {line(a4.bearing_bpfi_order):11.1f} "
          f"{line(a4.impeller_vanes):11.1f} {float(np.mean(br)):13.1f}")

# Envelope demodulation at the 2.8 kHz resonance: BPFO line visibility
print()
print("=" * 100)
print("ENVELOPE DEMODULATION: band-pass 2.6-3.0 kHz, |Hilbert| envelope, FFT up to 120 Hz -> BPFO/bin")
print("=" * 100)
from scipy.signal import butter, filtfilt, hilbert
b, aa = butter(4, [2600 / (fs / 2), 3000 / (fs / 2)], btype="band")
env_lines = []
for i, r in s4.iterrows():
    x = np.asarray(r.samples, dtype=float)
    xf = filtfilt(b, aa, x)
    env = np.abs(hilbert(xf)) - np.mean(np.abs(hilbert(xf)))
    E = np.abs(np.fft.rfft(env * np.hanning(N))) / N * 4
    f1x = r["rpm_at_capture"] / 60.0
    off = (r.timestamp_utc - s4.timestamp_utc.iloc[0]).total_seconds() / 86400
    mB = (freqs >= a4.bearing_bpfo_order * f1x - 1.5) & (freqs <= a4.bearing_bpfo_order * f1x + 1.5)
    ref = float(np.std(E[(freqs <= 120)])) + 1e-15
    env_lines.append({"day": off, "BPFO_env_peak": float(E[mB].max()), "env_noise_120Hz": ref,
                      "SNR": float(E[mB].max()) / ref})
    del xf, env, E
te = pd.DataFrame(env_lines)
print(te.round(1).to_string(index=False))

# Save summary + a compact CSV for figures
t.to_csv(ROOT + r"\analysis\pump04_snapshot_bands.csv", index=False)
te.to_csv(ROOT + r"\analysis\pump04_envelope_snr.csv", index=False)
np.savez_compressed(ROOT + r"\analysis\pump04_avg_spectra.npz",
                    freqs=freqs.astype(np.float32),
                    **{name.replace(" ", "_")[:12]: D2 for (name, m) in phases
                       for D2 in [np.median(db[m.values], axis=0).astype(np.float32)] if m.values.sum() > 0})
print("\nsaved: analysis/pump04_snapshot_bands.csv, pump04_envelope_snr.csv, pump04_avg_spectra.npz")

