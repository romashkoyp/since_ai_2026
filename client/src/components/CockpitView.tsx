import { useEffect, useMemo, useState } from "react";
import { fetchCockpit } from "../api/client";
import { getDummyCockpit } from "../data/dummy";
import {
  channelLabel,
  confidenceLabel,
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
  assetAlerts?: AlertPrediction[];
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
    rpm: data.rated_rpm != null ? Math.round(data.rated_rpm * (speed / 100)) : null,
  };
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
  const [speed, setSpeed] = useState(100);

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
  const isHealthy = severity === "ok" && /no active/i.test(data.diagnosis);
  const fault = explainFault(alert?.fault_type);
  const plainTitle = isHealthy ? "Working normally" : diagnosisPlain(data.diagnosis);
  const timeLeft = timeLeftLabel(asset?.rul_hours);
  const rulHours = asset?.rul_hours ?? null;

  const now = project(data, MAX_SPEED);
  const proj = project(data, speed);
  const riskNowPct = Math.round(now.risk * 100);
  const riskProjPct = Math.round(proj.risk * 100);
  const coolingOk = data.cooling_margin_pct >= 100;
  const saving = -proj.energyDelta;

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
              {data.title}
              {asset ? ` · ${systemLabel(asset.system)} · ${asset.site}` : ""}
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
          <section className="card diagnose-panel">
            <div className="card-title-row">
              <h2>Detected issues</h2>
              <span className="progress-pill">
                {assetAlerts.length} alert{assetAlerts.length === 1 ? "" : "s"}
                {assetAlerts.some((a) => a.correct != null) && (
                  <>
                    {" · "}
                    {assetAlerts.filter((a) => a.correct === true).length} pass
                    {" · "}
                    {assetAlerts.filter((a) => a.correct === false).length} fail
                  </>
                )}
              </span>
            </div>
            <p className="hint issue-legend">
              Tap a row for evidence. <strong>Pass</strong> = matches ground truth · <strong>Fail</strong> = wrong
              label.
            </p>
            {assetAlerts.length === 0 ? (
              <p className="muted">No detector alerts for this pump in the current data set.</p>
            ) : (
              <div className="issue-accordion">
                {assetAlerts.map((a, i) => {
                  const confPct = Math.round(a.confidence * 100);
                  const verdict =
                    a.correct === true ? "pass" : a.correct === false ? "fail" : "unknown";
                  const key = `${a.asset_id}-${a.alert_time_utc}-${a.fault_type}-${i}`;
                  return (
                    <details key={key} className={`issue-acc verdict-${verdict}`}>
                      <summary className="issue-acc-summary">
                        <span className="issue-acc-chevron" aria-hidden />
                        <span className="issue-acc-title">{explainFault(a.fault_type).title}</span>
                        {verdict === "pass" && (
                          <span className="verdict-badge pass">
                            <Icon name="check" size={14} /> Pass
                          </span>
                        )}
                        {verdict === "fail" && (
                          <span className="verdict-badge fail">
                            <Icon name="alert" size={14} /> Fail
                          </span>
                        )}
                        {verdict === "unknown" && <span className="verdict-badge unknown">Unchecked</span>}
                        <span className="issue-acc-conf">
                          <strong>{confPct}%</strong>
                          <span className="issue-acc-meter" aria-hidden>
                            <span
                              className={verdict === "fail" ? "bg-danger" : verdict === "pass" ? "bg-ok" : ""}
                              style={{ width: `${confPct}%` }}
                            />
                          </span>
                        </span>
                      </summary>
                      <div className="issue-acc-body">
                        <dl className="issue-acc-meta">
                          <div>
                            <dt>Fault code</dt>
                            <dd>{a.fault_type.replaceAll("_", " ")}</dd>
                          </div>
                          <div>
                            <dt>Class</dt>
                            <dd>{a.event_class}</dd>
                          </div>
                          <div>
                            <dt>Noticed</dt>
                            <dd>{friendlyTime(a.alert_time_utc)}</dd>
                          </div>
                          <div>
                            <dt>Confidence</dt>
                            <dd>
                              {confidenceLabel(a.confidence)} · {confPct}%
                            </dd>
                          </div>
                          {a.true_fault_type && (
                            <div>
                              <dt>True fault</dt>
                              <dd>{a.true_fault_type.replaceAll("_", " ")}</dd>
                            </div>
                          )}
                        </dl>
                        {a.evidence && (
                          <p className="issue-evidence">
                            <strong>Evidence:</strong> {a.evidence}
                          </p>
                        )}
                        {a.recommended_action && (
                          <p className="issue-action">
                            <Icon name="check" size={14} /> {plainStep(a.recommended_action)}
                          </p>
                        )}
                      </div>
                    </details>
                  );
                })}
              </div>
            )}

            {data.trends.length > 0 && (
              <details className="issue-section-acc">
                <summary>Sensor trends</summary>
                <p className="hint">Discharge head, suction pressure, and motor power. Dashed line = safe limit.</p>
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
          <section className="card">
            <h2>If nothing is done</h2>
            {isHealthy ? (
              <p className="lead">This pump is expected to keep running normally. No breakdown is predicted.</p>
            ) : (
              <>
                <p className="lead">
                  There is a <strong className="text-danger">{riskNowPct}% chance</strong> of damage if the pump keeps
                  running at full speed (risk at 100% from the mitigation model).
                </p>
                <ol className="timeline">
                  <li className="tl-now">
                    <span className="tl-dot" />
                    <strong>Now</strong>
                    <span>Problem detected. Pump still running.</span>
                  </li>
                  {data.port_eta_hours != null && (
                    <li className="tl-warn">
                      <span className="tl-dot" />
                      <strong>In about {data.port_eta_hours} hours</strong>
                      <span>Ship reaches port — planned window for filter clean / repair.</span>
                    </li>
                  )}
                  <li className="tl-fail">
                    <span className="tl-dot" />
                    <strong>{rulHours != null ? `In ${timeLeftLabel(rulHours)}` : "Later"}</strong>
                    <span>Without derate, pump may leave the safe window and need emergency repair.</span>
                  </li>
                </ol>
              </>
            )}
          </section>

          <section className="card">
            <h2>Mitigation simulator</h2>
            <p className="hint">
              What-if digital twin: adjust VFD speed. Sandbox only — no live PLC writes.
              {data.rated_rpm != null && proj.rpm != null && (
                <>
                  {" "}
                  At {speed}% ≈ <strong>{proj.rpm} RPM</strong> (rated {data.rated_rpm} RPM).
                </>
              )}
            </p>

            <div className="slider">
              <div className="slider-head">
                <span>VFD speed derate</span>
                <strong>
                  {MAX_SPEED}% → {speed}%
                </strong>
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
                <span>Full speed ({MAX_SPEED}%)</span>
              </div>
            </div>

            <div className="outcomes">
              <div className="outcome">
                <span className="outcome-label">NPSH margin</span>
                <div className="outcome-compare">
                  <span className="was">{data.npsh_at_100.toFixed(2)} m</span>
                  <Icon name="back" size={14} className="flip" />
                  <strong className="text-ok">{proj.npsh.toFixed(2)} m</strong>
                </div>
              </div>
              <div className="outcome">
                <span className="outcome-label">Risk</span>
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
                <span className="outcome-label">Energy</span>
                <strong className={saving >= 0 ? "text-ok" : "text-warn"}>
                  {Math.round(saving) === 0
                    ? "No change"
                    : saving > 0
                      ? `−€${saving.toFixed(2)}/day`
                      : `+€${Math.abs(saving).toFixed(2)}/day`}
                </strong>
              </div>
            </div>

            <div className="cooling-bar">
              <div className="cooling-bar-head">
                <span>Main engine HT cooling margin</span>
                <strong className={coolingOk ? "text-ok" : "text-danger"}>
                  {data.cooling_margin_pct}%
                  {data.cooling_safe_flow_m3h != null && (
                    <small> (SAFE: {data.cooling_safe_flow_m3h} m³/h)</small>
                  )}
                </strong>
              </div>
              <div className="meter" aria-hidden>
                <span
                  className={coolingOk ? "bg-ok" : "bg-danger"}
                  style={{ width: `${Math.min(data.cooling_margin_pct, 100)}%` }}
                />
              </div>
            </div>

            {!isHealthy && bestSpeed != null && bestSpeed < MAX_SPEED && (
              <div className="recommend">
                <Icon name="check" size={18} />
                <div>
                  <strong>Suggested derate:</strong> {bestSpeed}% speed
                  {data.standby_asset_id ? ` until duty transfers to ${data.standby_asset_id}` : ""}. Risk drops to about{" "}
                  {Math.round(project(data, bestSpeed).risk * 100)}%
                  {coolingOk ? " while cooling stays safe." : "."}
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
                  <dt>NPSH at 100% / 88%</dt>
                  <dd>
                    {data.npsh_at_100.toFixed(2)} m / {data.npsh_at_88.toFixed(2)} m
                  </dd>
                </div>
                <div>
                  <dt>Risk at 100% / 88%</dt>
                  <dd>
                    {Math.round(data.risk_at_100 * 100)}% / {Math.round(data.risk_at_88 * 100)}%
                  </dd>
                </div>
                <div>
                  <dt>Energy delta (full derate)</dt>
                  <dd>{data.energy_delta_eur_day.toFixed(2)} €/day</dd>
                </div>
                <div>
                  <dt>Cooling margin</dt>
                  <dd>
                    {data.cooling_margin_pct}%
                    {data.cooling_safe_flow_m3h != null ? ` · safe flow ${data.cooling_safe_flow_m3h} m³/h` : ""}
                  </dd>
                </div>
              </dl>
            </details>
          </section>
        </div>
      )}
    </div>
  );
}
