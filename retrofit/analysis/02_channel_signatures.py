# Stage 2: Per-fault-type channel signature matrix
# For each event: deviation (in noise z-units and % of healthy mean) on every channel,
# measured during [detectable, end], against a healthy per-asset reference (median + MAD).
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT + r"\data\full"

assets = pd.read_csv(DATA + r"\assets.csv")
assets["window_start_utc"] = pd.to_datetime(assets["window_start_utc"])
events = pd.concat([
    pd.read_csv(DATA + r"\events_train.csv", parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"]).assign(split="train"),
    pd.read_csv(DATA + r"\events_validation.csv", parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"]).assign(split="validation"),
], ignore_index=True)
benign = pd.read_csv(DATA + r"\benign_windows_train_validation.csv", parse_dates=["start_utc", "end_utc"])

feats = pd.read_parquet(DATA + r"\features_1min.parquet")
feats["window_start_utc"] = pd.to_datetime(feats["window_start_utc"])

CHANNELS = ["motor_speed_rpm", "motor_current_a", "motor_power_kw", "suction_pressure_kpa",
            "discharge_pressure_kpa", "flow_m3_h", "fluid_temp_c", "bearing_temp_c",
            "motor_winding_temp_c", "vibration_rms_mm_s", "vibration_accel_rms_g",
            "vibration_crest_factor", "valve_position_pct"]

# Build per-asset event/benign interval lists
ev_int = {a: [(r.onset_utc, r.end_utc) for r in events[events.asset_id == a].itertuples() if pd.notna(r.onset_utc)]
          for a in events.asset_id.unique()}
bn_int = {a: list(zip(benign[benign.asset_id == a].start_utc, benign[benign.asset_id == a].end_utc)) for a in benign.asset_id.unique()}

def overlaps(t, ivs, pad=pd.Timedelta(0)):
    return any(s <= t <= e for s, e in ivs)

# Healthy reference stats per asset/channel
idx = {c: f"{c}__mean" for c in CHANNELS}
healthy_stats = {}
for a, grp in feats.groupby("asset_id"):
    grp = grp.sort_values("window_start_utc")
    is_ev = grp["window_start_utc"].apply(lambda t: overlaps(t, ev_int.get(a, []), pd.Timedelta("6h")))
    is_bn = grp["window_start_utc"].apply(lambda t: overlaps(t, bn_int.get(a, [])))
    running = grp["operating_mode"] == "RUNNING"
    healthy = grp[running & ~is_ev & ~is_bn & (grp["running_fraction"] > 0.9)]
    for c in CHANNELS:
        col = idx[c]
        if col in healthy.columns:
            v = healthy[col].dropna().values
            if len(v) > 60:
                med = float(np.median(v))
                mad = float(np.median(np.abs(v - med))) * 1.4826
                mad = max(mad, 1e-6)
                healthy_stats[(a, c)] = (med, mad, np.mean(v))

# Signature extraction per event
rows = []
for r in events.itertuples():
    a = r.asset_id
    grp = feats[(feats.asset_id == a)].sort_values("window_start_utc")
    t0 = r.detectable_utc if pd.notna(r.detectable_utc) else r.onset_utc
    t1 = r.end_utc if pd.notna(r.end_utc) else grp["window_start_utc"].max()
    if pd.isna(t0):
        t0 = grp["window_start_utc"].min()
    mask = (grp["window_start_utc"] >= t0) & (grp["window_start_utc"] <= t1) & (grp["operating_mode"] == "RUNNING")
    sig = grp[mask]
    if len(sig) == 0:
        continue
    for c in CHANNELS:
        col = idx[c]
        if col not in sig.columns or (a, c) not in healthy_stats:
            continue
        med_h, mad_h, mean_h = healthy_stats[(a, c)]
        v = sig[col].dropna().values
        if len(v) == 0:
            continue
        m = float(np.median(v))
        rows.append({
            "asset": a, "split": r.split, "class": r.event_class, "fault": r.fault_type,
            "eid": r.event_id, "channel": c, "z": (m - med_h) / mad_h,
            "pct": 100.0 * (m - mean_h) / mean_h if mean_h != 0 else np.nan,
            "tier": assets[assets.asset_id == a].instrumentation_tier.iloc[0],
        })

sig_df = pd.DataFrame(rows)
sig_df["obs"] = sig_df["asset"].map(events.drop_duplicates("asset_id").set_index("asset_id").observable)  # not per-event; fix below
sig_df = sig_df.merge(events[["event_id", "observable"]].rename(columns={"eid": "event_id"}), left_on=["eid", "asset"], right_on=["event_id", "asset"], how="left") if False else sig_df

# Aggregate: median z/pct per fault type per channel
agg = sig_df.groupby(["class", "fault", "channel"]).agg(
    z_med=("z", "median"), pct_med=("pct", "median"), n_ev=("eid", "nunique"))
mat_z = agg.reset_index().pivot_table(index=["class", "fault"], columns="channel", values="z_med")
mat_p = agg.reset_index().pivot_table(index=["class", "fault"], columns="channel", values="pct_med")
order = CHANNELS
mat_z = mat_z.reindex(columns=order)
mat_p = mat_p.reindex(columns=order)

pd.set_option("display.width", 300)
print("=" * 140)
print("MEDIAN DEVIATION IN NOISE UNITS (z = deviation / per-asset MAD), per fault type x channel")
print("Machine faults: physically coupled multi-channel patterns. Sensor faults: single-channel.")
print("=" * 140)
print(mat_z.round(1).to_string())
print()
print("=" * 140)
print("MEDIAN RELATIVE DEVIATION (% of healthy regime mean)")
print("=" * 140)
print(mat_p.round(1).to_string())
print()

# Single-channel events (sensor faults): confirm isolation
print("=" * 140)
print("SENSOR FAULT ISOLATION: max |z| on affected channel vs second-highest |z| on other channels")
print("=" * 140)
sf = sig_df[sig_df["class"] == "SENSOR"].groupby("eid")
for eid, g in sf:
    fa = g["fault"].iloc[0]
    top = g.reindex(g.z.abs().sort_values(ascending=False).index)
    t1v, t2v = top.iloc[0], top.iloc[1] if len(top) > 1 else None
    print(f"{eid:22s} {fa:22s} top={t1v['channel']:24s} |z|={abs(t1v['z']):6.1f}   "
          f"next={t2v['channel'] if t2v is not None else '-':24s} |z|={abs(t2v['z']) if t2v is not None else 0:6.1f}")

sig_df.to_parquet(ROOT + r"\analysis\event_channel_z.parquet")
print()
print(f"saved {len(sig_df)} signature rows -> analysis/event_channel_z.parquet")

