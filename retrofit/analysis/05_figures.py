# Stage 5: figures for the deep-dive report
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt, hilbert
import os

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT + r"\data\full"
FIGS = ROOT + r"\analysis\figs"
os.makedirs(FIGS, exist_ok=True)

assets = pd.read_csv(DATA + r"\assets.csv", parse_dates=["window_start_utc"])
events = pd.concat([
    pd.read_csv(DATA + r"\events_train.csv", parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"]),
    pd.read_csv(DATA + r"\events_validation.csv", parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"]),
], ignore_index=True)
feats = pd.read_parquet(DATA + r"\features_1min.parquet")
feats["window_start_utc"] = pd.to_datetime(feats["window_start_utc"])
feats["day"] = (feats["window_start_utc"] - feats["window_start_utc"].min()).dt.total_seconds() / 86400

COL = {"vibration_accel_rms_g": "#1f77b4", "vibration_crest_factor": "#d62728",
       "vibration_rms_mm_s": "#2ca02c", "bearing_temp_c": "#9467bd", "motor_winding_temp_c": "#8c564b"}

def shade_events(ax, ev_df, colors, window_start, t_max_days=7.3):
    for e in ev_df.itertuples():
        s = e.onset_utc if pd.notna(e.onset_utc) else e.detectable_utc
        if pd.isna(s):
            continue
        e2 = e.end_utc if pd.notna(e.end_utc) else window_start + pd.Timedelta(days=t_max_days)
        s_d = (s - window_start).total_seconds() / 86400
        e_d = min((e2 - window_start).total_seconds() / 86400, t_max_days)
        ax.axvspan(s_d, e_d, alpha=0.18, color=colors.get(e.fault_type, "gray"), lw=0)

colors = {"BEARING_WEAR": "red", "IMBALANCE": "orange", "DISCHARGE_RESTRICTION": "purple",
          "SENSOR_NOISE_SPIKES": "yellowgreen", "SUCTION_STRAINER_CLOGGING": "brown", "CAVITATION": "cyan"}

# ---- Fig 1: PUMP-04 staging ----
ws4 = assets[assets.asset_id == "PUMP-04"].window_start_utc.iloc[0]
ws6 = assets[assets.asset_id == "PUMP-06"].window_start_utc.iloc[0]
g = feats[feats.asset_id == "PUMP-04"].sort_values("window_start_utc")
g["day"] = (g.window_start_utc - g.window_start_utc.min()).dt.total_seconds() / 86400
e4 = events[events.asset_id == "PUMP-04"]
fig, axes = plt.subplots(5, 1, figsize=(12, 11), sharex=True)
units = {"vibration_accel_rms_g": "g", "vibration_crest_factor": "-", "vibration_rms_mm_s": "mm/s",
         "bearing_temp_c": "deg C", "motor_winding_temp_c": "deg C"}
for ax, c in zip(axes, COL):
    ax.plot(g.day, g[f"{c}__mean"], color=COL[c], lw=0.8)
    ax.set_ylabel(f"{c}\n({units[c]})", fontsize=8)
    ax.grid(alpha=0.3)
    shade_events(ax, e4, colors, ws4)
axes[0].set_title("PUMP-04 (T2 Full) - bearing-wear staging: HF acceleration rises first, crest factor next,\n"
                  "then velocity and temperature; events shaded", fontsize=10)
axes[-1].set_xlabel("days since window start")
plt.tight_layout(); plt.savefig(FIGS + r"\fig1_pump04_staging.png", dpi=140); plt.close()

a4 = assets[assets.asset_id == "PUMP-04"].iloc[0]
snap = pd.read_parquet(DATA + r"\vibration_snapshots.parquet")
s4 = snap[snap.asset_id == "PUMP-04"].sort_values("timestamp_utc").reset_index(drop=True)
fs, N = 10240.0, 10240
freqs = np.fft.rfftfreq(N, 1 / fs)
X = np.stack(s4.samples.apply(lambda s: np.asarray(s, dtype=float)).values)
w = np.hanning(N); S = np.abs(np.fft.rfft(X * w, axis=1)) * 4 / N; S[:, 0] /= 2; S[:, -1] /= 2
dbS = 20 * np.log10(S + 1e-12)
day = (pd.to_datetime(s4.timestamp_utc) - pd.to_datetime(s4.timestamp_utc.iloc[0])).dt.total_seconds() / 86400
fig = plt.figure(figsize=(12, 9))
gs = fig.add_gridspec(2, 2, height_ratios=[1, 1])
ax1 = fig.add_subplot(gs[0, :])
sel = {"early (day<1)": day < 1, "mid (3-4.3d)": (day >= 3) & (day < 4.3), "peak (4.5-5.45d)": (day >= 4.5) & (day < 5.45), "post-repair (5.45d+)": day >= 5.45}
cmap = {"early (day<1)": "#1f77b4", "mid (3-4.3d)": "#ff7f0e", "peak (4.5-5.45d)": "#d62728", "post-repair (5.45d+)": "#7f7f7f"}
for name, m in sel.items():
    ax1.plot(freqs, dbS[m.values].max(axis=0), color=cmap[name], lw=0.6, alpha=0.9, label=name)
f1x = 1355 / 60.0
ax1.text(a4.bearing_bpfo_order * f1x + 6, -18, "BPFO 69Hz", fontsize=8, va="top", ha="left")
ax1.axvline(a4.bearing_bpfo_order * f1x, color="k", ls=":", lw=1, alpha=0.8)
ax1.text(a4.bearing_bpfi_order * f1x + 6, -38, "BPFI 111Hz", fontsize=8, va="top", ha="left")
ax1.axvline(a4.bearing_bpfi_order * f1x, color="k", ls=":", lw=1, alpha=0.8)
ax1.text(a4.impeller_vanes * f1x + 6, -58, "6xVP 135Hz", fontsize=8, va="top", ha="left")
ax1.axvline(a4.impeller_vanes * f1x, color="k", ls=":", lw=1, alpha=0.8)
ax1.axvspan(2600, 3000, color="r", alpha=0.12)
ax1.set_xlim(0, 4000); ax1.set_ylim(-90, 5)
ax1.set_xlabel("Hz"); ax1.set_ylabel("dB (max over phase)")
ax1.legend(fontsize=8, loc="lower right")
ax1.set_title("PUMP-04 snapshot spectra: housing resonance peak grows from day 0, collapses after bearing repair at 5.45 d", fontsize=9)

ax2 = fig.add_subplot(gs[1, :])
b, a = butter(4, [2600 / (fs / 2), 3000 / (fs / 2)], btype="band")
peaks, days_ = [], []
for _, r in s4.iterrows():
    xf = filtfilt(b, a, np.asarray(r.samples, dtype=float))
    env = np.abs(hilbert(xf)); env = env - env.mean()
    E = np.abs(np.fft.rfft(env * np.hanning(N))) / N * 4
    f1xs = r.rpm_at_capture / 60.0
    fB = a4.bearing_bpfo_order * f1xs
    mB = (freqs >= fB - 2) & (freqs <= fB + 2)
    peaks.append(E[mB].max()); days_.append((r.timestamp_utc - s4.timestamp_utc.iloc[0]).total_seconds() / 86400)
ax2.plot(days_, peaks, "o-", color="#d62728", lw=1, ms=3)
ax2.axvline(5.45, color="k", ls="--", lw=1); ax2.text(5.5, max(peaks) * 0.7, "bearing repair", fontsize=8)
ax2.set_xlabel("days since window start"); ax2.set_ylabel("BPFO envelope peak (g)")
ax2.set_title("Demodulated 2.6-3.0 kHz envelope, BPFO line amplitude: monotone defect growth, cleared by repair", fontsize=9)
ax2.grid(alpha=0.3)
plt.tight_layout(); plt.savefig(FIGS + r"\fig2_pump04_spectrum_envelope.png", dpi=140); plt.close()

# ---- Fig 3: PUMP-06 clog -> cavitation ----
g6 = feats[feats.asset_id == "PUMP-06"].sort_values("window_start_utc")
g6["day"] = (g6.window_start_utc - g6.window_start_utc.min()).dt.total_seconds() / 86400
e6 = events[events.asset_id == "PUMP-06"]
fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
hyd = ["suction_pressure_kpa", "discharge_pressure_kpa", "motor_current_a", "vibration_accel_rms_g"]
units = {"suction_pressure_kpa": "kPa(g)", "discharge_pressure_kpa": "kPa(g)", "motor_current_a": "A", "vibration_accel_rms_g": "g"}
for ax, c in zip(axes, hyd):
    is_sparse = c == "vibration_accel_rms_g"  # T1 wireless: one value / 300 s
    ax.plot(g6.day, g6[f"{c}__mean"], color="#1f77b4", lw=0.6,
            marker="." if is_sparse else None, ms=3 if is_sparse else None)
    ax.set_ylabel(f"{c}\n({units[c]})", fontsize=8); ax.grid(alpha=0.3)
    shade_events(ax, e6, colors, ws6)
axes[0].set_title("PUMP-06 (T1 retrofit) - strainer clog then 4 cavitation episodes (cyan): suction collapses,\n"
                  "discharge holds (VFD compensates) until head breakdown; HF acceleration spikes with each episode", fontsize=9)
axes[-1].set_xlabel("days since window start")
plt.tight_layout(); plt.savefig(FIGS + r"\fig3_pump06_clog_cavitation.png", dpi=140); plt.close()
print("figures written:", os.listdir(FIGS))

