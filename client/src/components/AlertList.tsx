import type { AlertPrediction } from "../types/alerts";

interface Props {
  alerts: AlertPrediction[];
}

function formatTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function AlertList({ alerts }: Props) {
  if (!alerts.length) {
    return <p className="muted">No alerts for this filter.</p>;
  }

  return (
    <ul className="alert-list">
      {alerts.map((alert) => (
        <li key={`${alert.asset_id}-${alert.alert_time_utc}-${alert.fault_type}`} className="alert-row">
          <div className="alert-top">
            <span className="asset-id">{alert.asset_id}</span>
            <span className={`chip class-${alert.event_class.toLowerCase()}`}>{alert.event_class}</span>
            <span className="fault">{alert.fault_type.replaceAll("_", " ")}</span>
            <span className="conf">{Math.round(alert.confidence * 100)}%</span>
          </div>
          <p className="time">{formatTime(alert.alert_time_utc)}</p>
          {alert.evidence && <p className="evidence">{alert.evidence}</p>}
          {alert.recommended_action && (
            <p className="action">
              <strong>Action:</strong> {alert.recommended_action}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
