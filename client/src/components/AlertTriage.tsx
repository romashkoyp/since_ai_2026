import { useMemo, useState } from "react";
import {
  ALERT_SEVERITY_LABEL,
  alertSeverity,
  explainFault,
  friendlyTime,
} from "../lib/plain";
import type { AlertPrediction, AlertSeverity } from "../types/alerts";

const BANDS: AlertSeverity[] = ["SEVERE", "MODERATE", "MINIMAL", "LOW_CONFIDENCE"];
const DEFAULT_BANDS = new Set<AlertSeverity>(["SEVERE", "MODERATE"]);

export function AlertTriage({ alerts }: { alerts: AlertPrediction[] }) {
  const [enabled, setEnabled] = useState<Set<AlertSeverity>>(() => new Set(DEFAULT_BANDS));

  const visible = useMemo(
    () => alerts.filter((alert) => enabled.has(alertSeverity(alert))),
    [alerts, enabled],
  );

  function toggle(band: AlertSeverity) {
    setEnabled((current) => {
      const next = new Set(current);
      if (next.has(band)) next.delete(band);
      else next.add(band);
      return next;
    });
  }

  return (
    <section className="card alert-triage" aria-labelledby="alert-triage-title">
      <div className="card-title-row">
        <h2 id="alert-triage-title">Alert triage</h2>
        <span className="progress-pill">
          {visible.length} of {alerts.length} shown
        </span>
      </div>
      <p className="hint">
        Moderate and severe alerts are shown by default. Toggle a band to include or hide it.
      </p>
      <div className="severity-toggles" role="group" aria-label="Alert severity filter">
        {BANDS.map((band) => (
          <button
            key={band}
            type="button"
            className={`severity-toggle alert-sev-${band.toLowerCase()} ${enabled.has(band) ? "active" : ""}`}
            onClick={() => toggle(band)}
            aria-pressed={enabled.has(band)}
          >
            {ALERT_SEVERITY_LABEL[band]}
          </button>
        ))}
      </div>

      {visible.length ? (
        <ul className="triage-list" aria-live="polite">
          {visible.map((alert, index) => {
            const severity = alertSeverity(alert);
            return (
              <li key={`${alert.asset_id}-${alert.alert_time_utc}-${index}`} className={`alert-sev-${severity.toLowerCase()}`}>
                <div className="triage-alert-head">
                  <strong>{explainFault(alert.fault_type).title}</strong>
                  <span className={`triage-severity alert-sev-${severity.toLowerCase()}`}>
                    {ALERT_SEVERITY_LABEL[severity]}
                  </span>
                </div>
                {alert.evidence && <p className="triage-evidence">{alert.evidence}</p>}
                <p className="triage-meta">
                  {friendlyTime(alert.alert_time_utc)} · {Math.round(alert.confidence * 100)}% confidence ·{" "}
                  {alert.event_class === "SENSOR" ? "Instrument review" : "Machine review"}
                </p>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="muted">No alerts in the selected bands.</p>
      )}
    </section>
  );
}
