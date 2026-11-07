import { useEffect, useState } from "react";
import { fetchCockpit } from "../api/client";
import { getDummyCockpit } from "../data/dummy";
import {
  channelLabel,
  explainFault,
  friendlyTime,
  severityOf,
  systemLabel,
  timeLeftLabel,
} from "../lib/plain";
import type { AlertPrediction, AssetStatus, CockpitMode, CockpitResponse } from "../types/alerts";
import { HealthBar, StatusBadge } from "./FleetView";
import { Icon } from "./Icon";
import { IssueChecklist } from "./IssueChecklist";
import { NextSteps } from "./NextSteps";
import { pumpHealth } from "../lib/issues";
import { LoadingBlock } from "./LoadingBlock";
import { Sparkline } from "./Sparkline";

interface Props {
  assetId: string | null;
  asset: AssetStatus | null;
  alert: AlertPrediction | null;
  assetAlerts?: AlertPrediction[];
  mode: CockpitMode;
  onModeChange: (mode: CockpitMode) => void;
  onBack: () => void;
  demoFallback?: boolean;
}

function diagnosisPlain(diagnosis: string): string {
  const d = diagnosis.toLowerCase();
  if (d.includes("strainer") && d.includes("cavitation")) {
    return "Blocked intake filter and air bubbles inside the pump";
  }
  if (d.includes("bearing") || d.includes("bpfo")) return "Worn bearing";
  if (d.includes("cavitation")) return "Air bubbles inside the pump";
  if (d.includes("strainer") || d.includes("clog")) return "Blocked intake filter";
  if (d.includes("no active")) return "Working normally";
  return diagnosis;
}

export function CockpitView({
  assetId,
  asset,
  alert,
  assetAlerts = [],
  mode,
  onModeChange,
  onBack,
  demoFallback = false,
}: Props) {
  const [data, setData] = useState<CockpitResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [usedFallback, setUsedFallback] = useState(false);

  useEffect(() => {
    if (!assetId) {
      setData(null);
      setLoading(false);
      return;
    }

    const ac = new AbortController();
    setLoading(true);
    setUsedFallback(false);
    setData(null);

    async function load(id: string) {
      try {
        const next = demoFallback ? getDummyCockpit(id) : await fetchCockpit(id);
        if (ac.signal.aborted) return;
        setData(next);
      } catch {
        if (ac.signal.aborted) return;
        const dummy = getDummyCockpit(id);
        setData(dummy);
        setUsedFallback(!demoFallback);
      } finally {
        if (!ac.signal.aborted) setLoading(false);
      }
    }

    void load(assetId);
    return () => ac.abort();
  }, [assetId, demoFallback]);

  if (!assetId) {
    return (
      <div className="empty-page">
        <Icon name="search" size={28} />
        <h1>Choose a pump first</h1>
        <p>Go to the Overview and pick a pump to see what is going on.</p>
        <button type="button" className="btn btn-primary" onClick={onBack}>
          Go to Overview
        </button>
      </div>
    );
  }

  if (loading || !data) {
    return <LoadingBlock label={`Looking at ${assetId}…`} variant="pump" />;
  }

  const severity = asset ? severityOf(asset) : data.risk_at_100 > 0.5 ? "act_now" : "ok";
  const isHealthy = severity === "ok" && /no active/i.test(data.diagnosis);
  const fault = explainFault(data.fault_type ?? alert?.fault_type);
  const health = pumpHealth(assetAlerts);
  const plainTitle = isHealthy ? "Working normally" : diagnosisPlain(data.diagnosis);
  const timeLeft = timeLeftLabel(asset?.rul_hours);


  return (
    <div className="pump-page">
      <button type="button" className="back-link" onClick={onBack}>
        <Icon name="back" size={16} /> All pumps
      </button>

      {usedFallback && (
        <div className="notice" role="status">
          <Icon name="help" size={18} />
          <span>Live details for this pump are not available right now. Showing example details from the demo set.</span>
        </div>
      )}

      <header className={`pump-hero sev-${severity}`}>
        <div className="pump-hero-main">
          <div className="pump-hero-top">
            <StatusBadge severity={severity} />
            <span className="muted">
              {/* title and system are often the same text: show each distinct part once */}
              {[data.title, asset && systemLabel(asset.system), asset?.site]
                .filter((part, i, all): part is string => !!part && all.indexOf(part) === i)
                .join(" · ")}
            </span>
          </div>
          <h1>
            {data.asset_id} <span className="muted-strong">— {plainTitle}</span>
          </h1>
          <p className="pump-hero-summary">
            {isHealthy
              ? "This pump is working normally. Nothing needs to be done."
              : `${fault.whyItMatters} ${data.safe_window}`}
          </p>
        </div>
        <dl className="pump-hero-facts">
          {asset && (
            <div>
              <dt>Health</dt>
              <dd>
                <HealthBar value={health.pct} title={`${health.passed} of ${health.total} machine issue types pass`} />
              </dd>
            </div>
          )}
          {timeLeft && (
            <div>
              <dt>Safe to run for</dt>
              <dd className="strong">{timeLeft}</dd>
            </div>
          )}
          {data.port_eta_hours != null && (
            <div>
              <dt>Port arrival</dt>
              <dd className="strong">in about {data.port_eta_hours} hours</dd>
            </div>
          )}
          {alert && (
            <div>
              <dt>Noticed</dt>
              <dd>{friendlyTime(alert.alert_time_utc)}</dd>
            </div>
          )}
        </dl>
      </header>

      <div className="tabs" role="tablist" aria-label="Pump questions">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "diagnose"}
          className={mode === "diagnose" ? "active" : ""}
          onClick={() => onModeChange("diagnose")}
        >
          <Icon name="search" size={16} />
          Why did this happen?
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "predict"}
          className={mode === "predict" ? "active" : ""}
          onClick={() => onModeChange("predict")}
        >
          <Icon name="trend" size={16} />
          What happens next?
        </button>
      </div>

      {mode === "diagnose" ? (
        <div className="tab-body" role="tabpanel">
          <IssueChecklist alerts={assetAlerts} />
          <section className="card diagnose-panel">
            {data.trends.length > 0 && (
              <details className="issue-section-acc">
                <summary>Sensor trends</summary>
                <p className="hint">Hourly averages of the sensors behind this diagnosis. Dashed line = alarm limit.</p>
                <div className="trend-grid">
                  {data.trends.map((series) => (
                    <Sparkline
                      key={series.name}
                      label={channelLabel(series.name)}
                      unit={series.unit}
                      values={series.points.map((p) => p.value)}
                      threshold={series.threshold}
                    />
                  ))}
                </div>
                {data.spectrum_note && (
                  <div className="spectrum-callout">
                    <Icon name="warning" size={18} />
                    <div>
                      <strong>Vibration spectrum</strong>
                      <p>
                        Cavitation band highlighted at <strong>{data.spectrum_note}</strong>.
                      </p>
                    </div>
                  </div>
                )}
              </details>
            )}

            <details className="issue-section-acc tech">
              <summary>Technical details for engineers</summary>
              <dl>
                <div>
                  <dt>Model diagnosis</dt>
                  <dd>{data.diagnosis}</dd>
                </div>
                <div>
                  <dt>Event class</dt>
                  <dd>{data.event_class}</dd>
                </div>
                {alert && (
                  <div>
                    <dt>Fault code</dt>
                    <dd>{alert.fault_type}</dd>
                  </div>
                )}
                {alert?.evidence && (
                  <div>
                    <dt>Raw evidence</dt>
                    <dd>{alert.evidence}</dd>
                  </div>
                )}
                {data.evidence.map((row) => (
                  <div key={row.channel}>
                    <dt>{row.channel}</dt>
                    <dd>
                      {row.sigma > 0 ? "+" : ""}
                      {row.sigma.toFixed(1)}σ · {row.note}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          </section>
        </div>
      ) : (
        <div className="tab-body" role="tabpanel">
          <NextSteps alerts={assetAlerts} />
        </div>
      )}
    </div>
  );
}
