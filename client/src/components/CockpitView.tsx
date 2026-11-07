import { useEffect, useMemo, useState } from "react";
import { getDummyCockpit } from "../data/dummy";
import { Sparkline } from "./Sparkline";

interface Props {
  assetId: string | null;
  onBack: () => void;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function CockpitView({ assetId, onBack }: Props) {
  const data = useMemo(() => (assetId ? getDummyCockpit(assetId) : null), [assetId]);
  const [speed, setSpeed] = useState(88);

  useEffect(() => {
    if (data) setSpeed(data.sandbox_default_speed_pct);
  }, [data]);

  if (!assetId || !data) {
    return (
      <div className="screen empty-screen">
        <h2>Asset cockpit</h2>
        <p className="muted">Pick a pump from Fleet triage to inspect diagnosis, trends, and what-if derate.</p>
        <button type="button" className="primary-btn" onClick={onBack}>
          Go to fleet
        </button>
      </div>
    );
  }

  const t = (100 - speed) / 12;
  const clamped = Math.min(Math.max(t, 0), 1);
  const npsh = lerp(data.npsh_at_100, data.npsh_at_88, clamped);
  const risk = lerp(data.risk_at_100, data.risk_at_88, clamped);

  return (
    <div className="screen cockpit-screen">
      <div className="section-head">
        <div>
          <p className="eyebrow">{data.asset_id}</p>
          <h2>{data.title}</h2>
        </div>
        <button type="button" className="text-btn" onClick={onBack}>
          ← Fleet
        </button>
      </div>

      <div className="cockpit-grid">
        <section className="panel">
          <h3>Diagnosis</h3>
          <p className="diagnosis">{data.diagnosis}</p>
          <p className="meta">
            <span className={`chip class-${data.event_class.toLowerCase()}`}>{data.event_class}</span>
            <span className="conf">{Math.round(data.confidence * 100)}% confidence</span>
          </p>
          <p className="safe">{data.safe_window}</p>

          {!!data.evidence.length && (
            <>
              <h4>Evidence</h4>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>σ</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {data.evidence.map((row) => (
                    <tr key={row.channel}>
                      <td>{row.channel}</td>
                      <td className={Math.abs(row.sigma) >= 3 ? "warn-text" : ""}>
                        {row.sigma > 0 ? "+" : ""}
                        {row.sigma.toFixed(1)}
                      </td>
                      <td>{row.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <h4>SOP</h4>
          <ol className="sop">
            {data.sop.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <p className="readonly">Read-only UI · no PLC / write path</p>
        </section>

        <section className="panel">
          <h3>Trends</h3>
          {data.trends.length ? (
            data.trends.map((series) => (
              <Sparkline
                key={series.name}
                label={series.name}
                unit={series.unit}
                values={series.points.map((p) => p.value)}
                threshold={series.threshold}
              />
            ))
          ) : (
            <p className="muted">No trend series for this asset in the demo set. Try PUMP-04 or PUMP-08.</p>
          )}
        </section>

        <section className="panel">
          <h3>What-if sandbox</h3>
          <label className="slider-label" htmlFor="speed">
            VFD speed derate: <strong>{speed}%</strong>
          </label>
          <input
            id="speed"
            type="range"
            min={80}
            max={100}
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
          />
          <ul className="proj">
            <li>
              <span>NPSH margin</span>
              <strong>{npsh.toFixed(2)} m</strong>
            </li>
            <li>
              <span>Risk</span>
              <strong className={risk > 0.5 ? "warn-text" : "ok-text"}>{Math.round(risk * 100)}%</strong>
            </li>
            <li>
              <span>Energy delta</span>
              <strong>{data.energy_delta_eur_day.toFixed(1)} €/day</strong>
            </li>
            <li>
              <span>Cooling margin</span>
              <strong className="ok-text">{data.cooling_margin_pct}%</strong>
            </li>
          </ul>
          <p className="muted">Sandbox only — compares interventions without live control writes.</p>
        </section>
      </div>
    </div>
  );
}
