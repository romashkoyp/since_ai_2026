# SENTRY trained diagnosis head (fits on LUMI-generated data, applies on real assets).
#
#   FIT:    python sentry/lumi_train.py fit --shards <gen_out_dir> --out build/mlmodel [--max-pumps N]
#   APPLY:  python sentry/lumi_train.py apply --model build/mlmodel --data data/full \
#              --assets PUMP-08 PUMP-09 --out build/predictions_ml_validation.csv
#   Score:  python -m retrofit_sim score --predictions <that csv> \
#              --events data/full/events_validation.csv --assets data/full/assets.csv \
#              --benign data/full/benign_windows_train_validation.csv --split validation
#
# Schema: shards contain the CANONICAL feature frame (sentry.ml_features.feature_columns)
# plus per-minute gate/benign/label(index_col) columns. LightGBM multiclass over
# {NONE, BENIGN, 8 machine types, 5 sensor types}; pump-grouped folds; per-class Platt
# calibration fitted in LOGIT space on the held-out fold.
import argparse
import json
import os
import pickle
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

import numpy as np
import pandas as pd

from sentry.ml_features import build_ml_features, feature_columns
from sentry.detect import AssetSentry as _A

CLASSES = ["NONE", "BENIGN", "BEARING_WEAR", "SUCTION_STRAINER_CLOGGING", "CAVITATION",
           "DISCHARGE_RESTRICTION", "MISALIGNMENT", "IMBALANCE", "IMPELLER_WEAR", "AIR_ENTRAINMENT",
           "SENSOR_DRIFT", "SENSOR_STUCK", "SENSOR_CALIBRATION_SHIFT", "SENSOR_NOISE_SPIKES",
           "COMMUNICATION_LOSS"]
MACHINE_CLASSES = set(CLASSES[2:10])
SEED = 7


def logit(p, eps=1e-6):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def fold_of(pump_id: str, n_folds: int = 5) -> int:
    h = (sum(hash(c) for c in pump_id) * 2654435761) & 0x7FFFFFFF
    return h % n_folds


def load_training_table(shard_dir: Path, max_pumps=None):
    parts, metas = [], []
    for sp in sorted(shard_dir.glob("shard_*.parquet")):
        parts.append(pd.read_parquet(sp))
    for mp in sorted(shard_dir.glob("meta_*.parquet")):
        metas.append(pd.read_parquet(mp))
    if not parts:
        raise SystemExit(f"no shard_*.parquet under {shard_dir}")
    df = pd.concat(parts, ignore_index=True)
    meta = pd.concat(metas, ignore_index=True)
    if max_pumps:
        keep = set(pd.Series(df.pump_id.unique()).sample(min(max_pumps, len(df.pump_id.unique())),
                                                         random_state=SEED))
        df = df[df.pump_id.isin(keep)]
    return df, meta


def fit(args):
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score, classification_report

    t0 = time.time()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"[fit] loading shards from {args.shards} ...", flush=True)
    df, _meta = load_training_table(Path(args.shards), args.max_pumps)
    fcols = feature_columns()
    df["pump_fold"] = df["pump_id"].map(lambda x: fold_of(x, args.folds))
    tr = df[df.pump_fold != args.holdout_fold]
    va = df[df.pump_fold == args.holdout_fold]
    if len(va) == 0:
        va = tr
    y = df["label"].map(lambda v: CLASSES.index(v) if v in CLASSES else 0).to_numpy()
    dummies = pd.get_dummies(df[["tier", "control", "profile"]], columns=["tier", "control", "profile"])
    dummy_cols = list(dummies.columns)
    X = np.hstack([df[fcols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32),
                   dummies.to_numpy(dtype=np.float32)])
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    Xtr, Xva = X[df.pump_fold != args.holdout_fold], X[df.pump_fold == args.holdout_fold]
    ytr, yva = y[df.pump_fold != args.holdout_fold], y[df.pump_fold == args.holdout_fold]
    if len(yva) == 0:
        Xva, yva = Xtr, ytr
    cls_counts = np.bincount(y, minlength=len(CLASSES))
    class_weight = {k: float(np.sqrt(len(y) / max(cls_counts[k], 1)))
                    for k in range(len(CLASSES)) if cls_counts[k] > 0}
    params = dict(
        objective="multiclass", num_class=len(CLASSES), metric=["multi_logloss"],
        learning_rate=args.lr, num_leaves=args.leaves, n_estimators=args.trees,
        feature_fraction=args.colsample, bagging_fraction=0.85, bagging_freq=1,
        min_data_in_leaf=args.min_leaf, verbosity=-1, seed=SEED, num_threads=args.threads,
        class_weight=class_weight, feature_pre_filter=False)
    print(f"[fit] {len(df):,} rows x {X.shape[1]} features; train {len(ytr):,}, holdout {len(yva):,}", flush=True)
    model = lgb.LGBMClassifier(**params)
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)],
              callbacks=[lgb.early_stopping(40, verbose=False), lgb.log_evaluation(0)])
    prob = model.predict_proba(Xva, num_iteration=model.best_iteration_)
    if prob.shape[1] != len(CLASSES):
        prob = np.hstack([prob, np.zeros((prob.shape[0], len(CLASSES) - prob.shape[1]))])

    calibration = {"NONE": {"a": 1.0, "b": 0.0}}
    for k in range(1, len(CLASSES)):
        yb = (yva == k).astype(int)
        if yb.sum() < 5 or len(yb) < 100:
            calibration[CLASSES[k]] = {"a": 1.0, "b": 0.0}
            continue
        from sklearn.linear_model import LogisticRegression
        lr = LogisticRegression(C=1e6, max_iter=200)
        lr.fit(logit(prob[:, k]).reshape(-1, 1), yb)
        calibration[CLASSES[k]] = {"a": float(lr.coef_[0, 0]), "b": float(lr.intercept_[0])}

    gate_p, gate_y = 1 - prob[:, 0], (yva != 0).astype(int)
    report = {"classes": CLASSES, "rows": int(len(df)), "n_pumps": int(df.pump_id.nunique()),
              "gate_auc_heldout": float(roc_auc_score(gate_y, gate_p)) if len(np.unique(gate_y)) > 1 else None,
              "class_counts": {CLASSES[k]: int(cls_counts[k]) for k in range(len(CLASSES))},
              "train_seconds": round(time.time() - t0, 1)}
    if len(yva) > 200:
        rep = classification_report(yva, prob.argmax(axis=1), labels=np.arange(len(CLASSES)),
                                    target_names=CLASSES, output_dict=True, zero_division=0)
        report["per_class_heldout"] = rep
        f1s = [rep[CLASSES[k]]["f1-score"] for k in range(2, len(CLASSES))
               if rep.get(CLASSES[k], {}).get("support", 0) > 10]
        report["macro_f1_typed_heldout"] = float(np.mean(f1s)) if f1s else None
    model.booster_.save_model(str(out / "lgb_model.txt"))
    with open(out / "bundle.pkl", "wb") as fh:
        pickle.dump({"classes": CLASSES, "feature_cols": fcols, "dummy_cols": dummy_cols,
                     "calibration": calibration, "params": params, "seed_base": None}, fh)
    with open(out / "report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=float)
    print(json.dumps({k: report[k] for k in ("gate_auc_heldout", "macro_f1_typed_heldout",
                                             "rows", "train_seconds") if k in report}, indent=2), flush=True)
    print(f"[fit] saved -> {out}", flush=True)


def _asset_from_data(data_dir: Path, asset_id: str):
    assets = pd.read_csv(data_dir / "assets.csv")
    arow = assets[assets.asset_id == asset_id].iloc[0].to_dict()
    feats_all = pd.read_parquet(data_dir / "features_1min.parquet")
    feats = feats_all[feats_all.asset_id == asset_id].sort_values("window_start_utc").set_index("window_start_utc")
    snaps = None
    p = data_dir / "vibration_snapshots.parquet"
    if p.exists():
        sn = pd.read_parquet(p)
        sn = sn[sn.asset_id == asset_id].sort_values("timestamp_utc")
        if len(sn):
            from sentry import snapshots as SN
            snaps = SN.snapshot_metrics(sn, float(arow["bearing_bpfo_order"]),
                                        float(arow["bearing_bpfi_order"]), int(arow["impeller_vanes"]))
    return arow, feats, snaps


def apply(args):
    import lightgbm as lgb
    with open(Path(args.model) / "bundle.pkl", "rb") as fh:
        bundle = pickle.load(fh)
    booster = lgb.Booster(model_file=str(Path(args.model) / "lgb_model.txt"))
    CLS, cal = bundle["classes"], bundle["calibration"]
    fcols, dummy_cols = bundle["feature_cols"], bundle["dummy_cols"]
    data = Path(args.data)
    alerts = []
    for asset_id in args.assets:
        arow, feats, snaps = _asset_from_data(data, asset_id)
        fx, _ = build_ml_features(arow, feats, snaps)
        X = np.hstack([fx[fcols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32),
                       pd.get_dummies(fx[["tier", "control", "profile"]],
                                     columns=["tier", "control", "profile"]) \
                           .reindex(columns=dummy_cols, fill_value=0).to_numpy(dtype=np.float32)])
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        prob = booster.predict(X, num_iteration=booster.best_iteration or None)
        if prob.shape[1] != len(CLS):
            prob = np.hstack([prob, np.zeros((prob.shape[0], len(CLS) - prob.shape[1]))])
        for k in range(1, len(CLS)):
            a_, b_ = cal.get(CLS[k], {"a": 1.0, "b": 0.0}).values()
            prob[:, k] = sigmoid(a_ * logit(prob[:, k]) + b_)
        prob = prob / np.maximum(prob.sum(axis=1, keepdims=True), 1e-9)
        idx = fx.index
        tmin = pd.DatetimeIndex(pd.to_datetime(pd.Series(idx), utc=True))
        p_smooth = np.asarray(pd.Series(1 - prob[:, 0]).rolling(5, min_periods=2).mean())
        runok = fx["running_fraction"].values > 0.9
        cand = (p_smooth > args.threshold) & runok
        sus = np.asarray(pd.Series(cand.astype(float)).rolling(15, min_periods=10).sum()) >= 12
        collapse = np.asarray(pd.Series((p_smooth < args.rearm_below).astype(float))
                              .rolling(15, min_periods=10).mean()) > 0.5
        last_by_type = {}
        for i2 in np.nonzero(sus)[0]:
            tss = pd.Timestamp(tmin[i2], tz="UTC") if tmin[i2].tzinfo is None else pd.Timestamp(tmin[i2])
            cls_p = prob[i2, 2:]
            j = int(np.argmax(cls_p)) + 2
            ftype = CLS[j]
            conf = float(np.clip(cls_p[j - 2], 0.05, 0.97))
            lapse = last_by_type.get(ftype)
            rearm_ok = ftype in ("CAVITATION", "AIR_ENTRAINMENT") and bool(collapse[i2])
            last_emit = last_by_type.get("__any__")
            if last_emit is not None and (tss - last_emit).total_seconds() < args.burst_gap_s and not rearm_ok:
                continue
            if lapse is not None and (tss - lapse).total_seconds() < args.reminder_h * 3600 and not rearm_ok:
                continue
            ev_cls = "MACHINE" if ftype in MACHINE_CLASSES else "SENSOR"
            zcols = [c for c in fx.columns if c.startswith("z_")]
            zvals = fx.loc[:, zcols].iloc[i2].abs().sort_values(ascending=False).head(3)
            evid = "; ".join(f"{c[2:]} {fx[c].iloc[i2]:+.0f}z"
                             if 0.5 <= abs(fx[c].iloc[i2]) < 50 else f"{c[2:]} strong"
                             for c in zvals.index if abs(fx[c].iloc[i2]) > 1.0)
            alerts.append({"asset_id": asset_id, "alert_time_utc": tss.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "event_class": ev_cls, "fault_type": ftype, "confidence": round(conf, 2),
                           "evidence": f"ml gate {p_smooth[i2]:.2f}; {evid[:180]}"[:230],
                           "recommended_action": _A.ACTIONS.get(ftype, _A.ACTIONS["UNKNOWN"])})
            last_by_type[ftype] = tss
            last_by_type["__any__"] = tss
            last_by_type["__lasttype__"] = ftype
    out = pd.DataFrame(alerts, columns=["asset_id", "alert_time_utc", "event_class", "fault_type",
                                        "confidence", "evidence", "recommended_action"])
    out.to_csv(args.out, index=False)
    print(f"[apply] {len(out)} alerts -> {args.out}")
    if len(out):
        print(out[["asset_id", "alert_time_utc", "fault_type"]].to_string(index=False))


def main():
    ap = argparse.ArgumentParser(prog="sentry.lumi_train")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fit")
    pf.add_argument("--shards", required=True)
    pf.add_argument("--out", required=True)
    pf.add_argument("--max-pumps", type=int, default=None)
    pf.add_argument("--folds", type=int, default=5)
    pf.add_argument("--holdout-fold", type=int, default=4)
    pf.add_argument("--trees", type=int, default=600)
    pf.add_argument("--leaves", type=int, default=63)
    pf.add_argument("--lr", type=float, default=0.05)
    pf.add_argument("--min-leaf", type=int, default=40)
    pf.add_argument("--colsample", type=float, default=0.85)
    pf.add_argument("--threads", type=int, default=max(2, (os.cpu_count() or 8) // 2))
    pa = sub.add_parser("apply")
    pa.add_argument("--model", required=True)
    pa.add_argument("--data", required=True)
    pa.add_argument("--assets", nargs="+", required=True)
    pa.add_argument("--out", required=True)
    pa.add_argument("--threshold", type=float, default=0.35)
    pa.add_argument("--rearm-below", type=float, default=0.20)
    pa.add_argument("--reminder-h", type=int, default=12)
    pa.add_argument("--burst-gap-s", type=int, default=600)
    args = ap.parse_args()
    (fit if args.cmd == "fit" else apply)(args)


if __name__ == "__main__":
    main()
