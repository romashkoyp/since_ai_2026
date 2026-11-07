"""Does the physics diagnostician generalise?  Two tests, no tuning on either.
  python3 joice_physics_rules/generalisation_test.py "$PWD" downgrade      # val pumps re-scored with fewer sensors (T2->T1->T0)
  python3 joice_physics_rules/generalisation_test.py "$PWD" stress <dir>    # unseen random pumps from make_dataset --tier stress
"""
import sys, os, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
R = sys.argv[1]; MODE = sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [HERE, os.path.join(R, "src")]
from retrofit_sim import baselines as B
from retrofit_sim.scoring import score
import diag2
from scipy.signal import butter, sosfiltfilt, hilbert

def vib_features(snap, assets):
    A = assets.set_index("asset_id"); rows = []
    for _, s in snap.iterrows():
        a = A.loc[s.asset_id]; x = np.asarray(s.samples, float); x -= x.mean()
        fs = s.sample_rate_hz; f1 = s.rpm_at_capture / 60; win = np.hanning(len(x))
        bp = butter(4, [2000, 3600], btype="band", fs=fs, output="sos")
        env = np.abs(hilbert(sosfiltfilt(bp, x))); env -= env.mean()
        es = np.abs(np.fft.rfft(env * win)) * 2 / win.sum(); sp = np.abs(np.fft.rfft(x * win)) * 2 / win.sum()
        fr = np.fft.rfftfreq(len(x), 1 / fs)
        amp = lambda S, f: (float(S[(fr > f * .97) & (fr < f * 1.03)].max()) if ((fr > f * .97) & (fr < f * 1.03)).any() else float("nan"))  # pump stopped -> no line
        hp = butter(4, 4000, btype="high", fs=fs, output="sos")
        rows.append(dict(asset_id=s.asset_id, time=s.timestamp_utc, a_1x=amp(sp, f1), a_2x=amp(sp, 2 * f1),
                         env_bpfo=amp(es, a.bearing_bpfo_order * f1), hf_rms=float(np.sqrt(np.mean(sosfiltfilt(hp, x) ** 2)))))
    return pd.DataFrame(rows, columns=["asset_id", "time", "a_1x", "a_2x", "env_bpfo", "hf_rms"])

def run(feat, assets, ctx, vf, events, benign, split, label):
    zf = B.zscores(B.regime_frame(feat, assets)); zf["window_start_utc"] = pd.to_datetime(zf.window_start_utc, utc=True)
    snapf = diag2.snap_ratios(vf) if len(vf) else pd.DataFrame(columns=["asset_id", "time", "r_bpfo", "r_1x", "r_2x", "r_hf", "b_idx", "r_bidx"])
    zp = diag2.prep(zf, ctx, snapf, assets)
    for name, pr in (("B1", B.b1_threshold(zf, 6, 15)), ("PHYSICS", diag2.detect(zp, assets))):
        r = score(pr, events, assets, benign, split); pe = pd.DataFrame(r["per_event"])
        print(f"{label:22s} {name:8s} recall {r['event_recall']:.2f} fa {r['false_alerts_per_asset_day']:.3f} composite {r['composite_score']:5.1f}  fault-type recall {r['fault_type_recall']:.2f}  "
              f"false alerts/day {r['false_alerts_per_asset_day']:.3f}  correct {pe.type_correct.sum()}/{len(pe)}")

if MODE == "downgrade":
    D = os.path.join(R, "data/full")
    assets0 = pd.read_csv(f"{D}/assets.csv"); feat0 = pd.read_parquet(f"{D}/features_1min.parquet")
    ctx = pd.read_csv(f"{D}/operating_context.csv"); ctx["t"] = pd.to_datetime(ctx.timestamp_utc, utc=True)
    ev = pd.read_csv(f"{D}/events_validation.csv"); bn = pd.read_csv(f"{D}/benign_windows_train_validation.csv")
    vf0 = pd.read_csv(os.path.join(R, "vibration_features.csv"))
    T0 = ["discharge_pressure_kpa", "motor_current_a", "fluid_temp_c", "ambient_temp_c", "motor_speed_rpm", "motor_power_kw"]
    T1 = T0 + ["suction_pressure_kpa", "bearing_temp_c", "vibration_rms_mm_s", "vibration_accel_rms_g", "vibration_crest_factor"]
    for tier, keep in (("as delivered", None), ("downgraded to T1", T1), ("downgraded to T0", T0)):
        feat = feat0.copy(); assets = assets0.copy(); vf = vf0
        if keep is not None:
            drop = [c for c in feat.columns if "__" in c and c.split("__")[0] not in keep]
            feat[drop] = np.nan
            assets["channels_available"] = assets.channels_available.map(lambda s: "|".join(c for c in s.split("|") if c in keep))
            if keep is T0: vf = vf0.iloc[0:0]
        ok = assets.split == "validation"
        ev_k = ev if keep is None else ev[ev.evidence_channels.fillna("").map(lambda s: any(c in keep for c in s.split(",")) or s == "")]
        run(feat[feat.asset_id.isin(assets[ok].asset_id)], assets, ctx, vf, ev_k, bn, "validation", tier)
elif MODE == "stress":
    S = sys.argv[3]; P = os.path.join(S, "public"); Q = os.path.join(S, "private")
    assets = pd.read_csv(f"{P}/assets.csv"); feat = pd.read_parquet(f"{P}/features_1min.parquet")
    ctx = pd.read_csv(f"{P}/operating_context.csv"); ctx["t"] = pd.to_datetime(ctx.timestamp_utc, utc=True)
    ev = pd.read_csv(f"{Q}/events_stress_all.csv")
    bn = pd.read_csv(f"{P}/benign_windows_stress.csv") if os.path.exists(f"{P}/benign_windows_stress.csv") else None
    sp = f"{P}/vibration_snapshots.parquet"
    vf = vib_features(pd.read_parquet(sp), assets) if os.path.exists(sp) else pd.DataFrame()
    print(assets[["asset_id", "instrumentation_tier", "control", "profile"]].to_string(index=False))
    run(feat, assets, ctx, vf, ev, bn, assets.split.iloc[0], "stress (unseen pumps)")
