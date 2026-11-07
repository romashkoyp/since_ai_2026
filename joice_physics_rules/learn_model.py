"""Physics + learning.  The physics detector raises the alarms; a model learned from data
decides the final fault type (and can cancel alarms it is sure are false).

Run from the challenge folder (with .venv active):
    python3 joice_physics_rules/learn_model.py build/generated

LEARN from : company train pumps PUMP-01..07 + generated batches stress_100..111
TEST on    : company validation PUMP-08/09   + generated batches stress_112..116  (never seen while learning)
Slow part (running the physics on every pump) is cached in build/alert_cache/, so a second run takes seconds.
"""
import sys, os, glob, pickle, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "build_training_table.py")).read().split("root = sys.argv")[0])
from sklearn.ensemble import HistGradientBoostingClassifier

SENSOR = {"SENSOR_DRIFT", "SENSOR_STUCK", "SENSOR_CALIBRATION_SHIFT", "SENSOR_NOISE_SPIKES", "COMMUNICATION_LOSS"}
CACHE = "build/alert_cache"; os.makedirs(CACHE, exist_ok=True)

def alert_table(name, assets, feat, ctx, snap, ev, bn, vf=None):
    """run the physics detector on one dataset -> one row per alarm with physics features + true answer"""
    path = f"{CACHE}/{name}.pkl"
    if os.path.exists(path): return pickle.load(open(path, "rb"))
    zf = B.zscores(B.regime_frame(feat, assets)); zf["window_start_utc"] = pd.to_datetime(zf.window_start_utc, utc=True)
    if vf is None: vf = vib_features(snap, assets) if snap is not None and len(snap) else pd.DataFrame()
    snapf = diag2.snap_ratios(vf) if len(vf) else pd.DataFrame(columns=["asset_id", "time", "r_bpfo", "r_1x", "r_2x", "r_hf", "b_idx", "r_bidx"])
    zp = diag2.prep(zf, ctx, snapf, assets); al = diag2.detect(zp, assets)
    A = assets.set_index("asset_id"); rows = []
    for _, x in al.iterrows():
        t = pd.Timestamp(x.alert_time_utc); ft, fc, eid = true_label(ev, x.asset_id, t)
        row = dict(dataset=name, asset_id=x.asset_id, alert_time_utc=x.alert_time_utc, rule_class=x.event_class,
                   rule_type=x.fault_type, rule_conf=x.confidence, evidence=x.evidence, action=x.recommended_action,
                   tier=A.loc[x.asset_id, "instrumentation_tier"], control=A.loc[x.asset_id, "control"],
                   profile=A.loc[x.asset_id, "profile"], true_type=ft)
        row.update(features_at(zp, x.asset_id, t)); rows.append(row)
    out = dict(table=pd.DataFrame(rows), assets=assets, ev=ev, bn=bn)
    pickle.dump(out, open(path, "wb")); return out

def company(split):
    D = "data/full"; assets = pd.read_csv(f"{D}/assets.csv"); assets = assets[assets.split == split]
    feat = pd.read_parquet(f"{D}/features_1min.parquet"); feat = feat[feat.asset_id.isin(assets.asset_id)]
    ctx = pd.read_csv(f"{D}/operating_context.csv"); ctx["t"] = pd.to_datetime(ctx.timestamp_utc, utc=True)
    vf = pd.read_csv("vibration_features.csv"); vf = vf[vf.asset_id.isin(assets.asset_id)]
    return alert_table(f"company_{split}", assets, feat, ctx, None, pd.read_csv(f"{D}/events_{split}.csv"),
                       pd.read_csv(f"{D}/benign_windows_train_validation.csv"), vf)

def generated(bdir):
    P, Q = os.path.join(bdir, "public"), os.path.join(bdir, "private")
    ctx = pd.read_csv(f"{P}/operating_context.csv"); ctx["t"] = pd.to_datetime(ctx.timestamp_utc, utc=True)
    return alert_table(os.path.basename(bdir), pd.read_csv(f"{P}/assets.csv"), pd.read_parquet(f"{P}/features_1min.parquet"), ctx,
                       pd.read_parquet(f"{P}/vibration_snapshots.parquet"), pd.read_csv(f"{Q}/events_stress_all.csv"),
                       pd.read_csv(f"{P}/benign_windows_stress.csv"))

def _gen_job(b):
    generated(b); return os.path.basename(b)

def main():
  global model, cols
  # ---------------------------------------------------------------- collect
  root = sys.argv[1] if len(sys.argv) > 1 else "build/generated"
  gen = sorted(glob.glob(os.path.join(root, "stress_*")))
  n_learn = int(round(len(gen) * 0.7))
  learn_sets, test_sets = [], []
  print("running physics detector on all cores (cached after first run)...", flush=True)
  from concurrent.futures import ProcessPoolExecutor
  todo = [b for b in gen if not os.path.exists(f"{CACHE}/{os.path.basename(b)}.pkl")]
  if todo:
      with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as ex:
          for nm in ex.map(_gen_job, todo): print("  physics done:", nm, flush=True)
  learn_sets.append(company("train")); print("  company train done", flush=True)
  test_sets.append(company("validation")); print("  company validation done", flush=True)
  for i, b in enumerate(gen):
      d = generated(b); (learn_sets if i < n_learn else test_sets).append(d)
      print(f"  {os.path.basename(b)} done ({'learn' if i < n_learn else 'TEST'})", flush=True)

  # ---------------------------------------------------------------- features
  def matrix(T, cols=None):
      num = T[[c for c in T.columns if c.startswith(("z_", "zs_", "ph_", "r_", "flat_")) or c in
               ("b_idx", "since_start", "prev_stop_min", "sea_state_hs_m", "suction_static_head_m", "steady", "gap", "rule_conf")]]
      num = num.apply(pd.to_numeric, errors="coerce")
      cat = pd.get_dummies(T[["rule_type", "tier", "control", "profile"]].astype(str), dtype=float)
      X = pd.concat([num, cat], axis=1)
      return X.reindex(columns=cols, fill_value=np.nan) if cols is not None else X

  L = pd.concat([d["table"] for d in learn_sets], ignore_index=True)
  X = matrix(L); cols = list(X.columns); y = L.true_type.values
  model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=8,
                                         l2_regularization=1.0, class_weight="balanced", random_state=7).fit(X, y)
  pickle.dump(dict(model=model, cols=cols), open("build/learned_model.pkl", "wb"))
  print(f"\nlearned from {len(L)} alarms ({(L.true_type == 'NO_FAULT').sum()} false alarms), {len(set(y))} classes")

  # ---------------------------------------------------------------- apply + score
  P_TYPE, P_DROP = 0.85, 0.90
  def apply(d):
      T = d["table"].copy()
      if not len(T): return T, T
      prob = model.predict_proba(matrix(T, cols)); cls = model.classes_
      best = prob.argmax(1); pbest = prob.max(1)
      new = T.rule_type.copy()
      take = (pbest >= P_TYPE) & (cls[best] != "NO_FAULT")
      new[take] = cls[best][take]
      drop = (cls[best] == "NO_FAULT") & (pbest >= P_DROP)
      T["final_type"] = new
      rules = T.rename(columns={"rule_type": "fault_type"})
      learned = T[~drop].copy(); learned["fault_type"] = learned.final_type
      def fmt(df):
          df = df.copy(); df["event_class"] = np.where(df.fault_type.isin(SENSOR), "SENSOR", "MACHINE")
          df["confidence"] = df.rule_conf; df["recommended_action"] = df.action
          return df[["asset_id", "alert_time_utc", "event_class", "fault_type", "confidence", "evidence", "recommended_action"]]
      return fmt(rules), fmt(learned)

  res = []
  for d in test_sets:
      split = d["assets"].split.iloc[0]
      pr_rules, pr_learn = apply(d)
      for nm, pr in (("PHYSICS", pr_rules), ("PHYSICS+LEARNING", pr_learn)):
          r = score(pr, d["ev"], d["assets"], d["bn"], split); pe = pd.DataFrame(r["per_event"])
          res.append(dict(test=d["table"].dataset.iloc[0] if len(d["table"]) else "?", model=nm, score=r["composite_score"],
                          correct=int(pe.type_correct.sum()), faults=len(pe), false_per_day=r["false_alerts_per_asset_day"]))
  R = pd.DataFrame(res); R.to_csv("build/learning_results.csv", index=False)
  print("\n=== TEST pumps (never used for learning) ===")
  print(R.pivot(index="test", columns="model", values="score").round(1).to_string())
  s = R.groupby("model").agg(avg_score=("score", "mean"), correct=("correct", "sum"), faults=("faults", "sum"), false_per_day=("false_per_day", "mean")).round(2)
  print("\n" + s.to_string())
  print("\nmodel saved to build/learned_model.pkl")


if __name__ == "__main__":
    main()
