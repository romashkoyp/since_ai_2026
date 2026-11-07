# Physics-informed fault diagnostician (Joice)

Same alarm as B1, but a physics-based "specialist" names the cause. Every number comes from the
pump datasheet (assets.csv) or textbook physics. Nothing is tuned per pump, so it should carry over to unseen pumps.

## Setup
Copy this folder into the challenge folder `RETROFIT_AI_PARTICIPANTS_2026/` (next to `src/` and `data/`), name it `joice_physics_rules`,
and copy `vibration_features.py` one level up into the challenge folder. Then run the commands below from the challenge folder.
The z-score cache (zf.parquet) is rebuilt automatically on the first run (~1 min).

## Run
    python3 vibration_features.py                                        # once, makes vibration_features.csv
    python3 joice_physics_rules/lab2.py "$PWD" -v                         # train + validation vs B1
    python3 joice_physics_rules/generalisation_test.py "$PWD" downgrade   # same pumps with fewer sensors
    python3 joice_physics_rules/generalisation_test.py "$PWD" stress <stress_dir>   # unseen random pumps

## Results (v5: + refractory-safe tie-breakers, T0 fixed-speed impeller wear, bearing-drift gating)
| test | B1 composite | physics | B1 fault-type recall | physics |
|---|---|---|---|---|
| train (7 pumps) | 58.2 | **93.7** | 0.27 | **0.923 (24/26)** |
| validation (2 pumps) | 78.0 | **95.8** | 0.44 | **0.889 (8/9)** |
| validation downgraded to T1 | 72.3 | 95.2 | 0.25 | 0.88 |
| validation downgraded to T0 | 38.5 | 59.6 | 0.00 | 0.50 |
| 17 stress batches, 102 unseen pumps (avg) | 59.8 | **71.5** | 0.36 | **0.589 (152/258)** |
Correct fault types, train + validation: B1 11/35, physics **32/35 (91.4%)**. Unseen pumps (17 batches): **152/258 (58.9%)**.
Train + validation event recall: **35/35 (100% of observable faults detected)**. Validation: event F1 1.0, zero false alerts.
Economic impact (`examples/business_case.py` at 100% recall, 0.032 false alerts/pump-day): **EUR 7,198/yr net savings per duty pump** (**0.6 yr / ~7 month payback** on a EUR 4,500 retrofit kit, vs EUR 4,458/yr and 1.0 yr payback for B1).
Weak spot: on unseen pumps physics raises slightly more false alerts (0.26 vs 0.19 per pump-day), mostly on batch-cycling process pumps.

## The physics, rule by rule
1. **Warm-up.** Motor and bearing temperatures need ~2 h after a start (thermal time constant 20-40 min).
   Cold readings in that window are ignored, by the alarm too, so restarts no longer raise false alerts.
2. **Sensor vs machine.** A real fault moves physically coupled signals together. One signal moving alone means the instrument
   failed: a jump is a calibration shift, a slow slide is drift, spikes are noise, flat while running means stuck, missing rows are a comms loss.
3. **Bearing.** Bearing index = BPFO envelope amplitude / high-frequency RMS (healthy ~0.1, damaged 2-4).
   Cavitation raises both parts, so the ratio stays low. Crest factor rising alone = early impacts = early bearing damage.
4. **Misalignment vs imbalance.** 2x vibration, warm bearing/winding, or just after maintenance = misalignment. 1x only = imbalance.
5. **Pump curve (affinity laws).** Head ~ speed^2, power ~ speed^3. H/(H_rated r^2) and P/r^3 remove speed changes.
   * head factor = measured head / datasheet curve head at the measured flow (1.0 = healthy)
   * head up + power down = **restriction** (pump pushed left on its curve)
   * head factor drops fast (hours) = **air entrainment** / cavitation; slow (weeks) = **impeller wear**
   * suction pressure down = **strainer clogging**; plus broadband vibration = **cavitation**
6. **Cavitation (NPSH).** NPSH margin = (suction abs. pressure - vapour pressure of the water [Antoine eq.] + velocity head) / NPSH3 from the datasheet.
   Healthy pumps > 3.5; cavitation < 1.15 for 10 min -> alarm, one per bubble episode. A big acceleration with a healthy bearing index and a low margin means bubbles, not a bearing.
7. **Valve-controlled pumps.** The valve opening to hold flow while suction falls = clogging; valve opening with normal suction = restriction downstream.
8. **Early physics alarms.** Bearing index crossing, cavitation and fast head loss raise an alarm even before any single sensor looks extreme. The same fault is never repeated within 12 h.
9. **Old vibration vs new pressure change.** If 2x/1x vibration was already there and the pressures are what moves now, the hydraulics get diagnosed.
10. **Drift needs a fixed reference.** B1 compares with the last 24 h, so a slow drift drags 'normal' along.
    Motor current is checked against the physics line current = magnetising current + k x power (fitted on the first 6 h,
    must be physical: no-load current 20-60 % of rated). Bearing temperature is checked against its normal offset above the water temperature.
    Jump within 2 h = calibration shift, gradual = drift. Reported once, not repeated.
11. **Look inside the minute.** Noise spikes vanish in the 1-min average but blow up the max-min range (x3-6). One channel's range > 2.5x its normal
    in 5 of 15 minutes, others normal = noise spikes.
12. **Stuck wireless sensor.** A healthy wireless bearing-temperature sensor never repeats the same value for more than ~1 h; > 2 h while running = stuck.
13. **Weather.** Wave height >= 2.5 m with head loss = air drawn into the sea chest.

## Files
* diag2.py - the rules (diagnose2) + B1-style alarm with warm-up suppression (detect)
* lab2.py - scoring vs B1;  generalisation_test.py - downgrade + stress tests
* schema.sql - database for alerts, operator feedback and retraining
* diag2_v1_backup.py, diag2_v2_backup.py - earlier versions
* ph_iP_res column (current vs power line residual) = feature for the ML model; too weak to be a rule on its own

## Known weak spots & honest limitations
* **Overlapping faults on one pump** (e.g., `PUMP-04` bearing wear + discharge restriction, `STRESS-05` seed 23): each alert row carries a single `fault_type`, and the benchmark scorer matches the first in-window alert.
* **T0 pumps (`T0_LEGACY`, no flow meter) under variable-speed or valve control**: pre-existing impeller wear is caught on fixed-speed T0 pumps (`PUMP-05`, `H / H_rated < 0.94`), but without a flow meter on `VFD_PRESSURE` / `FLOW_VALVE` pumps the operating point along the $H(Q)$ curve is under-constrained.
* **Batch-cycling process pumps**: frequent start/stop cycles shorten steady-state windows and slightly raise false-alert rates on unseen stress batches (`0.098/day` avg).
* **Advisory & read-only scope**: the detector + Laya severity categorizer (`SEVERE` / `MODERATE` / `MINIMAL` / `LOW_CONFIDENCE`) never write to PLC/VFD setpoints and earn no class society CBM credit without a formal PMS approval.
* Stress data: `python3 make_dataset.py --tier stress --seed N --output <dir>` (about 15 s)
