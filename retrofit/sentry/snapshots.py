# SENTRY module: vibration snapshot analysis (PSD line SNRs + housing-resonance envelope demodulation).
import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, hilbert

FMAX_REF = (20.0, 400.0)       # envelope-spectrum reference band (Hz)
RESONANCE_SEARCH = (2000.0, 3600.0)  # housing-resonance search band (Hz)


def _psd_line_db(spec_db, freqs, f, half=3.0):
    m = (freqs >= f - half) & (freqs <= f + half)
    return float(spec_db[m].max()) if m.any() else np.nan


def _ref_db(spec_db, freqs, excl):
    m = (freqs >= FMAX_REF[0]) & (freqs <= FMAX_REF[1])
    for f, h in excl:
        m &= ~((freqs >= f - h) & (freqs <= f + h))
    return float(np.median(spec_db[m])) if m.any() else np.nan


def analyze_snapshot(samples: np.ndarray, fs: float, rpm: float,
                     bpfo_order: float, bpfi_order: float, vanes: int,
                     resonance_hz: float):
    """Return dict of line levels (dB) and envelope line SNRs (dB) for one 1-s record."""
    x = np.asarray(samples, dtype=float)
    N = len(x)
    freqs = np.fft.rfftfreq(N, 1.0 / fs)
    w = np.hanning(N)
    S = np.abs(np.fft.rfft(x * w)) * 2.0 / N
    S[0] /= 2
    S[-1] /= 2
    spec_db = 20 * np.log10(S + 1e-12)
    f1x = rpm / 60.0
    excl = [(f1x * k, 4.0) for k in (1, 2, 3)]
    excl += [(bpfo_order * f1x, 3.0), (bpfi_order * f1x, 3.0), (vanes * f1x, 3.0)]
    out = {
        "f1x": f1x,
        "p1x_db": _psd_line_db(spec_db, freqs, f1x), "p2x_db": _psd_line_db(spec_db, freqs, 2 * f1x),
        "p3x_db": _psd_line_db(spec_db, freqs, 3 * f1x), "pvp_db": _psd_line_db(spec_db, freqs, vanes * f1x),
        "p_ref_db": _ref_db(spec_db, freqs, excl),
    }
    out["s1x"] = out["p1x_db"] - out["p_ref_db"]
    out["s2x"] = out["p2x_db"] - out["p_ref_db"]
    out["s3x"] = out["p3x_db"] - out["p_ref_db"]
    # housing-resonance envelope demodulation (defect-impulse carrier)
    lo, hi = max(resonance_hz - 200, 500), min(resonance_hz + 200, fs / 2 - 100)
    b, a = butter(4, [lo / (fs / 2), hi / (fs / 2)], btype="band")
    xf = filtfilt(b, a, x)
    env = np.abs(hilbert(xf))
    env = env - env.mean()
    E = np.abs(np.fft.rfft(env * np.hanning(N))) / N * 4
    Edb = 20 * np.log10(E + 1e-12)
    for name, order in (("bpfo", bpfo_order), ("bpfi", bpfi_order)):
        f = order * f1x
        mB = (freqs >= f - 2) & (freqs <= f + 2)
        peak = float(Edb[mB].max()) if mB.any() else np.nan
        pk = float(E[mB].max()) if mB.any() else np.nan
        ref = _ref_db(Edb, freqs, [(f, 4.0)])
        out[f"e_{name}_snr"] = float(peak - ref) if np.isfinite(ref) else np.nan
        out[f"e_{name}_amp"] = pk if pk == pk else np.nan
    return out


def learn_resonance(snapshot_spectra_med_db: np.ndarray, freqs: np.ndarray) -> float:
    """Peak frequency of the median PSD in the resonance search band."""
    m = (freqs >= RESONANCE_SEARCH[0]) & (freqs <= RESONANCE_SEARCH[1])
    if not m.any():
        return 2800.0
    idx = np.argmax(np.convolve(snapshot_spectra_med_db[m], np.ones(15) / 15, mode="same"))
    return float(freqs[m][idx])


def snapshot_metrics(snap_asset: pd.DataFrame, bpfo: float, bpfi: float, vanes: int) -> pd.DataFrame:
    """Analyze all snapshots of one asset; auto-learns the resonance band from early records."""
    fs = float(snap_asset.sample_rate_hz.iloc[0])
    N = int(snap_asset.n_samples.iloc[0])
    freqs = np.fft.rfftfreq(N, 1.0 / fs)

    def spec_of(i):
        x = np.asarray(snap_asset.samples.iloc[i], dtype=float)
        w = np.hanning(N)
        S = np.abs(np.fft.rfft(x * w)) * 2.0 / N
        S[0] /= 2; S[-1] /= 2
        return 20 * np.log10(S + 1e-12)

    n_learn = min(6, len(snap_asset))
    med_db = np.median([spec_of(i) for i in range(n_learn)], axis=0)
    res_hz = learn_resonance(med_db, freqs)
    rows = []
    for i, r in snap_asset.iterrows():
        d = analyze_snapshot(np.asarray(r.samples, dtype=float), fs, float(r.rpm_at_capture),
                             bpfo, bpfi, vanes, res_hz)
        d["timestamp_utc"] = r.timestamp_utc
        rows.append(d)
    out = pd.DataFrame(rows)
    out.attrs["resonance_hz"] = res_hz
    return out
