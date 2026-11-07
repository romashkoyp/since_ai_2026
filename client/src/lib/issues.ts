import type { AlertPrediction, FaultType } from "../types/alerts";
import { MACHINE_ISSUE_TYPES } from "./plain";

export type IssueVerdict = "pass" | "fail" | "unchecked";

/**
 * One row per issue type on the pump page — every type always listed once, never duplicated.
 *  - Pump result: Fail = this issue occurred (with how often and the highest confidence), Pass = no issue.
 *  - Model check: was the model right about this type vs the recorded real faults (when known).
 */
export interface IssueRow {
  type: FaultType;
  /** The issue occurred on this pump (the model raised alerts of this type) */
  occurred: boolean;
  /** Every alert of this type, oldest first — the same issue can repeat at different times */
  occurrences: AlertPrediction[];
  /** Highest confidence among the occurrences */
  confidence: number | null;
  /** Model check against the real faults */
  verdict: IssueVerdict;
  /** Confidence of the wrong call (verdict "fail" only) */
  wrongConfidence: number | null;
  /** Plain-language reason for the model check */
  reason: string;
  /** Alerts that make the model check wrong (wrong calls, or the mislabelled real fault) */
  wrongAlerts: AlertPrediction[];
}

/** The 8 machine issue types (sensor problems do not count against the pump's own health). */
const MACHINE_TYPES: readonly FaultType[] = MACHINE_ISSUE_TYPES;

export interface PumpHealth {
  /** Machine issue types with no issue */
  passed: number;
  total: number;
  /** passed / total, as a whole percentage */
  pct: number;
}

/** Health = machine issue types that passed / 8 — e.g. 2 failed types -> 6/8 = 75 %. */
export function pumpHealth(pumpAlerts: AlertPrediction[]): PumpHealth {
  const failed = new Set(pumpAlerts.map((a) => a.fault_type).filter((t) => MACHINE_TYPES.includes(t))).size;
  const total = MACHINE_TYPES.length;
  return { passed: total - failed, total, pct: Math.round((100 * (total - failed)) / total) };
}

const label = (fault: string) => (fault === "NO_FAULT" ? "no fault, a false alarm" : fault.replaceAll("_", " ").toLowerCase());

function maxBy(alerts: AlertPrediction[]): AlertPrediction {
  return alerts.reduce((best, a) => (a.confidence > best.confidence ? a : best));
}

/**
 * Model check per type, from the alerts' ground truth (`correct`, `true_fault_type`):
 * - any alert named this type while the real fault was different -> Wrong (confidence of that wrong call)
 * - a real fault of this type was named as something else        -> Wrong (confidence of the wrong label)
 * - otherwise                                                     -> Correct
 * Without ground truth (an upload with no known-faults file) the check is "unchecked".
 */
export function issueRows(alerts: AlertPrediction[], types: readonly FaultType[]): IssueRow[] {
  const scored = alerts.some((a) => a.correct != null);

  return types.map((type): IssueRow => {
    const occurrences = alerts.filter((a) => a.fault_type === type);
    const base = {
      type,
      occurred: occurrences.length > 0,
      occurrences,
      confidence: occurrences.length ? maxBy(occurrences).confidence : null,
    };
    if (!scored) {
      return { ...base, verdict: "unchecked", wrongConfidence: null, wrongAlerts: [],
        reason: "No known faults were supplied for this data, so the model's call is not checked." };
    }

    const hits = occurrences.filter((a) => a.correct === true);
    const wrong = occurrences.filter((a) => a.correct === false);
    const missed = alerts.filter((a) => a.true_fault_type === type && a.fault_type !== type);
    const right = hits.length ? ` (${hits.length} other alert${hits.length === 1 ? " was" : "s were"} right)` : "";

    if (wrong.length) {
      const worst = maxBy(wrong);
      return { ...base, verdict: "fail", wrongConfidence: worst.confidence, wrongAlerts: wrong,
        reason: `${wrong.length} alert${wrong.length === 1 ? "" : "s"} named this, but the real fault was ` +
          `${label(worst.true_fault_type ?? "NO_FAULT")}${right}.` };
    }
    if (missed.length) {
      const worst = maxBy(missed);
      return { ...base, verdict: "fail", wrongConfidence: worst.confidence, wrongAlerts: missed,
        reason: `This fault was really present, but the model called it ${label(worst.fault_type)}${right}.` };
    }
    return { ...base, verdict: "pass", wrongConfidence: null, wrongAlerts: [],
      reason: base.occurred
        ? "Matches the real faults recorded for this pump."
        : "Not present on this pump, and correctly not raised." };
  });
}
