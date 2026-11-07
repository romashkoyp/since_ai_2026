/** Mirrors shared/contracts.schema.json AlertPrediction */

export type EventClass = "MACHINE" | "SENSOR";

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
  evidence?: string | null;
  recommended_action?: string | null;
}

export interface AssetStatus {
  asset_id: string;
  site: string;
  tier: string;
  status: string;
  open_alerts: number;
}

export interface HealthResponse {
  status: string;
  service: string;
}
