import type {
  AlertPrediction,
  AssetStatus,
  CockpitResponse,
  FleetSummary,
  ScorecardResponse,
} from "../types/alerts";

export const DUMMY_SUMMARY: FleetSummary = {
  vessel: "M/V Borealis Voyager · Fleet overview",
  watch: "Operator triage · read-only demo",
  critical: 0,
  actionable: 4,
  sensor_faults: 1,
  availability_pct: 58.3,
  healthy: 7,
  total: 12,
  nuisance_suppressed_pct: 62,
};

export const DUMMY_ASSETS: AssetStatus[] = [
  { asset_id: "PUMP-01", site: "M/V Borealis", system: "SW cooling", tier: "T1", status: "healthy", mode: "RUNNING", load_pct: 74, open_alerts: 0 },
  { asset_id: "PUMP-02", site: "M/V Borealis", system: "SW cooling", tier: "T1", status: "sensor_issue", mode: "RUNNING", load_pct: 71, open_alerts: 1, fault_summary: "Sensor drift on vib channel" },
  { asset_id: "PUMP-03", site: "M/V Borealis", system: "LT freshwater", tier: "T0", status: "healthy", mode: "STANDBY", load_pct: 0, open_alerts: 0 },
  { asset_id: "PUMP-04", site: "M/V Borealis", system: "LT freshwater", tier: "T2", status: "alert", mode: "RUNNING", load_pct: 82, open_alerts: 1, fault_summary: "Bearing BPFO rising", rul_hours: 68 },
  { asset_id: "PUMP-05", site: "Plant B", system: "CW loop", tier: "T1", status: "healthy", mode: "RUNNING", load_pct: 66, open_alerts: 0 },
  { asset_id: "PUMP-06", site: "Plant B", system: "CW loop", tier: "T1", status: "alert", mode: "RUNNING", load_pct: 79, open_alerts: 1, fault_summary: "Suction strainer clogging", rul_hours: 24 },
  { asset_id: "PUMP-07", site: "Plant B", system: "Transfer", tier: "T0", status: "healthy", mode: "STOPPED", load_pct: 0, open_alerts: 0 },
  { asset_id: "PUMP-08", site: "Vessel C", system: "LT main", tier: "T2", status: "alert", mode: "RUNNING", load_pct: 88, open_alerts: 1, fault_summary: "Strainer / cavitation risk", rul_hours: 24 },
  { asset_id: "PUMP-09", site: "Vessel C", system: "LT main", tier: "T1", status: "healthy", mode: "STANDBY", load_pct: 0, open_alerts: 0 },
  { asset_id: "PUMP-10", site: "Vessel C", system: "SW cooling", tier: "T1", status: "healthy", mode: "RUNNING", load_pct: 58, open_alerts: 0 },
  { asset_id: "PUMP-11", site: "Vessel C", system: "SW cooling", tier: "T2", status: "alert", mode: "RUNNING", load_pct: 84, open_alerts: 1, fault_summary: "Cavitation signature", rul_hours: 36 },
  { asset_id: "PUMP-12", site: "Vessel C", system: "Transfer", tier: "T0", status: "healthy", mode: "STANDBY", load_pct: 0, open_alerts: 0 },
];

export const DUMMY_ALERTS: AlertPrediction[] = [
  {
    asset_id: "PUMP-04",
    alert_time_utc: "2026-03-12T08:14:00Z",
    event_class: "MACHINE",
    fault_type: "BEARING_WEAR",
    confidence: 0.91,
    evidence: "bearing_temp residual + crest factor rise; BPFO elevated",
    recommended_action: "Inspect DE bearing; plan replacement within 48h",
  },
  {
    asset_id: "PUMP-06",
    alert_time_utc: "2026-03-12T09:02:30Z",
    event_class: "MACHINE",
    fault_type: "SUCTION_STRAINER_CLOGGING",
    confidence: 0.87,
    evidence: "suction pressure drop with stable discharge",
    recommended_action: "Clean suction strainer; verify NPSH margin",
  },
  {
    asset_id: "PUMP-02",
    alert_time_utc: "2026-03-12T07:41:00Z",
    event_class: "SENSOR",
    fault_type: "SENSOR_DRIFT",
    confidence: 0.78,
    evidence: "vibration channel slope vs coupled channels stable",
    recommended_action: "Calibrate sensor; mask channel for machine checks",
  },
  {
    asset_id: "PUMP-08",
    alert_time_utc: "2026-03-12T10:05:00Z",
    event_class: "MACHINE",
    fault_type: "CAVITATION",
    confidence: 0.89,
    evidence: "suction -3.8σ; 2.6–3.0 kHz cavitation band",
    recommended_action: "Derate to 88% speed; clean strainer at port",
  },
  {
    asset_id: "PUMP-11",
    alert_time_utc: "2026-03-12T10:18:00Z",
    event_class: "MACHINE",
    fault_type: "CAVITATION",
    confidence: 0.84,
    evidence: "accel RMS spike with suction head drop",
    recommended_action: "Reduce speed setpoint; check suction level",
  },
];

const COCKPIT_08: CockpitResponse = {
  asset_id: "PUMP-08",
  title: "LT Main Cooling Pump",
  diagnosis: "Suction strainer clogging / early cavitation",
  event_class: "MACHINE",
  confidence: 0.89,
  safe_window: "~24h at 88% speed · port ETA 18h",
  evidence: [
    { channel: "Suction pressure", sigma: -3.8, note: "Below healthy envelope" },
    { channel: "Acoustic resonance", sigma: 4.3, note: "2.6–3.0 kHz band" },
    { channel: "Head vs affinity", sigma: -2.9, note: "Curve left of BEP" },
  ],
  sop: [
    "Derate VFD to 88% immediately",
    "Confirm standby pump ready",
    "Schedule strainer clean at next port",
    "Do not write setpoints from this UI (read-only)",
  ],
  trends: [
    {
      name: "Discharge head",
      unit: "m",
      threshold: 40,
      points: [42, 41, 40, 39, 38, 37, 36.5, 36].map((value, i) => ({ t: `t-${i}`, value })),
    },
    {
      name: "Suction pressure",
      unit: "kPa",
      threshold: 40,
      points: [48, 46, 44, 41, 38, 35, 33, 31].map((value, i) => ({ t: `t-${i}`, value })),
    },
    {
      name: "Motor power",
      unit: "kW",
      threshold: 60,
      points: [52, 53, 54, 55, 56, 57, 58, 59].map((value, i) => ({ t: `t-${i}`, value })),
    },
  ],
  sandbox_default_speed_pct: 88,
  npsh_at_100: 0.38,
  npsh_at_88: 1.84,
  risk_at_100: 0.78,
  risk_at_88: 0.14,
  energy_delta_eur_day: -34.2,
  cooling_margin_pct: 106,
};

const COCKPIT_04: CockpitResponse = {
  asset_id: "PUMP-04",
  title: "LT Freshwater Pump",
  diagnosis: "Drive-end bearing wear (BPFO)",
  event_class: "MACHINE",
  confidence: 0.91,
  safe_window: "~68h remaining · schedule change-out",
  evidence: [
    { channel: "Bearing temp", sigma: 3.1, note: "Rising residual" },
    { channel: "Crest factor", sigma: 2.8, note: "Impactivity up" },
    { channel: "BPFO band", sigma: 4.1, note: "142.8 Hz elevated" },
  ],
  sop: [
    "Keep load under 85%",
    "Confirm lubrication state",
    "Order DE bearing kit",
    "Plan swap within 48h",
  ],
  trends: [
    {
      name: "Bearing temp",
      unit: "°C",
      threshold: 70,
      points: [58, 59, 61, 63, 65, 67, 69, 71].map((value, i) => ({ t: `t-${i}`, value })),
    },
    {
      name: "Vibration RMS",
      unit: "mm/s",
      threshold: 3.2,
      points: [2.1, 2.2, 2.4, 2.6, 2.9, 3.1, 3.4, 3.6].map((value, i) => ({ t: `t-${i}`, value })),
    },
    {
      name: "Motor current",
      unit: "A",
      threshold: 95,
      points: [88, 89, 89, 90, 91, 91, 92, 93].map((value, i) => ({ t: `t-${i}`, value })),
    },
  ],
  sandbox_default_speed_pct: 90,
  npsh_at_100: 1.9,
  npsh_at_88: 2.2,
  risk_at_100: 0.62,
  risk_at_88: 0.28,
  energy_delta_eur_day: -12,
  cooling_margin_pct: 118,
};

export const DUMMY_COCKPITS: Record<string, CockpitResponse> = {
  "PUMP-08": COCKPIT_08,
  "PUMP-04": COCKPIT_04,
};

export function getDummyCockpit(assetId: string): CockpitResponse {
  if (DUMMY_COCKPITS[assetId]) return DUMMY_COCKPITS[assetId];

  const asset = DUMMY_ASSETS.find((a) => a.asset_id === assetId);
  const alert = DUMMY_ALERTS.find((a) => a.asset_id === assetId);

  if (alert) {
    return {
      asset_id: assetId,
      title: `${asset?.system ?? "Cooling"} pump`,
      diagnosis: alert.fault_type.replaceAll("_", " "),
      event_class: alert.event_class,
      confidence: alert.confidence,
      safe_window: asset?.rul_hours ? `~${asset.rul_hours}h remaining` : "Monitor closely",
      evidence: [],
      sop: [alert.recommended_action ?? "Review evidence", "Keep UI read-only — no PLC writes"],
      trends: [],
      sandbox_default_speed_pct: 95,
      npsh_at_100: 1.2,
      npsh_at_88: 1.5,
      risk_at_100: 0.4,
      risk_at_88: 0.25,
      energy_delta_eur_day: -8,
      cooling_margin_pct: 110,
    };
  }

  return {
    asset_id: assetId,
    title: `${asset?.system ?? "Cooling"} pump`,
    diagnosis: "No active fault",
    event_class: "MACHINE",
    confidence: 0.99,
    safe_window: "Healthy envelope",
    evidence: [],
    sop: ["Continue normal watch", "Standby verification on schedule"],
    trends: [],
    sandbox_default_speed_pct: 100,
    npsh_at_100: 2,
    npsh_at_88: 2.3,
    risk_at_100: 0.05,
    risk_at_88: 0.04,
    energy_delta_eur_day: 0,
    cooling_margin_pct: 120,
  };
}

export const DUMMY_SCORECARD: ScorecardResponse = {
  composite_score: 87.7,
  event_f1: 0.94,
  precision: 1,
  fault_type_recall: 0.778,
  timeliness: 0.91,
  false_alarms: 0,
  t0_vs_t1: [
    { capability: "Cavitation detection", t0: "No", t1: "Yes" },
    { capability: "Impeller wear", t0: "No", t1: "Yes" },
    { capability: "Sensor drift isolation", t0: "No", t1: "Yes" },
    { capability: "Bearing faults (FFT)", t0: "No", t1: "Yes" },
    { capability: "Shaft misalignment", t0: "No", t1: "Yes" },
    { capability: "Warning lead time", t0: "26 h", t1: "168 h" },
  ],
  hardware_bom: [
    { item: "Magnetic tri-axial MEMS accelerometer", eur: 180 },
    { item: "Split-core CT clamp", eur: 65 },
    { item: "DIN-rail edge IPC", eur: 205 },
  ],
  economics: [
    { metric: "8-pump critical kit", value: "€3,600" },
    { metric: "12-pump full fleet", value: "€5,400" },
    { metric: "Crew install time", value: "45 min / pump" },
    { metric: "Single avoided ME casualty", value: "€48,500" },
    { metric: "Net payback", value: "< 1 avoided event" },
  ],
};
