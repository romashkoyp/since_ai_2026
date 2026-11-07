"""Settings for the RETROFIT AI engine. Change these, not the code, when tuning."""

# Must match "feature_version" in models/current/metadata.json. Bump it whenever the feature code
# (features.py) or the physics rules (physics/diag2.py) change, so an old model is refused.
ENGINE_FEATURE_VERSION = "joice-v3/table-v1"
PHYSICS_VERSION = "joice-v3"

# Hybrid decision
MIN_CONF = 0.5                     # ML overrides the rule only when its calibrated confidence >= this
RULE_PRIORITY = {                  # always keep the rule's answer for these (rule beat the model in cross-validation)
    "CAVITATION", "AIR_ENTRAINMENT", "IMPELLER_WEAR", "COMMUNICATION_LOSS", "SENSOR_STUCK", "SENSOR_CALIBRATION_SHIFT"}

# Detector settings (same as the organisers' B1 choice)
Z_THRESHOLD = 6.0
MIN_HISTORY_HOURS = 24             # each pump needs this much data before alerts can fire (baseline learning)

TEMPLATE_COLUMNS = ["asset_id", "alert_time_utc", "event_class", "fault_type", "confidence", "evidence",
                    "recommended_action"]

SENSOR_TYPES = {"SENSOR_DRIFT", "SENSOR_STUCK", "SENSOR_CALIBRATION_SHIFT", "SENSOR_NOISE_SPIKES", "COMMUNICATION_LOSS"}

ACTIONS = {
    "BEARING_WEAR": "Plan bearing replacement; check lubrication.",
    "SUCTION_STRAINER_CLOGGING": "Inspect / clean suction strainer.",
    "CAVITATION": "Raise suction level / clean strainer / reduce flow.",
    "DISCHARGE_RESTRICTION": "Check discharge valves and heat-exchanger fouling.",
    "MISALIGNMENT": "Check coupling alignment (likely after maintenance).",
    "IMBALANCE": "Inspect impeller for fouling; balance.",
    "IMPELLER_WEAR": "Performance test; inspect impeller / wear rings.",
    "AIR_ENTRAINMENT": "Check sea-chest venting / basin level; air in suction.",
    "SENSOR_DRIFT": "Verify the instrument against a reference gauge; recalibrate.",
    "SENSOR_STUCK": "Check transmitter / wireless sensor.",
    "SENSOR_CALIBRATION_SHIFT": "Verify the instrument against a reference gauge; recalibrate.",
    "SENSOR_NOISE_SPIKES": "Check cabling / grounding of the instrument.",
    "COMMUNICATION_LOSS": "Check gateway / network; data gap.",
    "UNKNOWN": "Inspect pump; cause unclear.",
}

# Datasheet columns
REQUIRED_ASSET_COLUMNS = ["asset_id", "control", "motor_rated_rpm", "pump_rated_flow_m3_h", "pump_rated_head_m",
                          "pump_shutoff_head_m", "npsh3_at_bep_m", "fluid"]
ASSET_DEFAULTS = {"profile": "UNKNOWN", "bearing_bpfo_order": 3.6, "impeller_vanes": 6,
                  "motor_rated_current_a": None, "motor_rated_kw": None, "split": "uploaded"}
CONTROLS = {"FIXED_SPEED", "VFD_PRESSURE", "VFD_TEMPERATURE", "FLOW_VALVE"}

# Health indicators exported for charts: internal column -> dashboard name (same names as Joice's dashboard_data)
HEALTH_COLUMNS = {
    "ph_fH": "head_factor",
    "ph_dH": "head_change_vs_normal",
    "ph_dP": "power_change_vs_normal",
    "ph_sigma": "npsh_margin",
    "b_idx": "bearing_index",
    "ph_iP_res": "current_vs_power_error",
    "since_start": "minutes_since_start",
}
SENSOR_MEAN_COLUMNS = ["motor_speed_rpm", "motor_current_a", "motor_power_kw", "suction_pressure_kpa",
                       "discharge_pressure_kpa", "flow_m3_h", "fluid_temp_c", "bearing_temp_c", "motor_winding_temp_c",
                       "vibration_rms_mm_s", "vibration_accel_rms_g", "vibration_crest_factor", "valve_position_pct"]
