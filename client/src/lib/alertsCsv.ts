import type { AlertPrediction } from "../types/alerts";

/** Matches hybrid_model/output_csv/predictions_template.csv */
const COLUMNS = [
  "asset_id",
  "alert_time_utc",
  "event_class",
  "fault_type",
  "confidence",
  "evidence",
  "recommended_action",
] as const;

function escapeCsv(value: string): string {
  if (/[",\n\r]/.test(value)) return `"${value.replaceAll('"', '""')}"`;
  return value;
}

export function alertsToPredictionCsv(alerts: AlertPrediction[]): string {
  const lines = [COLUMNS.join(",")];
  for (const a of alerts) {
    const row = [
      a.asset_id,
      a.alert_time_utc,
      a.event_class,
      a.fault_type,
      String(a.confidence),
      a.evidence ?? "",
      a.recommended_action ?? "",
    ].map((cell) => escapeCsv(cell));
    lines.push(row.join(","));
  }
  return `${lines.join("\n")}\n`;
}

export function downloadPredictionAlertsCsv(alerts: AlertPrediction[], filename = "predictions_alerts.csv"): void {
  const csv = alertsToPredictionCsv(alerts);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
