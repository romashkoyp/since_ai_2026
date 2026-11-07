/** Mirrors shared/contracts + operator UI payloads */

export type EventClass = "MACHINE" | "SENSOR";

export type AlertSeverity = "SEVERE" | "MODERATE" | "MINIMAL" | "LOW_CONFIDENCE";

export type FaultType =
  | "BEARING_WEAR"
  | "SUCTION_STRAINER_CLOGGING"
  | "CAVITATION"
  | "DISCHARGE_RESTRICTION"
  | "MISALIGNMENT"
  | "IMBALANCE"
  | "IMPELLER_WEAR"
  | "AIR_ENTRAINMENT"
  | "SENSOR_DRIFT"
  | "SENSOR_STUCK"
  | "SENSOR_CALIBRATION_SHIFT"
  | "SENSOR_NOISE_SPIKES"
  | "COMMUNICATION_LOSS"
  | "UNKNOWN";

export interface AlertPrediction {
  asset_id: string;
  alert_time_utc: string;
  event_class: EventClass;
  fault_type: FaultType;
  confidence: number;
  severity?: AlertSeverity | null;
  evidence?: string | null;
  recommended_action?: string | null;
  /** Ground-truth fault when available (physics dashboard export) */
  true_fault_type?: string | null;
  /** Whether predicted fault_type matched ground truth */
  correct?: boolean | null;
}

/** Fleet triage level computed by the server from the open alerts' urgency */
export type Severity = "act_now" | "attention" | "sensor" | "ok";

export interface AssetStatus {
  asset_id: string;
  site: string;
  system: string;
  tier: string;
  status: string;
  mode: string;
  load_pct: number;
  open_alerts: number;
  fault_summary?: string | null;
  rul_hours?: number | null;
  severity?: Severity | null;
  last_data_utc?: string | null;
}

export interface FleetSummary {
  vessel: string;
  watch: string;
  critical: number;
  actionable: number;
  sensor_faults: number;
  availability_pct: number;
  healthy: number;
  total: number;
  nuisance_suppressed_pct?: number | null;
  run_id?: string | null;
  model_version?: string | null;
  data_end_utc?: string | null;
}

export interface TrendPoint {
  t: string;
  value: number;
}

export interface TrendSeries {
  name: string;
  unit: string;
  points: TrendPoint[];
  threshold?: number | null;
}

export interface EvidenceRow {
  channel: string;
  sigma: number;
  note: string;
}

export interface CockpitResponse {
  asset_id: string;
  title: string;
  diagnosis: string;
  event_class: EventClass;
  confidence: number;
  severity?: AlertSeverity | null;
  safe_window: string;
  evidence: EvidenceRow[];
  sop: string[];
  trends: TrendSeries[];
  sandbox_default_speed_pct: number;
  npsh_at_100: number;
  npsh_at_88: number;
  risk_at_100: number;
  risk_at_88: number;
  energy_delta_eur_day: number;
  cooling_margin_pct: number;
  /** Optional docs/demo fields (Screen 2 cockpit mock) */
  sign_off?: string | null;
  port_eta_hours?: number | null;
  standby_asset_id?: string | null;
  cooling_safe_flow_m3h?: number | null;
  spectrum_note?: string | null;
  rated_rpm?: number | null;
  /** Fault behind the diagnosis (most severe open alert) */
  fault_type?: FaultType | null;
  /** Physics assumptions behind the mitigation simulator numbers */
  sandbox_note?: string | null;
}

export interface ScorecardResponse {
  composite_score: number;
  event_f1: number;
  precision: number;
  fault_type_recall: number;
  timeliness: number;
  false_alarms: number;
  t0_vs_t1: { capability: string; t0: string; t1: string }[];
  hardware_bom: { item: string; eur: number }[];
  economics: { metric: string; value: string }[];
}

export interface HealthResponse {
  status: string;
  service: string;
  database?: string | null;
  model?: string | null;
}

export interface ModelInfo {
  available: boolean;
  model_version?: string | null;
  physics_version?: string | null;
  classes: string[];
  calibrated?: boolean | null;
  reason?: string | null;
  required_datasheet_columns: string[];
  min_history_hours?: number | null;
  max_upload_mb: number;
}

/** One model run over uploaded (or bundled demo) data; the dashboard shows the latest */
export interface AnalysisRun {
  run_id: string;
  created_utc: string;
  source: "upload" | "seed";
  label?: string | null;
  model_version: string;
  physics_version?: string | null;
  use_ml: boolean;
  pumps: number;
  alerts: number;
  ml_overrides: number;
  by_fault_type: Record<string, number>;
  data_start_utc?: string | null;
  data_end_utc?: string | null;
  processing_seconds: number;
  scored: boolean;
  notes: string[];
}

export type AnalysisFileField = "datasheet" | "telemetry" | "baseline" | "context" | "snapshots" | "events";

export type ScreenId = "fleet" | "cockpit" | "scorecard";

/** Why it failed vs what happens next */
export type CockpitMode = "diagnose" | "predict";
