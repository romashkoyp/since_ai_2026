import { useMemo, useState } from "react";
import { downloadPredictionAlertsCsv } from "../lib/alertsCsv";
import { pumpHealth } from "../lib/issues";
import {
  SEVERITY_LABEL,
  SEVERITY_ORDER,
  severityOf,
  systemLabel,
  type Severity,
} from "../lib/plain";
import type { AlertPrediction, AssetStatus, FleetSummary } from "../types/alerts";
import { Icon } from "./Icon";

interface Props {
  summary: FleetSummary | null;
  assets: AssetStatus[];
  alerts: AlertPrediction[];
  onDiagnose: (assetId: string) => void;
  onPredict: (assetId: string) => void;
}

type Filter = "all" | Severity;

const SEVERITY_ICON = {
  act_now: "alert",
  attention: "warning",
  sensor: "sensor",
  ok: "check",
} as const;

export function StatusBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`status-badge sev-${severity}`}>
      <Icon name={SEVERITY_ICON[severity]} size={14} />
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

export function HealthBar({ value, title }: { value: number; title?: string }) {
  // health = machine issue types passed / 8: green only when nothing failed
  const tone = value >= 100 ? "ok" : value >= 50 ? "attention" : "act_now";
  return (
    <div className="health" title={title}>
      <div className="health-track" aria-hidden>
        <span className={`health-fill sev-${tone}`} style={{ width: `${value}%` }} />
      </div>
      <span className="health-value">{value}%</span>
    </div>
  );
}

export function FleetView({
  summary,
  assets,
  alerts,
  onDiagnose,
  onPredict,
}: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const ranked = useMemo(
    () =>
      [...assets].sort((a, b) => {
        const d = SEVERITY_ORDER[severityOf(a)] - SEVERITY_ORDER[severityOf(b)];
        if (d !== 0) return d;
        return (a.rul_hours ?? Infinity) - (b.rul_hours ?? Infinity);
      }),
    [assets],
  );

  const alertsByPump = useMemo(() => {
    const m = new Map<string, AlertPrediction[]>();
    for (const a of alerts) m.set(a.asset_id, [...(m.get(a.asset_id) ?? []), a]);
    return m;
  }, [alerts]);

  const counts = useMemo(() => {
    const c: Record<Severity, number> = { act_now: 0, attention: 0, sensor: 0, ok: 0 };
    for (const a of assets) c[severityOf(a)] += 1;
    return c;
  }, [assets]);

  const total = summary?.total ?? assets.length;

  const visible = ranked.filter((a) => {
    if (filter !== "all" && severityOf(a) !== filter) return false;
    if (!query.trim()) return true;
    const q = query.trim().toLowerCase();
    return (
      a.asset_id.toLowerCase().includes(q) ||
      systemLabel(a.system).toLowerCase().includes(q) ||
      a.site.toLowerCase().includes(q)
    );
  });

  return (
    <div className="overview">
      <section className="filters" aria-label="Filter pumps by status">
        {(["act_now", "attention", "sensor", "ok"] as Severity[]).map((sev) => (
          <button
            key={sev}
            type="button"
            className={`count-card sev-${sev} ${filter === sev ? "active" : ""}`}
            onClick={() => setFilter(filter === sev ? "all" : sev)}
            aria-pressed={filter === sev}
          >
            <span className="count-icon">
              <Icon name={SEVERITY_ICON[sev]} size={18} />
            </span>
            <span className="count-num">{counts[sev]}</span>
            <span className="count-label">{SEVERITY_LABEL[sev]}</span>
            <span className="count-pct">{total ? Math.round((counts[sev] / total) * 100) : 0}% of pumps</span>
          </button>
        ))}
      </section>

      <section className="section">
        <div className="section-title">
          <h2>All pumps</h2>
          <div className="section-actions">
            <div className="search">
              <Icon name="search" size={16} />
              <input
                type="search"
                placeholder="Search pump, system or location"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search pumps"
              />
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm download-csv-btn"
              disabled={alerts.length === 0}
              onClick={() =>
                downloadPredictionAlertsCsv(
                  alerts,
                  `predictions_alerts_${new Date().toISOString().slice(0, 10)}.csv`,
                )
              }
              title="Download prediction alerts as CSV"
            >
              <Icon name="download" size={14} />
              Download CSV
            </button>
          </div>
        </div>

        {filter !== "all" && (
          <p className="filter-note">
            Showing only <strong>{SEVERITY_LABEL[filter]}</strong>.{" "}
            <button type="button" className="link-btn" onClick={() => setFilter("all")}>
              Show all pumps
            </button>
          </p>
        )}

        {visible.length ? (
          <ul className="pump-grid">
            {visible.map((asset) => {
              const sev = severityOf(asset);
              const health = pumpHealth(alertsByPump.get(asset.asset_id) ?? []);
              return (
                <li key={asset.asset_id}>
                  <div className={`pump-tile sev-${sev}`}>
                    <button
                      type="button"
                      className="pump-tile-body"
                      onClick={() => onDiagnose(asset.asset_id)}
                    >
                      <div className="pump-tile-head">
                        <strong>{asset.asset_id}</strong>
                        <StatusBadge severity={sev} />
                      </div>
                      <p className="pump-tile-system">{systemLabel(asset.system)}</p>
                      <div className="pump-tile-row">
                        <span>Health</span>
                        <HealthBar
                          value={health.pct}
                          title={`${health.passed} of ${health.total} machine issue types pass`}
                        />
                      </div>
                    </button>
                    <div className="pump-tile-actions">
                      {sev !== "ok" && (
                        <button type="button" className="btn btn-primary btn-sm" onClick={() => onDiagnose(asset.asset_id)}>
                          <Icon name="search" size={14} />
                          Why did this happen?
                        </button>
                      )}
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => onPredict(asset.asset_id)}>
                        <Icon name="trend" size={14} />
                        What happens next?
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="empty">
            <Icon name="search" size={22} />
            <p>No pumps match your search.</p>
            <button
              type="button"
              className="link-btn"
              onClick={() => {
                setQuery("");
                setFilter("all");
              }}
            >
              Clear search
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
