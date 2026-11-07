# retrofit_engine

Joice's physics rules (detector + diagnosis) + the trained hybrid ML diagnostician, as one drop-in folder for a
FastAPI backend. Input: pump datasheet + telemetry (+ optional baseline, context, vibration snapshots).
Output: alerts in the organisers' template format (`asset_id, alert_time_utc, event_class, fault_type, confidence,
evidence, recommended_action`) plus a few extra fields.

## Install
1. Copy this folder into your FastAPI project (next to your `main.py`).
2. `pip install pandas numpy scipy scikit-learn lightgbm joblib pyarrow python-multipart`
3. Put the trained model in `retrofit_engine/model/`:
   `python -m retrofit_engine.tools.export_model --training "<path>/RETROFIT_AI_PARTICIPANTS_2026" --version hybrid-v3-001`
   (without a model it still works, using Joice's rules only)
4. In `main.py`:
   ```python
   from retrofit_engine.router import router as retrofit_router
   app.include_router(retrofit_router)
   ```
5. Open http://localhost:8000/docs and try `POST /retrofit/analyze`.

## Endpoints
| | |
|---|---|
| `GET /retrofit/info` | model version, required datasheet columns, limits |
| `POST /retrofit/analyze` | multipart upload -> JSON `{alerts, pumps, summary, notes}` |
| `POST /retrofit/analyze/csv` | same upload -> template CSV download |

Upload fields: `datasheet` (required), `telemetry` (required), `baseline`, `context`, `snapshots` (optional),
`use_ml` (form field, default true). Files may be CSV, parquet or JSON.

## Or as a function
```python
from retrofit_engine import predict, read_table, to_template_csv
res = predict(read_table("datasheet.csv"), read_table("telemetry.csv"), baseline=read_table("baseline.csv"))
```

## Input files
* **datasheet** - one row per pump. Required: `asset_id, control (FIXED_SPEED|VFD_PRESSURE|VFD_TEMPERATURE|FLOW_VALVE),
  motor_rated_rpm, pump_rated_flow_m3_h, pump_rated_head_m, pump_shutoff_head_m, npsh3_at_bep_m, fluid`.
  Optional: `motor_rated_current_a, motor_rated_kw, profile, bearing_bpfo_order, impeller_vanes, instrumentation_tier,
  channels_available` (derived from the telemetry when missing).
* **telemetry** - the period to monitor. Either raw readings (`asset_id, timestamp_utc, <sensor columns>`, any rate,
  e.g. 1 Hz; `operating_mode` optional) or 1-minute summaries (`asset_id, window_start_utc, <sensor>__mean/std/min/max/count`).
  Sensor column names: motor_speed_rpm, motor_current_a, motor_power_kw, suction_pressure_kpa, discharge_pressure_kpa,
  flow_m3_h, fluid_temp_c, bearing_temp_c, motor_winding_temp_c, vibration_rms_mm_s, vibration_accel_rms_g,
  vibration_crest_factor, ambient_temp_c, valve_position_pct (send the ones the pump has).
* **baseline** (optional) - same format, a healthy period just BEFORE the telemetry, at least 24 h of running.
  It defines each pump's "normal"; alerts are reported for the telemetry period only.
  Without it, the first ~24 h of the telemetry are used as normal and alerts start after that.
* **context** (optional) - `asset_id, timestamp_utc, sea_state_hs_m, suction_static_head_m`.
* **snapshots** (optional, parquet) - vibration waveforms `asset_id, timestamp_utc, sample_rate_hz, rpm_at_capture,
  samples`. Without them bearing / misalignment / imbalance diagnosis is weaker.

## Demo files
`python -m retrofit_engine.tools.make_demo_files --data "<path>/RETROFIT_AI_PARTICIPANTS_2026/data/full" --pumps PUMP-08 PUMP-09 --out demo_files`
writes datasheet.csv, baseline.csv, telemetry.csv, context.csv, snapshots.parquet ready to upload.

## Swapping the model
Re-run `tools.export_model` with the new training output. If the features or Joice's rules changed (e.g. v4),
also replace `physics/diag2.py` and `features.py` and bump `ENGINE_FEATURE_VERSION` in `config.py`; a model built
for other features is refused at load time.

## Files
`engine.py` predict() | `inputs.py` file reading, raw->1-min, baseline, datasheet checks | `features.py` ML features |
`model.py` model loading | `physics/diag2.py` Joice's rules (v3) | `config.py` settings | `router.py` FastAPI endpoints |
`_vendor/` organisers' MIT code (normalisation, 1-minute aggregation) | `tools/` export_model, make_demo_files
