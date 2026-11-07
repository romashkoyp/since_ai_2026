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

## Results (v4: + fixed physics references for drift, in-minute noise check, stuck wireless sensor)
| test | B1 composite | physics | B1 fault-type recall | physics |
|---|---|---|---|---|
| train (7 pumps) | 58.2 | 85.9 | 0.27 | 0.81 |
| validation (2 pumps) | 78.0 | 95.8 | 0.44 | 0.89 |
| validation downgraded to T1 | 72.3 | 95.2 | 0.25 | 0.88 |
| validation downgraded to T0 | 38.5 | 59.6 | 0.00 | 0.50 |
| 5 stress batches, 30 unseen pumps (avg) | 59.8 | 66.0 | 0.36 | 0.53 |
Correct fault types, train + validation: B1 11/35, physics 29/35. Unseen pumps: B1 27/76, physics 40/76.
Validation: every fault detected (event F1 1.0), zero false alerts.
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

## Known weak spots (next work)
* FLOW_VALVE pumps: the controller opens the valve and hides clogging. Use valve position: valve opening + suction falling = clogging.
* Overlapping faults on one pump (seed 23 STRESS-05, PUMP-04): one alert can only carry one type.
* Pre-existing impeller wear on T0 pumps (no flow meter): no clean reference, so it is hard to see.
* Stress data: python3 make_dataset.py --tier stress --seed N --output <dir>   (about 15 s)
