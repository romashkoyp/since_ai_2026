# Stage 3a: Trace-level analysis
# (1) PUMP-04: bearing-wear staging (accel -> crest -> velocity -> temp) with onset ordering
# (2) PUMP-06: strainer clogging and the 4 cavitation episodes
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT + r"\data\full"

events = pd.concat([
    pd.read_csv(DATA + r"\events_train.csv", parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"]),
    pd.read_csv(DATA + r"\events_validation.csv", parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"]),
], ignore_index=True)
benign = pd.read_csv(DATA + r"\benign_windows_train_validation.csv", parse_dates=["start_utc", "end_utc"])
assets = pd.read_csv(DATA + r"\assets.csv")
feats = pd.read_parquet(DATA + r"\features_1min.parquet")
feats["window_start_utc"] = pd.to_datetime(feats["window_start_utc"])

CH = ["vibration_accel_rms_g", "vibration_crest_factor", "vibration_rms_mm_s",
      "bearing_temp_c", "motor_winding_temp_c", "motor_current_a", "motor_power_kw"]
HYD = ["suction_pressure_kpa", "discharge_pressure_kpa", "flow_m3_h", "motor_speed_rpm",
       "motor_power_kw", "motor_current_a", "vibration_accel_rms_g", "valve_position_pct"]


def healthy_ref(grp, ev_int, a):
    """healthy reference (median, MAD) computed on RUNNING minutes outside event windows (pad 6 h)."""
    is_ev = grp["window_start_utc"].apply(
        lambda t: any(pd.notna(s) and s - pd.Timedelta("6h") <= t <= (e if pd.notna(e) else t) for s, e in ev_int))
    h = grp[(grp["operating_mode"] == "RUNNING") & ~is_ev & (grp["running_fraction"] > 0.9)]
    out = {}
    for c in set(CH) | set(HYD):
        col = f"{c}__mean"
        if col in h.columns:
            v = h[col].dropna().values
            if len(v) > 50:
                med = np.median(v); mad = max(np.median(np.abs(v - med)) * 1.4826, 1e-9)
                out[c] = (med, mad)
    return out


def onset_order(asset, channels, min_hours=10):
    """first 1-min time where rolling 12-min mean of channel z exceeds +4 (detectable-ish rule)."""
    a = assets[assets.asset_id == asset].iloc[0]
    base = a.window_start_utc
    grp = feats[feats.asset_id == asset].sort_values("window_start_utc").reset_index(drop=True)
    ev_int = [(r.onset_utc, r.end_utc) for r in events[events.asset_id == asset].itertuples()]
    ref = healthy_ref(grp, ev_int, asset)
    out = {}
    for c in channels:
        col = f"{c}__mean"
        if col not in grp.columns or c not in ref:
            out[c] = None; continue
        med, mad = ref[c]
        z = (grp[col].fillna(np.nan) - med) / mad
        rz = z.rolling(12, min_periods=6).mean()
        hit = grp.loc[(rz > 4) & (grp["operating_mode"] == "RUNNING"), "window_start_utc"]
        # keep only sustained (persist >= min_hours in same day later): take first hit
        out[c] = None if len(hit) == 0 else hit.iloc[0]
    return base, out, ref


print("=" * 110)
print("A1. PUMP-04 BEARING WEAR + IMBALANCE: onset ordering, first sustained (12-min mean) z>4 per channel")
print("    label rule reference: detectable = 10-min mean > 3x noise")
print("=" * 110)
base, order, ref = onset_order("PUMP-04", CH)
bwear = events[(events.asset_id == "PUMP-04") & (events.fault_type == "BEARING_WEAR")].iloc[0]
imbal = events[(events.asset_id == "PUMP-04") & (events.fault_type == "IMBALANCE")].iloc[0]
print(f"    label onset={bwear.onset_utc}  detectable={bwear.detectable_utc}")
for c in CH:
    t = order[c]
    if t is None:
        continue
    d = (t - base).total_seconds() / 86400
    print(f"    {c:26s} first sustained hit at day {d:.3f} ({t})")

print()
print("=" * 110)
print("A2. PUMP-06 STRAINER CLOG -> CAVITATION: hydraulic channel deviations per segment")
print("=" * 110)
p6 = events[events.asset_id == "PUMP-06"]
clog = p6[p6.fault_type == "SUCTION_STRAINER_CLOGGING"].iloc[0]
grp6 = feats[feats.asset_id == "PUMP-06"].sort_values("window_start_utc").reset_index(drop=True)
ev_int6 = [(r.onset_utc, r.end_utc) for r in p6.itertuples()]
ref6 = healthy_ref(grp6, ev_int6, "PUMP-06")

segs = [
    ("healthy pre-clog", clog.onset_utc - pd.Timedelta("2d"), clog.onset_utc),
    ("clog develops", clog.detectable_utc, clog.action_deadline_utc),
    ("pre-deadline 1d", clog.action_deadline_utc - pd.Timedelta("1d"), clog.action_deadline_utc),
    ("cav ep1", p6[p6.fault_type == "CAVITATION"].sort_values('onset_utc').iloc[0].onset_utc,
     p6[p6.fault_type == "CAVITATION"].sort_values('onset_utc').iloc[0].end_utc),
]
rows = []
for name, s, e in segs:
    if pd.isna(s) or pd.isna(e):
        continue
    m = (grp6["window_start_utc"] >= s) & (grp6["window_start_utc"] <= e) & (grp6["operating_mode"] == "RUNNING")
    seg = grp6[m]
    row = {"segment": name, "nmin": int(len(seg))}
    for c in HYD:
        col = f"{c}__mean"
        if col in seg.columns and c in ref6:
            v = seg[col].dropna()
            if len(v) > 0:
                med, mad = ref6[c]
                row[c] = f"{v.median():.1f} (z={(v.median() - med) / mad:+.1f}, {100 * (v.median() - ref6[c][0]) / ref6[c][0]:+.1f}%)"
    rows.append(row)
t6 = pd.DataFrame(rows)
cnames = [c for c in t6.columns if c != "segment" and t6[c].notna().any()]
pd.set_option("display.width", 400)
print(t6[["segment", "nmin"] + cnames].to_string(index=False))

print()
print("=" * 110)
print("A3. VFD compensation evidence: PUMP-01 (VFD_TEMPERATURE) clog -> speed/power up; PUMP-06 same check")
print("=" * 110)
for asset in ["PUMP-01", "PUMP-08"]:
    e = events[(events.asset_id == asset) & (events.fault_type == "SUCTION_STRAINER_CLOGGING")].iloc[0]
    grp = feats[feats.asset_id == asset].sort_values("window_start_utc")
    is_ev = grp["window_start_utc"].apply(
        lambda t: any(pd.notna(s) and s <= t <= (e2 if pd.notna(e2) else t) for s, e2 in zip(events[events.asset_id == asset].onset_utc, events[events.asset_id == asset].end_utc)))
    h = grp[(grp["operating_mode"] == "RUNNING") & ~is_ev & (grp["running_fraction"] > 0.9)]
    m = (grp["window_start_utc"] >= e.detectable_utc) & (grp["window_start_utc"] <= (e.end_utc if pd.notna(e.end_utc) else grp["window_start_utc"].max())) & (grp["operating_mode"] == "RUNNING")
    seg = grp[m]
    for c in ["motor_speed_rpm", "motor_power_kw", "suction_pressure_kpa", "flow_m3_h"]:
        col = f"{c}__mean"
        if col in h.columns and col in seg.columns:
            hv, sv = h[col].dropna(), seg[col].dropna()
            if len(hv) and len(sv) and c != "flow_m3_h":
                print(f"    {asset}: {c:22s} healthy med={hv.median():9.2f}  during-clog med={sv.median():9.2f}  "
                      f"delta={100 * (sv.median() - hv.median()) / hv.median():+6.1f}%")

print()
print("=" * 110)
print("A4. SENSOR vs MACHINE: stuck/drift events - affected channel flat or ramping, covariates healthy")
print("    (checks: stuck => ~zero local variance; drift => slow ramp; covariate channels unchanged)")
print("=" * 110)
for asset, eid in [("PUMP-01", "PUMP-01-E04"), ("PUMP-05", "PUMP-05-E03"), ("PUMP-09", "PUMP-09-E02"),
                   ("PUMP-02", "PUMP-02-E02")]:
    p = events[events.event_id == eid]
    if len(p) == 0:
        continue
    r = p.iloc[0]
    print(f"  {eid} {r.fault_type} viteza on {r.sensor_tag} [{r.detectable_utc} .. {r.end_utc}]", end="")
    grp = feats[feats.asset_id == asset].sort_values("window_start_utc")
    m = (grp["window_start_utc"] >= r.detectable_utc) & (grp["window_start_utc"] <= r.end_utc)
    seg = grp[m]
    if len(seg) == 0:
        print(" -> no 1-min features in window (sparse wireless channel)"); continue

    def show(c):
        col = f"{c}__mean"; stdc = f"{c}__std"
        if col not in seg.columns:
            return "n/a"
        v = seg[col].dropna()
        if len(v) == 0:
            return "no-data"
        s = seg[stdc].dropna() if stdc in seg.columns else None
        st = f", std_med={s.median():.3g}" if s is not None and len(s) else ""
        return f"mean={v.mean():.4g}, range=[{v.min():.4g}, {v.max():.4g}]{st}"

    if r.sensor_tag != "GATEWAY":
        print(f" -> {show(r.sensor_tag)}")
        # covariates: pick 2 physically related channels that exist
        cov = {"bearing_temp_c": ["vibration_accel_rms_g", "motor_current_a"],
               "discharge_pressure_kpa": ["flow_m3_h", "motor_current_a"],
               "suction_pressure_kpa": ["flow_m3_h", "motor_current_a"],
               "motor_current_a": ["motor_power_kw", "flow_m3_h"],
               "flow_m3_h": ["motor_current_a", "discharge_pressure_kpa"]}
        for cc in cov.get(r.sensor_tag, [])[:2]:
            print(f"     covariate {cc:24s} {show(cc)}")

