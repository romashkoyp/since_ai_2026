import type { AlertPrediction, AssetStatus, FleetSummary } from "../types/alerts";

interface Props {
  summary: FleetSummary | null;
  assets: AssetStatus[];
  alerts: AlertPrediction[];
  selected: string | null;
  onSelect: (assetId: string) => void;
}

function statusLabel(status: string): string {
  if (status === "alert") return "Action needed";
  if (status === "sensor_issue") return "Sensor issue";
  return "Healthy";
}

export function FleetView({ summary, assets, alerts, selected, onSelect }: Props) {
  return (
    <div className="screen fleet-screen">
      <section className="summary-row" aria-label="Fleet summary">
        <article className="stat">
          <span className="stat-label">Context</span>
          <strong>{summary?.vessel ?? "Fleet"}</strong>
          <p>{summary?.watch ?? "—"}</p>
        </article>
        <article className="stat">
          <span className="stat-label">Critical</span>
          <strong className="ok-text">{summary?.critical ?? 0}</strong>
          <p>Immediate stop risks</p>
        </article>
        <article className="stat">
          <span className="stat-label">Actionable</span>
          <strong className="warn-text">{summary?.actionable ?? 0}</strong>
          <p>Mechanical advisories</p>
        </article>
        <article className="stat">
          <span className="stat-label">Sensor faults</span>
          <strong className="info-text">{summary?.sensor_faults ?? 0}</strong>
          <p>Isolated from machine checks</p>
        </article>
        <article className="stat">
          <span className="stat-label">Availability</span>
          <strong>
            {summary?.availability_pct ?? "—"}%
            <span className="sub">
              {" "}
              ({summary?.healthy ?? 0}/{summary?.total ?? 0})
            </span>
          </strong>
          <p>{summary?.nuisance_suppressed_pct ?? 0}% nuisance suppressed</p>
        </article>
      </section>

      <section>
        <div className="section-head">
          <h2>Fleet matrix</h2>
          <p className="muted">Select a pump to open the diagnostic cockpit</p>
        </div>
        <ul className="pump-grid">
          {assets.map((asset) => (
            <li key={asset.asset_id}>
              <button
                type="button"
                className={`pump-card status-${asset.status} ${selected === asset.asset_id ? "selected" : ""}`}
                onClick={() => onSelect(asset.asset_id)}
              >
                <div className="pump-top">
                  <span className="asset-id">{asset.asset_id}</span>
                  <span className="tier">{asset.tier}</span>
                </div>
                <p className="mode">
                  {asset.mode}
                  {asset.mode === "RUNNING" ? ` · ${Math.round(asset.load_pct)}% load` : ""}
                </p>
                <p className={`badge status-${asset.status}`}>{statusLabel(asset.status)}</p>
                {asset.fault_summary && <p className="fault-line">{asset.fault_summary}</p>}
                {asset.rul_hours != null && (
                  <p className="rul">Safe window ~{asset.rul_hours}h</p>
                )}
                <div className="load-bar" aria-hidden>
                  <span style={{ width: `${Math.min(asset.load_pct, 100)}%` }} />
                </div>
                <p className="meta">
                  {asset.site} · {asset.system}
                </p>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="alert-rail">
        <div className="section-head">
          <h2>Open alerts</h2>
        </div>
        <ul className="alert-compact">
          {alerts.map((a) => (
            <li key={`${a.asset_id}-${a.alert_time_utc}`}>
              <button type="button" className="text-btn" onClick={() => onSelect(a.asset_id)}>
                <span className="asset-id">{a.asset_id}</span>
                <span className={`chip class-${a.event_class.toLowerCase()}`}>{a.event_class}</span>
                <span>{a.fault_type.replaceAll("_", " ")}</span>
                <span className="conf">{Math.round(a.confidence * 100)}%</span>
              </button>
            </li>
          ))}
          {!alerts.length && <li className="muted">No open alerts</li>}
        </ul>
      </section>
    </div>
  );
}
