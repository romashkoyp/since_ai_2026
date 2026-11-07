import { useEffect, useMemo, useState } from "react";
import { fetchCockpit } from "../api/client";
import { getDummyCockpit } from "../data/dummy";
import {
  channelLabel,
  confidenceLabel,
  deviationLabel,
  explainFault,
  friendlyTime,
  healthScore,
  modeLabel,
  plainStep,
  severityOf,
  systemLabel,
  timeLeftLabel,
} from "../lib/plain";
import type { AlertPrediction, AssetStatus, CockpitMode, CockpitResponse } from "../types/alerts";
import { HealthBar, StatusBadge } from "./FleetView";
import { Icon } from "./Icon";
import { LoadingBlock } from "./LoadingBlock";
import { Sparkline } from "./Sparkline";

interface Props {
  assetId: string | null;
  asset: AssetStatus | null;
  alert: AlertPrediction | null;
  mode: CockpitMode;
  onModeChange: (mode: CockpitMode) => void;
  onBack: () => void;
  demoFallback?: boolean;
}

const MIN_SPEED = 80;
const MAX_SPEED = 100;

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function project(data: CockpitResponse, speed: number) {
  const t = Math.min(Math.max((100 - speed) / 12, 0), 1);
  return {
    risk: lerp(data.risk_at_100, data.risk_at_88, t),
    npsh: lerp(data.npsh_at_100, data.npsh_at_88, t),
    energyDelta: data.energy_delta_eur_day * t,
  };
}

export function CockpitView({
  assetId,
  asset,
  alert,
  mode,
  onModeChange,
  onBack,
  demoFallback = false,
}: Props) {
  const [data, setData] = useState<CockpitResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [usedFallback, setUsedFallback] = useState(false);
  const [speed, setSpeed] = useState(100);
  const [done, setDone] = useState<Record<string, boolean>>({});

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
    setDone({});

    async function load(id: string) {
      try {
        const next = demoFallback ? getDummyCockpit(id) : await fetchCockpit(id);
        if (ac.signal.aborted) return;
        setData(next);
        setSpeed(next.sandbox_default_speed_pct);
      } catch {
        if (ac.signal.aborted) return;
        const dummy = getDummyCockpit(id);
        setData(dummy);
        setSpeed(dummy.sandbox_default_speed_pct);
        setUsedFallback(!demoFallback);
      } finally {
        if (!ac.signal.aborted) setLoading(false);
      }
    }

    void load(assetId);
    return () => ac.abort();
  }, [assetId, demoFallback]);

  const bestSpeed = useMemo(() => {
    if (!data) return null;
    let best = MAX_SPEED;
    let bestRisk = project(data, MAX_SPEED).risk;
    for (let s = MAX_SPEED; s >= MIN_SPEED; s -= 1) {
      const r = project(data, s).risk;
      if (r < bestRisk - 0.005) {
        best = s;
        bestRisk = r;
      }
    }
    return best;
  }, [data]);

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
  const isHealthy = severity === "ok";
  const fault = explainFault(alert?.fault_type);
  const faultTitle = alert ? fault.title : isHealthy ? "Working normally" : data.diagnosis;
  const confidencePct = Math.round(data.confidence * 100);
  const timeLeft = timeLeftLabel(asset?.rul_hours);
  const rulHours = asset?.rul_hours ?? null;

  const now = project(data, MAX_SPEED);
  const proj = project(data, speed);
  const riskNowPct = Math.round(now.risk * 100);
  const riskProjPct = Math.round(proj.risk * 100);
  const coolingOk = data.cooling_margin_pct >= 100;
  const saving = -proj.energyDelta;
  const doneCount = data.sop.filter((s) => done[s]).length;

  return (
    <div className="pump-page">
      <button type="button" className="back-link" onClick={onBack}>
        <Icon name="back" size={16} /> All pumps
      </button>

      {usedFallback && (
        <div className="notice" role="status">
          <Icon name="help" size={18} />
          <span>Live details for this pump are not available right now. Showing example details.</span>
        </div>
      )}

      <header className={`pump-hero sev-${severity}`}>
        <div className="pump-hero-main">
          <div className="pump-hero-top">
            <StatusBadge severity={severity} />
            <span className="muted">
              {asset ? `${systemLabel(asset.system)} · ${asset.site}` : data.title}
            </span>
          </div>
          <h1>
            {data.asset_id} <span className="muted-strong">— {faultTitle}</span>
          </h1>
          <p className="pump-hero-summary">
            {isHealthy
              ? "This pump is working normally. Nothing needs to be done."
              : `${fault.whyItMatters}${timeLeft ? ` It is safe to keep running for ${timeLeft}.` : ""}`}
          </p>
        </div>
        <dl className="pump-hero-facts">
          {asset && (
            <div>
              <dt>Health</dt>
              <dd>
                <HealthBar value={healthScore(asset)} />
              </dd>
            </div>
          )}
          {asset && (
            <div>
              <dt>Status</dt>
              <dd>
                {modeLabel(asset.mode)}
                {asset.mode === "RUNNING" ? ` at ${Math.round(asset.load_pct)}% power` : ""}
              </dd>
            </div>
          )}
          {timeLeft && (
            <div>
              <dt>Safe to run for</dt>
              <dd className="strong">{timeLeft}</dd>
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
          <div className="grid-2">
            <section className="card">
              <h2>What we found</h2>
              <p className="lead">{isHealthy ? "No problems found. All readings look normal." : fault.whatItMeans}</p>

              <div className="confidence">
                <div className="confidence-head">
                  <span>How sure we are</span>
                  <strong>
                    {confidenceLabel(data.confidence)} · {confidencePct}%
                  </strong>
                </div>
                <div className="meter" aria-hidden>
                  <span style={{ width: `${confidencePct}%` }} />
                </div>
              </div>

              {data.evidence.length > 0 && (
                <>
                  <h3>Warning signs we noticed</h3>
                  <ul className="signs">
                    {data.evidence.map((row) => {
                      const dev = deviationLabel(row.sigma);
                      return (
                        <li key={row.channel} className={`sign lvl-${dev.level}`}>
                          <div>
                            <strong>{channelLabel(row.channel)}</strong>
                            <span>{dev.text}</span>
                          </div>
                          <div className="sign-bar" aria-hidden>
                            <span style={{ width: `${Math.min((Math.abs(row.sigma) / 5) * 100, 100)}%` }} />
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </section>

            <section className="card">
              <div className="card-title-row">
                <h2>What to do</h2>
                {data.sop.length > 0 && (
                  <span className="progress-pill">
                    {doneCount} of {data.sop.length} done
                  </span>
                )}
              </div>
              <ol className="checklist">
                {data.sop.map((step, i) => (
                  <li key={step} className={done[step] ? "done" : ""}>
                    <label>
                      <input
                        type="checkbox"
                        checked={!!done[step]}
                        onChange={(e) => setDone((d) => ({ ...d, [step]: e.target.checked }))}
                      />
                      <span className="step-num">{i + 1}</span>
                      <span>{plainStep(step)}</span>
                    </label>
                  </li>
                ))}
              </ol>
              <p className="hint">Ticking steps here is just for your own tracking. It does not change the pump.</p>
            </section>
          </div>

          {data.trends.length > 0 && (
            <section className="card">
              <h2>How the readings changed</h2>
              <p className="hint">The dashed line is the safe limit. The latest reading is the dot on the right.</p>
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
            </section>
          )}

          <details className="tech">
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
        </div>
      ) : (
        <div className="tab-body" role="tabpanel">
          <section className="card">
            <h2>If nothing is done</h2>
            {isHealthy ? (
              <p className="lead">This pump is expected to keep running normally. No breakdown is predicted.</p>
            ) : (
              <>
                <p className="lead">
                  There is a <strong className="text-danger">{riskNowPct}% chance</strong> of damage if the pump keeps
                  running at full speed.
                </p>
                <ol className="timeline">
                  <li className="tl-now">
                    <span className="tl-dot" />
                    <strong>Now</strong>
                    <span>Problem detected. Pump still running.</span>
                  </li>
                  {rulHours != null && (
                    <li className="tl-warn">
                      <span className="tl-dot" />
                      <strong>In {timeLeftLabel(Math.max(rulHours / 2, 1))}</strong>
                      <span>Wear gets worse. Less cooling, more noise and heat.</span>
                    </li>
                  )}
                  <li className="tl-fail">
                    <span className="tl-dot" />
                    <strong>{rulHours != null ? `In ${timeLeftLabel(rulHours)}` : "Later"}</strong>
                    <span>Pump may stop working and need emergency repair.</span>
                  </li>
                </ol>
              </>
            )}
          </section>

          <section className="card">
            <h2>Try it: slow the pump down</h2>
            <p className="hint">
              Move the slider to see what would happen. This is only a simulation. It does not change the real pump.
            </p>

            <div className="slider">
              <div className="slider-head">
                <span>Pump speed</span>
                <strong>{speed}%</strong>
              </div>
              <input
                type="range"
                min={MIN_SPEED}
                max={MAX_SPEED}
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
                aria-label="Pump speed"
              />
              <div className="slider-scale">
                <span>Slower ({MIN_SPEED}%)</span>
                <span>Full speed</span>
              </div>
            </div>

            <div className="outcomes">
              <div className="outcome">
                <span className="outcome-label">Chance of damage</span>
                <div className="outcome-compare">
                  <span className="was">{riskNowPct}%</span>
                  <Icon name="back" size={14} className="flip" />
                  <strong className={riskProjPct > 50 ? "text-danger" : riskProjPct > 25 ? "text-warn" : "text-ok"}>
                    {riskProjPct}%
                  </strong>
                </div>
                <div className="meter" aria-hidden>
                  <span
                    className={riskProjPct > 50 ? "bg-danger" : riskProjPct > 25 ? "bg-warn" : "bg-ok"}
                    style={{ width: `${riskProjPct}%` }}
                  />
                </div>
              </div>
              <div className="outcome">
                <span className="outcome-label">Enough cooling?</span>
                <strong className={coolingOk ? "text-ok" : "text-danger"}>
                  {coolingOk ? "Yes" : "No"} <small>({data.cooling_margin_pct}% of what is needed)</small>
                </strong>
              </div>
              <div className="outcome">
                <span className="outcome-label">Energy cost</span>
                <strong className={saving >= 0 ? "text-ok" : "text-warn"}>
                  {Math.round(saving) === 0
                    ? "No change"
                    : saving > 0
                      ? `Saves €${saving.toFixed(0)} per day`
                      : `Costs €${Math.abs(saving).toFixed(0)} more per day`}
                </strong>
              </div>
            </div>

            {!isHealthy && bestSpeed != null && bestSpeed < MAX_SPEED && (
              <div className="recommend">
                <Icon name="check" size={18} />
                <div>
                  <strong>Our suggestion:</strong> run at about {bestSpeed}% speed until the repair. This lowers the chance of
                  damage to about {Math.round(project(data, bestSpeed).risk * 100)}%
                  {coolingOk ? " while still giving enough cooling." : "."}
                  {speed !== bestSpeed && (
                    <button type="button" className="link-btn" onClick={() => setSpeed(bestSpeed)}>
                      Show me
                    </button>
                  )}
                </div>
              </div>
            )}

            <details className="tech">
              <summary>Technical details for engineers</summary>
              <dl>
                <div>
                  <dt>NPSH margin at {speed}%</dt>
                  <dd>{proj.npsh.toFixed(2)} m</dd>
                </div>
                <div>
                  <dt>Risk at 100% / 88%</dt>
                  <dd>
                    {Math.round(data.risk_at_100 * 100)}% / {Math.round(data.risk_at_88 * 100)}%
                  </dd>
                </div>
                <div>
                  <dt>Energy delta at {speed}%</dt>
                  <dd>{proj.energyDelta.toFixed(1)} €/day</dd>
                </div>
              </dl>
            </details>
          </section>
        </div>
      )}
    </div>
  );
}
