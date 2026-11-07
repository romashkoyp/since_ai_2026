import type { AlertPrediction } from "../types/alerts";
import { MACHINE_ISSUE_TYPES, type MachineIssueType } from "./plain";

export type IssueVerdict = "pass" | "fail" | "unchecked";

/** One row per machine issue type on the pump page — always all 8, never duplicated */
export interface IssueRow {
  type: MachineIssueType;
  verdict: IssueVerdict;
  /** The model raised this issue type on this pump (pump health: Detected vs OK) */
  detected: boolean;
  /** Highest model confidence among this type's alerts (Detected rows only) */
  detectedConfidence: number | null;
  /** Confidence of the wrong call (Fail rows only) */
  failConfidence: number | null;
  /** Plain-language reason for the verdict */
  reason: string;
  /** Alerts behind the row: the model's alerts of this type, or the mislabelled real fault */
  alerts: AlertPrediction[];
}

const label = (fault: string) => (fault === "NO_FAULT" ? "no fault, a false alarm" : fault.replaceAll("_", " ").toLowerCase());

function maxBy(alerts: AlertPrediction[]): AlertPrediction {
  return alerts.reduce((best, a) => (a.confidence > best.confidence ? a : best));
}

/**
 * Pass / Fail per issue type, from the alerts' ground truth (`correct`, `true_fault_type`):
 * - any alert flagged this type while the real fault was different -> Fail (confidence of that wrong call)
 * - a real fault of this type was labelled as something else      -> Fail (confidence of the wrong label)
 * - flagged, and every alert right                                -> Pass
 * - not flagged and not present                                   -> Pass
 * Without ground truth (an upload with no known-faults file) rows are "unchecked".
 */
export function machineIssueRows(alerts: AlertPrediction[]): IssueRow[] {
  const scored = alerts.some((a) => a.correct != null);

  return MACHINE_ISSUE_TYPES.map((type): IssueRow => {
    const flagged = alerts.filter((a) => a.fault_type === type);
    const detected = flagged.length > 0;
    const detectedConfidence = detected ? maxBy(flagged).confidence : null;

    if (!scored) {
      return {
        type,
        verdict: "unchecked",
        detected,
        detectedConfidence,
        failConfidence: null,
        reason: detected
          ? `Flagged by the model (${flagged.length} alert${flagged.length === 1 ? "" : "s"}). Not checked: no known faults were supplied.`
          : "Not flagged by the model.",
        alerts: flagged,
      };
    }

    const hits = flagged.filter((a) => a.correct === true);
    const wrong = flagged.filter((a) => a.correct === false);
    const missed = alerts.filter((a) => a.true_fault_type === type && a.fault_type !== type);
    const right = hits.length ? ` (${hits.length} other alert${hits.length === 1 ? " was" : "s were"} right)` : "";

    if (wrong.length) {
      const worst = maxBy(wrong);
      return {
        type,
        verdict: "fail",
        detected,
        detectedConfidence,
        failConfidence: worst.confidence,
        reason:
          `${wrong.length} alert${wrong.length === 1 ? "" : "s"} flagged this, but the real fault was ` +
          `${label(worst.true_fault_type ?? "NO_FAULT")}${right}.`,
        alerts: flagged,
      };
    }

    if (missed.length) {
      const worst = maxBy(missed);
      return {
        type,
        verdict: "fail",
        detected,
        detectedConfidence,
        failConfidence: worst.confidence,
        reason: `This fault was really present, but the model called it ${label(worst.fault_type)}${right}.`,
        alerts: [...flagged, ...missed],
      };
    }

    return {
      type,
      verdict: "pass",
      detected,
      detectedConfidence,
      failConfidence: null,
      reason: detected
        ? `Detected correctly (${hits.length} alert${hits.length === 1 ? "" : "s"}).`
        : "Not present on this pump, and correctly not flagged.",
      alerts: flagged,
    };
  });
}
