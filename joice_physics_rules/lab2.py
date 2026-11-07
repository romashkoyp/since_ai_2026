import sys, os, warnings, pandas as pd
warnings.filterwarnings("ignore")
R = sys.argv[1]; sys.path.insert(0, os.path.join(R, "src")); HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from retrofit_sim import baselines as B
from retrofit_sim.scoring import score
import diag2
D = os.path.join(R, "data/full")
assets = pd.read_csv(f"{D}/assets.csv"); bn = pd.read_csv(f"{D}/benign_windows_train_validation.csv")
zpath = os.path.join(HERE, "zf.parquet")
if not os.path.exists(zpath):
    print("building z-scores once (~1 min)...")
    B.zscores(B.regime_frame(pd.read_parquet(f"{D}/features_1min.parquet"), assets)).to_parquet(zpath)
zf = pd.read_parquet(zpath)
zf["window_start_utc"] = pd.to_datetime(zf.window_start_utc, utc=True)
ctx = pd.read_csv(f"{D}/operating_context.csv"); ctx["t"] = pd.to_datetime(ctx.timestamp_utc, utc=True)
snapf = diag2.snap_ratios(pd.read_csv(os.path.join(R, "vibration_features.csv")))
zp = diag2.prep(zf, ctx, snapf, assets)
zp.to_parquet(os.path.join(HERE, "zp.parquet"))
tot = {}
for split in ("train", "validation"):
    ids = set(assets[assets.split == split].asset_id)
    ev = pd.read_csv(f"{D}/events_{split}.csv")
    for name, pr in (("B1", B.b1_threshold(zf[zf.asset_id.isin(ids)], 6, 15)), ("NEW", diag2.detect(zp[zp.asset_id.isin(ids)], assets))):
        r = score(pr, ev, assets, bn, split)
        print(f"{split:10s} {name:4s}", {k: round(r[k], 3) for k in ("composite_score", "event_f1", "fault_type_recall", "class_recall", "timeliness", "false_alerts_per_asset_day")})
        pe = pd.DataFrame(r["per_event"]); tot.setdefault(name, [0, 0]); tot[name][0] += pe.type_correct.sum(); tot[name][1] += len(pe)
        if name == "NEW" and "-v" in sys.argv:
            print(pe[["event_id", "fault_type", "detected", "predicted_fault_type", "type_correct"]].to_string(index=False))
print("correct types (train+val):", {k: f"{v[0]}/{v[1]}" for k, v in tot.items()})
