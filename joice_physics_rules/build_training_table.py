"""Run the physics detector on every generated batch, score it against the answer sheets,
and export one training table for the ML model.

Run from the challenge folder (with the .venv active):
    python3 joice_physics_rules/build_training_table.py build/generated

Outputs (in build/):
    generated_scores.csv   - B1 vs physics score per batch
    alerts_training.csv    - one row per alert: physics features + rule answer + TRUE answer
"""
import sys, os, glob, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "src")]
from retrofit_sim import baselines as B
from retrofit_sim.scoring import score
import diag2
from scipy.signal import butter, sosfiltfilt, hilbert

def vib_features(snap, assets):
    A = assets.set_index("asset_id"); rows = []
    for _, s in snap.iterrows():
        a = A.loc[s.asset_id]; x = np.asarray(s.samples, float); x -= x.mean()
        fs = s.sample_rate_hz; f1 = s.rpm_at_capture / 60; win = np.hanning(len(x))
        env = np.abs(hilbert(sosfiltfilt(butter(4, [2000, 3600], btype="band", fs=fs, output="sos"), x))); env -= env.mean()
        es = np.abs(np.fft.rfft(env * win)) * 2 / win.sum(); sp = np.abs(np.fft.rfft(x * win)) * 2 / win.sum()
        fr = np.fft.rfftfreq(len(x), 1 / fs)
        amp = lambda S, f: float(S[(fr > f * .97) & (fr < f * 1.03)].max())
        rows.append(dict(asset_id=s.asset_id, time=s.timestamp_utc, a_1x=amp(sp, f1), a_2x=amp(sp, 2 * f1),
                         env_bpfo=amp(es, a.bearing_bpfo_order * f1),
                         hf_rms=float(np.sqrt(np.mean(sosfiltfilt(butter(4, 4000, btype="high", fs=fs, output="sos"), x) ** 2)))))
    return pd.DataFrame(rows, columns=["asset_id", "time", "a_1x", "a_2x", "env_bpfo", "hf_rms"])

FEATS = None
def features_at(zp, a, t):
    g = zp[zp.asset_id == a].set_index("window_start_utc")
    row = g.loc[:t - pd.Timedelta(minutes=1)]
    if not len(row): return {}
    r = row.iloc[-1]
    keep = [c for c in r.index if c.startswith(("z_", "zs_", "ph_", "r_", "flat_")) or c in
            ("b_idx", "since_start", "prev_stop_min", "sea_state_hs_m", "suction_static_head_m", "steady", "gap")]
    out = {}
    for c in keep:
        v = r[c]
        if isinstance(v, (bool, np.bool_)): v = int(v)
        if isinstance(v, (int, float, np.integer, np.floating)): out[c] = float(v)
    return out

def true_label(ev, a, t):
    e = ev[ev.asset_id == a]
    on = pd.to_datetime(e.onset_utc, utc=True); end = pd.to_datetime(e.end_utc, utc=True)
    act = e[(on - pd.Timedelta("30min") <= t) & (end.isna() | (t <= end + pd.Timedelta("2h")))]
    if not len(act): return "NO_FAULT", "NONE", ""
    last = act.assign(_on=pd.to_datetime(act.onset_utc, utc=True)).sort_values("_on").iloc[-1]
    return last.fault_type, last.event_class, last.event_id

root = sys.argv[1] if len(sys.argv) > 1 else "build/generated"
batches = sorted(glob.glob(os.path.join(root, "stress_*")))
scores, table = [], []
for bdir in batches:
    P, Q = os.path.join(bdir, "public"), os.path.join(bdir, "private")
    try:
        assets = pd.read_csv(f"{P}/assets.csv"); feat = pd.read_parquet(f"{P}/features_1min.parquet")
        ctx = pd.read_csv(f"{P}/operating_context.csv"); ctx["t"] = pd.to_datetime(ctx.timestamp_utc, utc=True)
        ev = pd.read_csv(f"{Q}/events_stress_all.csv")
        bn = pd.read_csv(f"{P}/benign_windows_stress.csv") if os.path.exists(f"{P}/benign_windows_stress.csv") else None
        sp = f"{P}/vibration_snapshots.parquet"
        vf = vib_features(pd.read_parquet(sp), assets) if os.path.exists(sp) else pd.DataFrame()
    except Exception as ex:
        print(f"{os.path.basename(bdir)}: skipped ({ex})"); continue
    zf = B.zscores(B.regime_frame(feat, assets)); zf["window_start_utc"] = pd.to_datetime(zf.window_start_utc, utc=True)
    snapf = diag2.snap_ratios(vf) if len(vf) else pd.DataFrame(columns=["asset_id", "time", "r_bpfo", "r_1x", "r_2x", "r_hf", "b_idx", "r_bidx"])
    zp = diag2.prep(zf, ctx, snapf, assets)
    b1 = B.b1_threshold(zf, 6, 15); ph = diag2.detect(zp, assets)
    split = assets.split.iloc[0]
    rb, rp = score(b1, ev, assets, bn, split), score(ph, ev, assets, bn, split)
    pe = pd.DataFrame(rp["per_event"]); pb = pd.DataFrame(rb["per_event"])
    scores.append(dict(batch=os.path.basename(bdir), B1=round(rb["composite_score"], 1), PHYSICS=round(rp["composite_score"], 1),
                       B1_correct=int(pb.type_correct.sum()), PHYSICS_correct=int(pe.type_correct.sum()), faults=len(pe),
                       PHYSICS_false_per_day=round(rp["false_alerts_per_asset_day"], 3),
                       T0_pumps=int((assets.instrumentation_tier == "T0_LEGACY").sum())))
    print(f"{os.path.basename(bdir):12s} B1 {rb['composite_score']:5.1f} | PHYSICS {rp['composite_score']:5.1f} | correct {int(pe.type_correct.sum())}/{len(pe)}", flush=True)
    A = assets.set_index("asset_id")
    for _, al in ph.iterrows():
        t = pd.Timestamp(al.alert_time_utc)
        ft, fc, eid = true_label(ev, al.asset_id, t)
        row = dict(batch=os.path.basename(bdir), asset_id=al.asset_id, alert_time_utc=al.alert_time_utc,
                   tier=A.loc[al.asset_id, "instrumentation_tier"], control=A.loc[al.asset_id, "control"],
                   profile=A.loc[al.asset_id, "profile"], rule_type=al.fault_type, rule_class=al.event_class,
                   rule_conf=al.confidence, rule_evidence=al.evidence, true_type=ft, true_class=fc, true_event=eid)
        row.update(features_at(zp, al.asset_id, t)); table.append(row)

os.makedirs("build", exist_ok=True)
S = pd.DataFrame(scores); S.to_csv("build/generated_scores.csv", index=False)
T = pd.DataFrame(table); T.to_csv("build/alerts_training.csv", index=False)
print("\n=== SUMMARY over", len(S), "batches,", 6 * len(S), "pumps ===")
print(f"average score      B1 {S.B1.mean():.1f}   PHYSICS {S.PHYSICS.mean():.1f}")
print(f"correct fault type B1 {S.B1_correct.sum()}/{S.faults.sum()}   PHYSICS {S.PHYSICS_correct.sum()}/{S.faults.sum()}")
print(f"physics beats B1 in {(S.PHYSICS > S.B1).sum()} of {len(S)} batches")
print(f"training table: {len(T)} alerts, {(T.true_type != 'NO_FAULT').sum()} real faults, {(T.true_type == 'NO_FAULT').sum()} false alarms")
print(f"rule already correct on {(T.rule_type == T.true_type).mean()*100:.0f}% of alerts")
print("saved build/generated_scores.csv and build/alerts_training.csv")
