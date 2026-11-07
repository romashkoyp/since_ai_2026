# SENTRY LUMI/parallel synthetic-data generator.
#
# Generates N independent 7-day synthetic pumps IN MEMORY using the challenge's own
# stress-tier sampler (unseen ratings, seasons, tiers, missing sensors, fault mixes),
# and writes ONLY the compact ML training tables (no 1 Hz telemetry):
#   <out>/shard_<k>.parquet    canonical SENTRY ML features + labels per minute
#                              (schema: sentry.ml_features.feature_columns() + gate/label/benign)
#   <out>/meta_<k>.parquet     one row per pump: asset row + events + benign + snapshot metrics (JSON)
#   <out>/manifest.json
#
# Measured runtime reference (1 core): ~11 s per 7-day pump end-to-end.
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))               # `sentry` imports as a package
sys.path.insert(0, str(_ROOT / "src"))       # `retrofit_sim` (same trick make_dataset.py uses)

import numpy as np
import pandas as pd

CFG = None  # fleet config, loaded once per worker via initializer


def _init_worker(fleet_path):
    global CFG
    from retrofit_sim.fleet import load_fleet
    cfg, _fleet = load_fleet(fleet_path)
    CFG = cfg


def _build_one_pump(args):
    """Generate one synthetic 7-day pump fully in memory; return compact tables or an error stub."""
    seed, days, healthy_frac = args
    try:
        from retrofit_sim import generate as G
        from retrofit_sim import dataset as D
        from retrofit_sim.stress import sample_fleet
        from sentry.ml_features import build_ml_features, build_labels

        assets = sample_fleet(CFG, seed=seed, n_assets=1, days=days)
        a = assets[0]
        a["asset_id"] = f"SYN{seed:06d}"       # unique id (rngs() mixes seed+id => deterministic)
        a = D.enrich_asset(a)

        res = G.simulate_asset(a, seed=seed, n_days=days)
        tele = G.telemetry_frame(res)
        feats = D.features_1min(tele)
        events = pd.DataFrame(G.events_for(res))   # *_ms columns at this stage (ISO comes later in write_tables)
        benign = pd.DataFrame(G.benign_for(res))
        snaps = D.snapshots_for(res)
        arow = D.asset_row(res["acfg"], res["specs"], res["acfg"]["limits"], days)

        # ---- SENTRY ML features (canonical schema) + per-minute labels ----
        fidx = feats.set_index("window_start_utc")
        snap_df = pd.DataFrame(snaps) if snaps else None
        ml, _chans = build_ml_features(arow, fidx, snap_df)
        gate, lab, bmask = build_labels(events, benign, ml.index)
        ml.insert(0, "pump_id", a["asset_id"])
        ml["index_col"] = ml.index.astype(str)
        ml["gate"] = gate.astype("float32")
        ml["benign"] = bmask.astype("float32")
        ml["label"] = lab

        # ---- keep every event/benign/non-running minute; subsample plain healthy minutes ----
        keep = pd.Series(True, index=ml.index)
        if healthy_frac < 1.0:
            rng = np.random.default_rng(seed)
            samp = pd.Series(rng.random(len(ml)) < healthy_frac, index=ml.index)
            still = pd.Series(pd.Series(feats["operating_mode"].values != "RUNNING").values, index=ml.index)
            keep = (ml["gate"].values == 1) | (ml["benign"].values == 1) | samp | still
        ml = ml[keep.values].reset_index(drop=True) if healthy_frac < 1.0 else ml.reset_index(drop=True)

        # ---- snapshot spectral metrics (stored as JSON; recomputed identically at apply time) ----
        snap_json = "[]"
        if snaps:
            from sentry import snapshots as SN
            sd = pd.DataFrame(snaps)
            met = SN.snapshot_metrics(sd, float(arow["bearing_bpfo_order"]),
                                      float(arow["bearing_bpfi_order"]), int(arow["impeller_vanes"]))
            met = met.assign(timestamp_utc=met["timestamp_utc"].astype(str))
            keep_snap = [c for c in met.columns if met[c].dtype == "float64"]
            met[keep_snap] = met[keep_snap].astype("float32")
            met = met[(["timestamp_utc"] + [c for c in met.columns if c != "timestamp_utc"])]
            snap_json = met.to_json(orient="records")

        meta = {
            "pump_id": a["asset_id"], "seed": seed, "tier": a["instrumentation_tier"],
            "control": a["control"], "profile": a["profile"], "split": a["split"],
            "days": days,
            "asset_row_json": json.dumps(arow),
            "events_json": events.to_json(orient="records"),
            "benign_json": benign.to_json(orient="records"),
            "snap_metrics_json": snap_json,
            "n_events": int(len(events)), "n_snapshots": int(len(snaps)),
        }
        return {"ok": True, "pump_id": a["asset_id"], "features": ml, "meta": meta}
    except Exception as ex:  # worker isolation: one bad pump must never kill the batch
        import traceback
        return {"ok": False, "pump_id": f"SYN{seed:06d}", "seed": seed,
                "error": f"{ex.__class__.__name__}: {ex}",
                "traceback": traceback.format_exc(limit=6)}


def main():
    ap = argparse.ArgumentParser(description="SENTRY LUMI synthetic-data generator (in-memory, compact output)")
    ap.add_argument("--n-pumps", type=int, default=6000)
    ap.add_argument("--seed-base", type=int, default=100000)
    ap.add_argument("--workers", type=int, default=max(1, min(os.cpu_count() or 8, 120)))
    ap.add_argument("--days", type=float, default=7.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shard-size", type=int, default=50, help="pumps per output parquet pair")
    ap.add_argument("--healthy-frac", type=float, default=0.3,
                    help="fraction of non-event/non-benign RUNNING minutes to keep (event windows always kept)")
    ap.add_argument("--fleet-config", default=str(_ROOT / "configs" / "fleet_public.yaml"))
    args = ap.parse_args()

    out = Path(args.out)
    (out / "logs").mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    jobs = [(args.seed_base + i, args.days, args.healthy_frac) for i in range(args.n_pumps)]
    print(f"[gen] {args.n_pumps} pumps x {args.days}d on {args.workers} workers -> {out}", flush=True)

    feats_buf, metas_buf, shard_k, done, ok_ct, err_ct = [], [], 0, 0, 0, 0
    n_shards = (args.n_pumps + args.shard_size - 1) // args.shard_size
    with Pool(args.workers, initializer=_init_worker, initargs=(args.fleet_config,)) as pool:
        for r in pool.imap_unordered(_build_one_pump, jobs, chunksize=1):
            done += 1
            if r["ok"]:
                feats_buf.append(r["features"])
                metas_buf.append(r["meta"])
                ok_ct += 1
            else:
                err_ct += 1
                print(f"[gen] FAIL {r['pump_id']}: {r['error']}", flush=True)
                with open(out / "logs" / "failures.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(r) + "\n")
            if len(feats_buf) >= args.shard_size or done == args.n_pumps:
                if feats_buf:
                    pd.concat(feats_buf, ignore_index=True).to_parquet(
                        out / f"shard_{shard_k:04d}.parquet", index=False, compression="zstd", compression_level=3)
                    pd.DataFrame(metas_buf).to_parquet(
                        out / f"meta_{shard_k:04d}.parquet", index=False, compression="zstd", compression_level=3)
                    print(f"[gen] shard {shard_k + 1}/{n_shards} written ({len(feats_buf)} pumps, "
                          f"{ok_ct}/{done} ok, {time.time() - t0:.0f}s elapsed)", flush=True)
                    feats_buf, metas_buf = [], []
                    shard_k += 1

    manifest = {
        "n_pumps": args.n_pumps, "ok": ok_ct, "failed": err_ct, "days": args.days,
        "seed_base": args.seed_base, "healthy_frac": args.healthy_frac,
        "fleet_config": args.fleet_config, "shards": shard_k,
        "wall_seconds": round(time.time() - t0, 1),
        "generator": "sentry/lumi_generate.py (in-memory; no 1 Hz telemetry stored)",
    }
    with open(out / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"[gen] done in {time.time() - t0:.1f}s: {ok_ct} ok, {err_ct} failed -> {out}", flush=True)


if __name__ == "__main__":
    main()
