"""ONE pipeline: simulate pumps -> physics detector -> dashboard-ready files.

Run from the challenge folder (RETROFIT_AI_PARTICIPANTS_2026, with .venv active):
    python3 joice_physics_rules/pipeline.py --seed 100 --out dashboard_data/seed_100
    python3 joice_physics_rules/pipeline.py --company validation --out dashboard_data/company_validation

Output folder:
    assets.csv            pump datasheets: site, system, sensor tier, control
    alerts.csv            every alarm: time, class, fault type, confidence, evidence (why), action, + true answer
    events_truth.csv      when each real fault started / ended (answer sheet)
    timeseries/<pump>.csv minute-by-minute sensors + physics health numbers (for plots)
    summary.json          score vs baseline B1, counts
"""
import sys, os, json, argparse, subprocess, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "build_training_table.py")).read().split("root = sys.argv")[0])

SENSORS = ["motor_speed_rpm", "motor_current_a", "motor_power_kw", "suction_pressure_kpa", "discharge_pressure_kpa",
           "flow_m3_h", "fluid_temp_c", "bearing_temp_c", "motor_winding_temp_c", "vibration_rms_mm_s",
           "vibration_accel_rms_g", "vibration_crest_factor", "valve_position_pct"]
PHYSICS = {"ph_fH": "head_factor (1.0 = on pump curve)", "ph_dH": "head_change_vs_normal", "ph_dP": "power_change_vs_normal",
           "ph_sigma": "npsh_margin (<1.15 = cavitation)", "b_idx": "bearing_index (~0.1 healthy, >0.6 damaged)",
           "ph_iP_res": "current_vs_power_error", "ph_bt_dev": "bearing_temp_above_normal_C", "since_start": "minutes_since_start"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int); ap.add_argument("--company", choices=["train", "validation"])
    ap.add_argument("--out", required=True); a = ap.parse_args()
    if a.seed is not None:
        src = f"build/generated/stress_{a.seed}"
        if not os.path.exists(f"{src}/public/assets.csv"):
            print("simulating pumps, seed", a.seed, flush=True)
            subprocess.run([sys.executable, "make_dataset.py", "--tier", "stress", "--seed", str(a.seed), "--output", src], check=True,
                           stdout=subprocess.DEVNULL)
        P, Q = f"{src}/public", f"{src}/private"
        assets = pd.read_csv(f"{P}/assets.csv"); feat = pd.read_parquet(f"{P}/features_1min.parquet")
        ctx = pd.read_csv(f"{P}/operating_context.csv"); ev = pd.read_csv(f"{Q}/events_stress_all.csv")
        bn = pd.read_csv(f"{P}/benign_windows_stress.csv"); vf = vib_features(pd.read_parquet(f"{P}/vibration_snapshots.parquet"), assets)
    else:
        D = "data/full"; assets = pd.read_csv(f"{D}/assets.csv"); assets = assets[assets.split == a.company]
        feat = pd.read_parquet(f"{D}/features_1min.parquet"); feat = feat[feat.asset_id.isin(assets.asset_id)]
        ctx = pd.read_csv(f"{D}/operating_context.csv"); ev = pd.read_csv(f"{D}/events_{a.company}.csv")
        bn = pd.read_csv(f"{D}/benign_windows_train_validation.csv"); vf = pd.read_csv("vibration_features.csv"); vf = vf[vf.asset_id.isin(assets.asset_id)]
    ctx["t"] = pd.to_datetime(ctx.timestamp_utc, utc=True)
    print("running physics detector...", flush=True)
    zf = B.zscores(B.regime_frame(feat, assets)); zf["window_start_utc"] = pd.to_datetime(zf.window_start_utc, utc=True)
    zp = diag2.prep(zf, ctx, diag2.snap_ratios(vf), assets)
    al = diag2.detect(zp, assets)

    os.makedirs(f"{a.out}/timeseries", exist_ok=True)
    keep_a = ["asset_id", "split", "site", "system", "profile", "control", "instrumentation_tier", "pump_rated_flow_m3_h",
              "pump_rated_head_m", "motor_rated_kw", "motor_rated_rpm", "fluid", "window_start_utc", "window_end_utc"]
    assets[[c for c in keep_a if c in assets]].to_csv(f"{a.out}/assets.csv", index=False)
    al = al.copy(); al["true_fault_type"] = [true_label(ev, r.asset_id, pd.Timestamp(r.alert_time_utc))[0] for _, r in al.iterrows()]
    al["correct"] = al.fault_type == al.true_fault_type
    al.to_csv(f"{a.out}/alerts.csv", index=False)
    ev.to_csv(f"{a.out}/events_truth.csv", index=False)
    for aid, g in zp.groupby("asset_id"):
        out = pd.DataFrame({"time_utc": g.window_start_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "operating_mode": g.operating_mode})
        for s in SENSORS:
            c = s + "__mean"
            if c in g and g[c].notna().any(): out[s] = g[c].round(3).values
        for c, nice in PHYSICS.items():
            if c in g and g[c].notna().any(): out[nice.split(" ")[0]] = pd.to_numeric(g[c], errors="coerce").round(4).values
        out.to_csv(f"{a.out}/timeseries/{aid}.csv", index=False)
    r1 = score(B.b1_threshold(zf, 6, 15), ev, assets, bn, assets.split.iloc[0])
    r2 = score(al.drop(columns=["true_fault_type", "correct"]), ev, assets, bn, assets.split.iloc[0])
    pe = pd.DataFrame(r2["per_event"])
    summ = dict(source=(f"simulated seed {a.seed}" if a.seed is not None else f"company {a.company}"), pumps=int(len(assets)),
                faults=int(len(ev)), alerts=int(len(al)), faults_detected=int(pe.detected.sum()), fault_type_correct=int(pe.type_correct.sum()),
                score_physics=round(r2["composite_score"], 1), score_baseline_B1=round(r1["composite_score"], 1),
                false_alerts_per_pump_day=round(r2["false_alerts_per_asset_day"], 3),
                physics_columns={v.split(" ")[0]: v for v in PHYSICS.values()})
    json.dump(summ, open(f"{a.out}/summary.json", "w"), indent=2)
    print(json.dumps(summ, indent=2)); print("saved to", a.out)

if __name__ == "__main__":
    main()
