# ZeroFault physics detector: submission notes

Physics-informed operator-assist layer for cooling-water pumps (RETROFIT AI 2026, Business Turku / Elomatic).
It raises alerts, names the fault from pump physics, shows the evidence and recommends a human-approved action.
It only reads data: no hardware writes, no control.

## 1. How to run

Requirements: Python 3.10-3.13 and the challenge folder `RETROFIT_AI_PARTICIPANTS_2026/` (contains `src/`, `data/`, `make_dataset.py`).
Copy this folder into it as `RETROFIT_AI_PARTICIPANTS_2026/joice_physics_rules/`, then:

```bash
cd RETROFIT_AI_PARTICIPANTS_2026
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp joice_physics_rules/vibration_features.py . && python3 vibration_features.py   # vibration recordings -> features (once)

# score against baseline B1 on train + validation, fault by fault
python3 joice_physics_rules/lab2.py "$PWD" -v

# dashboard files (alerts with evidence + action, minute-by-minute physics numbers)
python3 joice_physics_rules/pipeline.py --company validation --out dashboard_data/company_validation

# same validation pumps with fewer sensors (T1, T0)
python3 joice_physics_rules/generalisation_test.py "$PWD" downgrade

# new random pumps from the simulator (never seen while building)
python3 make_dataset.py --tier stress --seed 300 --output build/generated/stress_300
python3 joice_physics_rules/pipeline.py --seed 300 --out dashboard_data/seed_300
```

Every alert uses only data up to its own time (causal). Rules were built on train and checked on validation; the test pumps were not used to choose anything.

## 2. Results against the provided baselines

Official scorer (`src/retrofit_sim/scoring.py`), composite score out of 100.

| Method | Train (7 pumps) | Validation (2 pumps, 9 faults) | Fault type right (validation) | False alerts / pump-day (validation) |
|---|---|---|---|---|
| B0 SCADA alarms | 27.6 | 23.1 | 11 % | 0.00 |
| B2 CUSUM | 53.3 | 50.9 | 33 % | 1.07 |
| B3 Isolation Forest | 39.4 | 69.2 | 44 % | 0.21 |
| B1 mode-aware z (best baseline) | 58.2 | 78.0 | 44 % | 0.07 |
| **Physics detector** | **84.5** | **95.8** | **89 %** | **0.00** |

Validation detail: 9 of 9 faults detected, 8 of 9 named correctly, no false alerts, timeliness 0.93 (B1 0.86).

Generalisation (pumps and sensor sets the rules were not built on):

| Test | B1 | Physics |
|---|---|---|
| Validation pumps with sensors removed to T1 | 72.3 | 95.2 |
| Validation pumps with sensors removed to T0 | 38.5 | 61.5 |
| 102 unseen simulated pumps (17 batches), average | 57.5 | 65.4, better in 16 of 17 batches |
| 15 held-out simulated batches, latest version | | 73.8 (previous version 71.2) |

## 3. What the physics does

- Pump curve and affinity laws (head ~ speed^2, power ~ speed^3): head factor = measured head / datasheet head. Restriction = head up, power down; head lost in hours = air, in weeks = impeller wear.
- NPSH margin from suction pressure and the boiling pressure of the water (Antoine equation): < 1.15 = cavitation.
- Vibration recordings: bearing index (bearing-frequency envelope / high-frequency energy), 2x line = misalignment, 1x line = imbalance.
- Sensor vs machine: a real fault moves physically linked signals together; one signal moving alone is a sensor fault (drift, shift, stuck, noise, comms loss).
- Warm-up: temperatures ignored for 2 h after a start (thermal time constants 20-40 min), which removes restart false alarms.
Full rules per fault: `dashboard_data/fault_actions.json` (actions) and the machine fault playbook.

## 4. Honest limitations

- All results are on the organiser's synthetic data. A real pilot needs read-only shadow mode first and a check of limits (NPSH 1.15, bearing index 0.6) against the real pump's datasheet.
- Legacy T0 pumps have no vibration, flow or suction sensors. Vibration faults are nearly invisible there; T0 score 61.5 vs 95.8 with full sensors. The fix is a low-cost retrofit sensor, not more software.
- Impeller wear already present on day 1 is not found (no healthy reference, no flow meter on T0).
- Bearing faults on T1 are confirmed only at the next 4-hourly vibration recording (about 1 day late).
- Slow sensor drift and a sudden calibration shift are sometimes confused (PUMP-09 current).
- Confidence values are rule strengths (e.g. cavitation 0.85, impeller wear 0.4), not calibrated probabilities.
- Machine learning was tested on 400 simulated pumps (fault naming and alarm timing). It reached the physics level but did not beat it, so the submitted detector is physics only. Learning should pay off once real operator feedback (confirmed / false alarm) is collected.
