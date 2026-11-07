import { useMemo, useState } from "react";
import {
  alertFor,
  explainFault,
  healthScore,
  modeLabel,
  SEVERITY_LABEL,
  SEVERITY_ORDER,
  severityOf,
  systemLabel,
  timeLeftLabel,
  type Severity,
} from "../lib/plain";
import type { AlertPrediction, AssetStatus, FleetSummary } from "../types/alerts";
import { Icon } from "./Icon";

interface Props {
  summary: FleetSummary | null;
  assets: AssetStatus[];
  alerts: AlertPrediction[];
  updatedAt: Date | null;
  refreshing: boolean;
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

export function HealthBar({ value }: { value: number }) {
  const tone = value < 40 ? "act_now" : value < 75 ? "attention" : "ok";
  return (
    <div className="health">
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
  updatedAt,
  refreshing,
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

  const counts = useMemo(() => {
    const c: Record<Severity, number> = { act_now: 0, attention: 0, sensor: 0, ok: 0 };
    for (const a of assets) c[severityOf(a)] += 1;
    return c;
  }, [assets]);

  const total = summary?.total ?? assets.length;
  const okPct = total ? Math.round((counts.ok / total) * 100) : 0;

  const hero: { tone: Severity; title: string; text: string } =
    counts.act_now > 0
      ? {
          tone: "act_now",
          title: `${counts.act_now} pump${counts.act_now > 1 ? "s need" : " needs"} action now`,
          text: "Start with the red pumps below. Tap a pump to see what is wrong and what to do.",
        }
      : counts.attention > 0
        ? {
            tone: "attention",
            title: `${counts.attention} pump${counts.attention > 1 ? "s need" : " needs"} attention soon`,
            text: "Nothing is urgent right now, but plan these checks in the coming days.",
          }
        : counts.sensor > 0
          ? {
              tone: "sensor",
              title: "Pumps are fine — a sensor needs checking",
              text: "The machines are healthy. One measuring device is giving unreliable readings.",
            }
          : {
              tone: "ok",
              title: "All pumps are working well",
              text: "No action needed. We will alert you if anything changes.",
            };

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
      <section className={`hero sev-${hero.tone}`} aria-live="polite">
        <div className="hero-icon">
          <Icon name={SEVERITY_ICON[hero.tone]} size={28} />
        </div>
        <div className="hero-text">
          <h1>{hero.title}</h1>
          <p>{hero.text}</p>
          <p className="hero-meta">
            {summary?.vessel ?? "Your fleet"} · {total} pumps watched
            {updatedAt && ` · Updated ${updatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
            {refreshing && " · Updating…"}
          </p>
        </div>
        <div className="hero-score">
          <span className="hero-score-value">{okPct}%</span>
          <span className="hero-score-label">
            of pumps working normally
            <br />({counts.ok} of {total})
          </span>
        </div>
      </section>

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
              const failing = sev !== "ok";
              const alert = alertFor(asset.asset_id, alerts);
              const timeLeft = timeLeftLabel(asset.rul_hours);
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
                      <p className="pump-tile-site">{asset.site}</p>
                      {failing && (
                        <p className="pump-tile-fault">
                          {alert ? explainFault(alert.fault_type).title : asset.fault_summary ?? "Unusual behaviour"}
                          {timeLeft && <span> · safe for {timeLeft}</span>}
                        </p>
                      )}
                      <div className="pump-tile-row">
                        <span>Health</span>
                        <HealthBar value={healthScore(asset)} />
                      </div>
                      <p className="pump-tile-mode">
                        {modeLabel(asset.mode)}
                        {asset.mode === "RUNNING" && ` at ${Math.round(asset.load_pct)}% power`}
                      </p>
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

      <details className="legend">
        <summary>
          <Icon name="help" size={16} /> How to read this page
        </summary>
        <ul>
          <li>
            <StatusBadge severity="act_now" /> The pump could break soon. Act today.
          </li>
          <li>
            <StatusBadge severity="attention" /> Something is wearing out. Plan a check in the next few days.
          </li>
          <li>
            <StatusBadge severity="sensor" /> The pump is fine, but a measuring sensor is giving wrong readings.
          </li>
          <li>
            <StatusBadge severity="ok" /> Everything is normal.
          </li>
          <li>
            <strong>Health</strong> is a simple 0–100% score. Higher is better.
          </li>
        </ul>
      </details>
    </div>
  );
}
