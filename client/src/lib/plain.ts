import type { AlertPrediction, AssetStatus, FaultType } from "../types/alerts";

export type Severity = "act_now" | "attention" | "sensor" | "ok";

export interface FaultExplainer {
  title: string;
  whatItMeans: string;
  whyItMatters: string;
}

const FAULTS: Record<FaultType, FaultExplainer> = {
  BEARING_WEAR: {
    title: "Bearing wear",
    whatItMeans: "A bearing that lets the shaft spin smoothly is wearing out. The pump is shaking and running hotter than normal.",
    whyItMatters: "If ignored, the bearing can seize and stop the pump suddenly.",
  },
  SUCTION_STRAINER_CLOGGING: {
    title: "Strainer clogging",
    whatItMeans: "The filter where water enters the pump is getting clogged, so less water reaches the pump.",
    whyItMatters: "The pump has to work harder and may start damaging itself.",
  },
  CAVITATION: {
    title: "Cavitation",
    whatItMeans: "Water pressure at the inlet is too low, so small bubbles form and collapse inside the pump.",
    whyItMatters: "These bubbles slowly eat away the metal parts and reduce cooling.",
  },
  DISCHARGE_RESTRICTION: {
    title: "Restriction",
    whatItMeans: "Something is restricting water leaving the pump, like a partly closed valve.",
    whyItMatters: "Less cooling water flows and the pump wastes energy.",
  },
  MISALIGNMENT: {
    title: "Misalignment",
    whatItMeans: "The motor and pump are no longer perfectly lined up.",
    whyItMatters: "This wears out bearings and seals much faster.",
  },
  IMBALANCE: {
    title: "Imbalance",
    whatItMeans: "A spinning part is heavier on one side, causing the pump to shake.",
    whyItMatters: "Constant shaking damages bearings and mounts over time.",
  },
  IMPELLER_WEAR: {
    title: "Impeller wear",
    whatItMeans: "The spinning blades that push water are worn down.",
    whyItMatters: "The pump moves less water while using the same power.",
  },
  AIR_ENTRAINMENT: {
    title: "Air entrainment",
    whatItMeans: "Air is being sucked in with the water.",
    whyItMatters: "Pumping air reduces cooling and can damage the pump.",
  },
  SENSOR_DRIFT: {
    title: "Sensor reading slowly drifting",
    whatItMeans: "One measuring sensor is slowly giving wrong values. The pump itself looks fine.",
    whyItMatters: "Wrong readings can hide a real problem or cause false alarms.",
  },
  SENSOR_STUCK: {
    title: "Sensor frozen",
    whatItMeans: "A sensor keeps showing the same value. The pump itself looks fine.",
    whyItMatters: "We cannot see changes on that measurement until it is fixed.",
  },
  SENSOR_CALIBRATION_SHIFT: {
    title: "Sensor needs recalibration",
    whatItMeans: "A sensor suddenly jumped to a different level. The pump itself looks fine.",
    whyItMatters: "Readings from this sensor cannot be trusted until recalibrated.",
  },
  SENSOR_NOISE_SPIKES: {
    title: "Sensor giving noisy readings",
    whatItMeans: "A sensor is showing random spikes. The pump itself looks fine.",
    whyItMatters: "Noisy readings may cause false alarms.",
  },
  COMMUNICATION_LOSS: {
    title: "Lost connection to sensor",
    whatItMeans: "We stopped receiving data from this pump.",
    whyItMatters: "We cannot watch this pump until the connection is restored.",
  },
  UNKNOWN: {
    title: "Unusual behaviour",
    whatItMeans: "The pump is behaving differently from normal, but the exact cause is unclear.",
    whyItMatters: "An engineer should take a look.",
  },
};

/** MACHINE fault types shown on Pump details (detector issues). */
export const MACHINE_ISSUE_TYPES = [
  "BEARING_WEAR",
  "SUCTION_STRAINER_CLOGGING",
  "CAVITATION",
  "DISCHARGE_RESTRICTION",
  "MISALIGNMENT",
  "IMBALANCE",
  "IMPELLER_WEAR",
  "AIR_ENTRAINMENT",
] as const satisfies readonly FaultType[];

export type MachineIssueType = (typeof MACHINE_ISSUE_TYPES)[number];

export function isMachineIssue(fault: string | null | undefined): fault is MachineIssueType {
  return !!fault && (MACHINE_ISSUE_TYPES as readonly string[]).includes(fault);
}

export function explainFault(fault: FaultType | string | null | undefined): FaultExplainer {
  if (fault && fault in FAULTS) return FAULTS[fault as FaultType];
  return FAULTS.UNKNOWN;
}

export function severityOf(asset: AssetStatus): Severity {
  if (asset.status === "sensor_issue") return "sensor";
  if (asset.status !== "alert") return "ok";
  if (asset.rul_hours != null && asset.rul_hours <= 24) return "act_now";
  return "attention";
}

export const SEVERITY_ORDER: Record<Severity, number> = {
  act_now: 0,
  attention: 1,
  sensor: 2,
  ok: 3,
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  act_now: "Act now",
  attention: "Needs attention",
  sensor: "Check sensor",
  ok: "Working well",
};

/**
 * Display-only estimate from status + remaining safe hours; not a model output.
 */
export function healthScore(asset: AssetStatus): number {
  const sev = severityOf(asset);
  const rul = asset.rul_hours ?? 0;
  if (sev === "act_now") return Math.round(15 + (Math.min(rul, 24) / 24) * 20);
  if (sev === "attention") return Math.round(45 + (Math.min(rul, 96) / 96) * 25);
  if (sev === "sensor") return 85;
  return asset.load_pct > 85 ? 92 : 97;
}

const SYSTEMS: Record<string, string> = {
  "SW cooling": "Seawater cooling",
  "LT freshwater": "Freshwater cooling",
  "CW loop": "Cooling water loop",
  "LT main": "Main engine cooling",
  Transfer: "Water transfer",
};

export function systemLabel(system: string): string {
  return SYSTEMS[system] ?? system;
}

export function modeLabel(mode: string): string {
  if (mode === "RUNNING") return "Running";
  if (mode === "STANDBY") return "Ready as backup";
  if (mode === "STOPPED") return "Switched off";
  return mode.charAt(0) + mode.slice(1).toLowerCase();
}

export function timeLeftLabel(hours: number | null | undefined): string | null {
  if (hours == null) return null;
  if (hours < 1) return "less than 1 hour";
  if (hours < 48) return `about ${Math.round(hours)} hours`;
  const days = Math.round(hours / 24);
  return `about ${days} day${days === 1 ? "" : "s"}`;
}

export function confidenceLabel(confidence: number): string {
  if (confidence >= 0.85) return "Very likely";
  if (confidence >= 0.7) return "Likely";
  if (confidence >= 0.5) return "Possible";
  return "Uncertain";
}

const CHANNELS: Record<string, string> = {
  "suction pressure": "Water pressure at the inlet",
  "suction ps": "Water pressure at the inlet",
  "acoustic resonance": "Noise inside the pump",
  "housing acoustic resonance": "Noise inside the pump housing",
  "head vs affinity": "Pumping strength vs expected curve",
  "discharge head": "Discharge head (pumping strength)",
  "bearing temp": "Bearing temperature",
  "crest factor": "Knocking / impacts",
  "bpfo band": "Bearing vibration pattern",
  "vibration rms": "Shaking (vibration)",
  "motor current": "Electricity used by motor",
  "motor power": "Power used by motor",
};

export function channelLabel(channel: string): string {
  return CHANNELS[channel.trim().toLowerCase()] ?? channel;
}

const STEP_PHRASES: [RegExp, string][] = [
  [/\bderate (the )?vfd to\b/i, "Slow the pump down to"],
  [/\bderate to\b/i, "Slow the pump down to"],
  [/\btransfer duty to standby\b/i, "Switch the job to backup"],
  [/\bbackflush strainer\b/i, "Flush the intake filter clean"],
  [/\bvfd\b/gi, "speed controller"],
  [/\bstrainer\b/gi, "intake filter"],
  [/\bDE bearing\b/g, "main bearing"],
  [/\bNPSH margin\b/gi, "inlet pressure"],
  [/\bsetpoints?\b/gi, "settings"],
  [/\bPLC\b/g, "control system"],
];

export function plainStep(step: string): string {
  return STEP_PHRASES.reduce((s, [re, rep]) => s.replace(re, rep), step);
}

export function deviationLabel(sigma: number): { text: string; level: "high" | "mid" | "low" } {
  const dir = sigma >= 0 ? "higher" : "lower";
  const abs = Math.abs(sigma);
  if (abs >= 3) return { text: `Much ${dir} than normal`, level: "high" };
  if (abs >= 2) return { text: `Clearly ${dir} than normal`, level: "mid" };
  return { text: `Slightly ${dir} than normal`, level: "low" };
}

export function alertFor(assetId: string, alerts: AlertPrediction[]): AlertPrediction | undefined {
  return alerts.find((a) => a.asset_id === assetId);
}

export function friendlyTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
