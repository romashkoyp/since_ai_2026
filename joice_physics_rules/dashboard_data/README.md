# Dashboard data (physics detector output)

Made by `joice_physics_rules/pipeline.py`. Two ready examples:

| folder | source | pumps | faults | physics score | baseline B1 |
|---|---|---|---|---|---|
| `company_validation/` | company data PUMP-08, PUMP-09 | 2 | 9 | 95.8 | 78.0 |
| `company_train/` | company data PUMP-01..07 (all 13 fault types) | 7 | 27 | 86.7 | 58.2 |
| `simulated_seed_100/` | simulator, seed 100 (unseen pumps) | 6 | 19 | 58.5 | 55.2 |

## Files in each folder
| file | one row per | use in dashboard |
|---|---|---|
| `assets.csv` | pump | pump list: site, system, sensor tier (T0/T1/T2), control type |
| `alerts.csv` | alarm | alarm feed: time, class (MACHINE/SENSOR), fault_type, confidence, **evidence** (why), **recommended_action**, true_fault_type, correct |
| `events_truth.csv` | real fault | answer sheet: onset_utc, end_utc, fault_type, severity (shade these periods on plots) |
| `timeseries/<pump>.csv` | minute | sensor plots + physics health numbers |
| `summary.json` | folder | headline numbers |

## Physics health columns in timeseries/*.csv (only present if the pump has the sensors)
| column | healthy | fault meaning |
|---|---|---|
| `head_factor` | ~1.0 | below normal = pump losing head (wear, air, cavitation) |
| `head_change_vs_normal`, `power_change_vs_normal` | ~0 | head up + power down = discharge restriction |
| `npsh_margin` | > 3 | < 1.15 = cavitation (water boiling at the inlet) |
| `bearing_index` | ~0.1 | > 0.6 = bearing damage |
| `current_vs_power_error` | < 0.025 | larger = current sensor drift / shift |
| `bearing_temp_above_normal_C` | ~0 | > 6 with normal vibration = temperature sensor drift |
| `minutes_since_start` | | < 120 = motor still warming up (temperatures not trusted) |

## Make more data
Run from the challenge folder `RETROFIT_AI_PARTICIPANTS_2026/` (needs `src/`, `data/`, `make_dataset.py`, and this folder copied in as `joice_physics_rules/`):
```
python3 joice_physics_rules/pipeline.py --seed 200 --out dashboard_data/seed_200
python3 joice_physics_rules/pipeline.py --company train --out dashboard_data/company_train
```
