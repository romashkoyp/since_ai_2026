"""Learned ALARM: a model that learns, minute by minute, when a fault is visible.
It adds alarms the physics rules miss; the physics rules still NAME every alarm.

Run from the challenge folder (with .venv active):
  python3 joice_physics_rules/alarm_model.py build build/generated   # step 1: physics on every pump, minute tables (cached)
  python3 joice_physics_rules/alarm_model.py train build/generated   # step 2: learn when a fault is visible
  python3 joice_physics_rules/alarm_model.py test  build/generated   # step 3: physics vs physics+learned alarm

Split (by batch, sorted): first 70 % LEARN, next 10 % TUNE (choose sensitivity), last 20 % + company validation = TEST.
"""
import sys, os, glob, pickle, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "build_training_table.py")).read().split("root = sys.argv")[0])
CACHE = "build/minute_cache_v2"; os.makedirs(CACHE, exist_ok=True)
SENSOR = {"SENSOR_DRIFT", "SENSOR_STUCK", "SENSOR_CALIBRATION_SHIFT", "SENSOR_NOISE_SPIKES", "COMMUNICATION_LOSS"}

# ------------------------------------------------------------------ data
def load_source(name):
    if name.startswith("company_"):
        split = name.split("_", 1)[1]; D = "data/full"
        assets = pd.read_csv(f"{D}/assets.csv"); assets = assets[assets.split == split]
        feat = pd.read_parquet(f"{D}/features_1min.parquet"); feat = feat[feat.asset_id.isin(assets.asset_id)]
        ctx = pd.read_csv(f"{D}/operating_context.csv"); ev = pd.read_csv(f"{D}/events_{split}.csv")
        bn = pd.read_csv(f"{D}/benign_windows_train_validation.csv")
        vf = pd.read_csv("vibration_features.csv"); vf = vf[vf.asset_id.isin(assets.asset_id)]
    else:
        P, Q = f"{ROOT_DIR}/{name}/public", f"{ROOT_DIR}/{name}/private"
        assets = pd.read_csv(f"{P}/assets.csv"); feat = pd.read_parquet(f"{P}/features_1min.parquet")
        ctx = pd.read_csv(f"{P}/operating_context.csv"); ev = pd.read_csv(f"{Q}/events_stress_all.csv")
        bn = pd.read_csv(f"{P}/benign_windows_stress.csv")
        vf = vib_features(pd.read_parquet(f"{P}/vibration_snapshots.parquet"), assets)
    ctx["t"] = pd.to_datetime(ctx.timestamp_utc, utc=True)
    return assets, feat, ctx, ev, bn, vf

def label_minutes(zp, ev):
    """1 = an observable fault is visible (detectable..end), 0 = healthy, -1 = ambiguous (onset..detectable)"""
    y = pd.Series(0, index=zp.index, dtype="int8")
    t = zp.window_start_utc
    for _, e in ev.iterrows():
        if str(e.get("observable", True)).lower() in ("false", "0"): continue
        on = pd.Timestamp(e.onset_utc); det = pd.Timestamp(e.detectable_utc) if isinstance(e.detectable_utc, str) else on
        end = pd.Timestamp(e.end_utc) if isinstance(e.end_utc, str) else t.max()
        m = zp.asset_id.eq(e.asset_id)
        y[m & (t >= on) & (t < det) & (y == 0)] = -1
        y[m & (t >= det) & (t <= end)] = 1
    return y

def build_one(name):
    path = f"{CACHE}/{name}.parquet"
    if os.path.exists(path): return name
    assets, feat, ctx, ev, bn, vf = load_source(name)
    zf = B.zscores(B.regime_frame(feat, assets)); zf["window_start_utc"] = pd.to_datetime(zf.window_start_utc, utc=True)
    snapf = diag2.snap_ratios(vf) if len(vf) else pd.DataFrame(columns=["asset_id", "time", "r_bpfo", "r_1x", "r_2x", "r_hf", "b_idx", "r_bidx"])
    zp = diag2.prep(zf, ctx, snapf, assets)
    A = assets.set_index("asset_id")
    zp["tier_code"] = zp.asset_id.map(A.instrumentation_tier).map({"T0_LEGACY": 0, "T1_RETROFIT": 1, "T2_FULL": 2})
    zp["ctl_code"] = zp.asset_id.map(A.control).map({"FIXED_SPEED": 0, "VFD_TEMPERATURE": 1, "VFD_PRESSURE": 2, "FLOW_VALVE": 3})
    # slow-change features (trailing only -> causal): 60 min average of every z
    for c in [c for c in zp.columns if c.startswith("z_")]:
        zp["m60_" + c[2:]] = zp.groupby("asset_id")[c].transform(lambda s: s.rolling(60, min_periods=20).mean())
    zp["label"] = label_minutes(zp, ev)
    for c in zp.columns:
        if zp[c].dtype == "float64": zp[c] = zp[c].astype("float32")
        if c in ("asset_id", "operating_mode", "ph_pi_who"):
            zp[c] = zp[c].astype(str)
        elif zp[c].dtype == "object" or zp[c].dtype == "bool":          # yes/no flags (some with gaps) -> 1.0 / 0.0 / NaN
            zp[c] = zp[c].map(lambda v: np.nan if v is None or (isinstance(v, float) and np.isnan(v)) else float(bool(v))).astype("float32")
    zp.to_parquet(path); pickle.dump(dict(assets=assets, ev=ev, bn=bn), open(f"{CACHE}/{name}.meta.pkl", "wb"))
    return name

def feature_cols(df):
    num = [c for c in df.columns if c.startswith(("z_", "zs_", "m60_", "flat_", "r_")) or
           (c.startswith("ph_") and df[c].dtype != object) or c in
           ("b_idx", "since_start", "prev_stop_min", "sea_state_hs_m", "suction_static_head_m", "steady", "gap",
            "running_fraction", "tier_code", "ctl_code")]
    return [c for c in num if c != "ph_has_flow" and str(df[c].dtype) != "object"]

def splits(names):
    gen = [n for n in names if not n.startswith("company_")]
    n = len(gen); a, b = int(n * 0.7), int(n * 0.8)
    return ["company_train"] + gen[:a], gen[a:b], ["company_validation"] + gen[b:]

# ------------------------------------------------------------------ alarm from probabilities
def learned_alarms(zp, prob, assets, thr, persist, physics_alerts):
    ctl = dict(zip(assets.asset_id, assets.control)); rows = []
    have = {}
    for x in physics_alerts.itertuples(): have.setdefault(x.asset_id, []).append(pd.Timestamp(x.alert_time_utc))
    zp = zp.assign(_p=prob)
    for a, g in zp.groupby("asset_id", sort=False):
        g = g.reset_index(drop=True); run = 0; last = None
        on = (g._p.values >= thr) & g.operating_mode.eq("RUNNING").values
        for j in range(len(g)):
            run = run + 1 if on[j] else 0
            if run != persist: continue
            t = g.window_start_utc.iloc[j] + pd.Timedelta(minutes=1)
            if last is not None and t - last < B.REFRACTORY: continue
            if any(abs((t - e).total_seconds()) < 4 * 3600 for e in have.get(a, [])): continue   # physics already on it
            cls, ft, conf, evd, act = diag2.diagnose2(g, j, 6.0, ctl.get(a))
            rows.append(dict(asset_id=a, alert_time_utc=t.strftime("%Y-%m-%dT%H:%M:%SZ"), event_class=cls, fault_type=ft,
                             confidence=round(float(g._p.iloc[j]), 2), evidence="learned alarm (p=%.2f); " % g._p.iloc[j] + evd,
                             recommended_action=act))
            last = t
    return pd.DataFrame(rows, columns=B._COLS)

# ------------------------------------------------------------------ main
def main():
    global ROOT_DIR
    step = sys.argv[1]; ROOT_DIR = sys.argv[2] if len(sys.argv) > 2 else "build/generated"
    names = ["company_train", "company_validation"] + sorted(os.path.basename(b) for b in glob.glob(f"{ROOT_DIR}/stress_*"))
    learn, tune, test = splits(names)
    if step == "build":
        from concurrent.futures import ProcessPoolExecutor
        todo = [n for n in names if not os.path.exists(f"{CACHE}/{n}.parquet")]
        print(f"{len(names) - len(todo)} cached, {len(todo)} to build (all cores)...", flush=True)
        with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1), initializer=_init, initargs=(ROOT_DIR,)) as ex:
            for nm in ex.map(build_one, todo): print("  built", nm, flush=True)
        print("done. learn:", len(learn), " tune:", len(tune), " test:", len(test))
    elif step == "train":
        from sklearn.ensemble import HistGradientBoostingClassifier
        parts = []
        for n in learn:
            d = pd.read_parquet(f"{CACHE}/{n}.parquet"); d = d[d.label >= 0]
            pos, neg = d[d.label == 1], d[d.label == 0]
            k = max(1, int(round(len(pos) / max(len(neg), 1) * 3)))           # roughly 1 fault-minute per 3 healthy minutes
            parts.append(pd.concat([pos.iloc[::max(k, 3)], neg.iloc[::3]]))   # thin out: neighbouring minutes are near-copies
        D = pd.concat(parts, ignore_index=True); cols = feature_cols(D)
        print(f"learning from {len(D):,} minutes ({int(D.label.sum()):,} fault-visible) of {len(learn)} datasets, {len(cols)} features", flush=True)
        m = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200,
                                           l2_regularization=1.0, random_state=7).fit(D[cols].astype("float32"), D.label)
        pickle.dump(dict(model=m, cols=cols), open("build/alarm_model.pkl", "wb")); print("saved build/alarm_model.pkl")
    elif step == "test":
        M = pickle.load(open("build/alarm_model.pkl", "rb")); m, cols = M["model"], M["cols"]
        SETTINGS = [(0.9, 30), (0.9, 60), (0.95, 30), (0.95, 60), (0.98, 60)]
        res = []
        for part, sets in (("tune", tune), ("test", test)):
            for n in sets:
                zp = pd.read_parquet(f"{CACHE}/{n}.parquet"); meta = pickle.load(open(f"{CACHE}/{n}.meta.pkl", "rb"))
                assets, ev, bn = meta["assets"], meta["ev"], meta["bn"]; sp = assets.split.iloc[0]
                zp["window_start_utc"] = pd.to_datetime(zp.window_start_utc, utc=True)
                for c in ("steady", "gap"): zp[c] = zp[c].fillna(0).astype(bool)
                phys = diag2.detect(zp, assets)
                prob = m.predict_proba(zp.reindex(columns=cols).astype("float32"))[:, 1]
                r = score(phys, ev, assets, bn, sp); pe = pd.DataFrame(r["per_event"])
                res.append(dict(part=part, set=n, setting="physics only", score=r["composite_score"], detected=int(pe.detected.sum()),
                                correct=int(pe.type_correct.sum()), faults=len(pe), false_day=r["false_alerts_per_asset_day"]))
                line = f"{part:4s} {n:20s} physics {r['composite_score']:5.1f}"
                for thr, per in SETTINGS:
                    extra = learned_alarms(zp, prob, assets, thr, per, phys)
                    allal = pd.concat([phys, extra], ignore_index=True).sort_values(["asset_id", "alert_time_utc"])
                    r2 = score(allal, ev, assets, bn, sp); pe2 = pd.DataFrame(r2["per_event"])
                    res.append(dict(part=part, set=n, setting=f"+learned p>={thr} for {per} min", score=r2["composite_score"],
                                    detected=int(pe2.detected.sum()), correct=int(pe2.type_correct.sum()), faults=len(pe2),
                                    false_day=r2["false_alerts_per_asset_day"]))
                    line += f" | {thr}/{per}: {r2['composite_score']:5.1f}"
                print(line, flush=True)
        R = pd.DataFrame(res); R.to_csv("build/alarm_results.csv", index=False)
        for part in ("tune", "test"):
            s = R[R.part == part].groupby("setting").agg(avg_score=("score", "mean"), detected=("detected", "sum"),
                    correct=("correct", "sum"), faults=("faults", "sum"), false_per_day=("false_day", "mean")).round(2)
            print(f"\n=== {part.upper()} ({R[R.part == part].set.nunique()} sets) ===\n" + s.sort_values("avg_score", ascending=False).to_string())
        print("\nPick the setting that is best on TUNE; the TEST table shows how it does on data never used for anything.")

def _init(root):
    global ROOT_DIR; ROOT_DIR = root

if __name__ == "__main__":
    main()
