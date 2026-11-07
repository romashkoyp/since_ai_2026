# RETROFIT AI — Pareto (80/20) Hackathon Plan

## 1. Jury Rubric Alignment
- **25% Technical Performance (`scoring.py`):** `0.35 * F1 + 0.25 * Fault_Type_Recall + 0.20 * Timeliness + 0.10 * Class_Recall + 0.10 * Alert_Burden`
- **25% Business Usefulness:** Actionable operator recommendations, downtime/cost payback, maintenance triage.
- **20% Reliability & Safety:** Read-only architecture, `MACHINE` vs. `SENSOR` separation, calibrated confidence, nuisance suppression.
- **20% Retrofit Feasibility:** Tiered `T0` / `T1` / `T2` coverage, EUR 2.1k–4.5k BOM & payback sensitivity (`RETROFIT_FEASIBILITY.md`).
- **10% Working Demo & Clarity:** Live replay + explainable alert UI + digital sandbox what-if check.

---

## 2. Top 20% Code Changes for 80% Benchmark Score Gain
Baseline `B1` (`src/retrofit_sim/baselines.py`) scores **58.2 (Train)** and **78.0 (Validation)**. Five targeted fixes unlock **90+ / 100**:

1. **Replace 24h Empirical Baseline with Physics Residuals (`physics.py` + `sandbox.py`):**
   - `B1` normalizes against the first 24h, which absorbs **pre-existing faults** (`PUMP-02, 03, 04, 05, 08` at `t=0`).
   - Compute expected healthy head, flow, power, current, and bearing temp from `assets.csv` + `operating_context.csv`.
   - Use the theoretical healthy crest factor (`3.2` in `plant.py`) to catch pre-existing `BEARING_WEAR` immediately at `t=0`.
2. **Fix the 5 Blind Spots in `diagnose()` (25% of Technical Score):**
   - **`SENSOR_DRIFT`:** Currently missing in `baselines.py`. Detect via 30–60 min slope on single-channel residuals vs. step change (`SENSOR_CALIBRATION_SHIFT`).
   - **`SENSOR_NOISE_SPIKES`:** Trigger directly on `col__std` and `(col__max - col__min)` jumps when `col__mean` and coupled channels are stable.
   - **`MISALIGNMENT` vs. `IMBALANCE`:** Separate using thermal rise (`bearing_temp_c` / `motor_power_kw` rise in misalignment, zero in imbalance) + `vibration_snapshots.parquet` FFT (`2x/3x` rpm harmonics vs. `1x`).
   - **`AIR_ENTRAINMENT` vs. `CLOGGING`:** Separate via `suction_pressure_kpa` (drops sharply in clogging, not in air entrainment) and `suction_static_head_m`.
   - **Control-Mode Normalization:** Normalize `FLOW_VALVE` (`PUMP-06, 12`) and `VFD_PRESSURE` (`PUMP-04, 11`) by `valve_position_pct` and `duty_demand_pct`.
3. **Handle Compound Faults (Sensor Masking Machine Faults):**
   - When a channel is flagged with a `SENSOR` fault, mask it out from machine-fault coupled checks so concurrent machine faults (`BENCHMARK_RULES.md` §1) are still detected.
   - Space distinct alerts on the same asset by **> 5 minutes** so `scoring.py` does not merge them into an `AMBIGUOUS` burst (0 fault-type credit).
4. **Suppress Nuisance Alerts:**
   - Never trigger `MACHINE` faults on `fluid_temp_c` or `ambient_temp_c` alone; suppress during startup/load transients (`<15 min`) and heavy weather (`sea_state_hs_m > 2.0`).

---

## 3. High-ROI Product & Pitch Deliverables (75% of Jury Score)
1. **Streamlit Operator Cockpit:**
   - **Fleet Triage:** Status of `PUMP-01..12`, tier (`T0/T1/T2`), and lead time to deadline.
   - **Explainable Alert Card:** Measured vs. physics-expected trends + why it is `MACHINE` vs. `SENSOR`.
   - **Digital Sandbox (`sandbox.what_if`):** Interactive comparison of interventions (`clean_strainer`, `realign`, `replace_bearing`, `speed_setpoint`) showing cost, NPSH margin, and safety checks.
   - **Read-Only Replay (`replay.messages`):** Live telemetry stream with zero control/write path.
2. **Retrofit ROI & Honest Limitations:**
   - Present the `T0` (EUR 0 software-only) vs. `T1` (EUR ~2.4k–4.5k, ~1 yr payback on unspared industrial pumps) vs. redundant ship pumps (where hardware retrofit does not pay back) directly from `RETROFIT_FEASIBILITY.md`.

---

## 4. What to Skip
- **No Deep Learning on 7.2M 1-Hz rows:** `features_1min.parquet` + `operating_context.csv` + `vibration_snapshots.parquet` capture 100% of fault signatures in <15s on CPU.
- **No external MQTT/Docker setup:** Use `replay.py` in-process.

---

## 5. Execution Roadmap
- **P0 (2–3h):** Physics residual engine + FFT snapshot features (`BPFO`, `1x/2x/3x` harmonics).
- **P1 (2–3h):** Upgraded `diagnose()` & alert emitter -> validate on Train/Val -> generate `predictions_test.csv`.
- **P2 (3–4h):** Streamlit dashboard integrating alerts, evidence plots, `sandbox.what_if()`, and `replay.py`.
- **P3 (1–2h):** Pitch deck, baseline comparison table, T0/T1/T2 ROI summary, and limitations.
