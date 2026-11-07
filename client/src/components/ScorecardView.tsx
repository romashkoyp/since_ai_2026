import { useEffect, useState } from "react";
import { fetchScorecard } from "../api/client";
import { DUMMY_SCORECARD } from "../data/dummy";
import { timeLeftLabel } from "../lib/plain";
import type { ScorecardResponse } from "../types/alerts";
import { Icon } from "./Icon";
import { LoadingBlock } from "./LoadingBlock";

interface Props {
  demoFallback?: boolean;
}

function isYes(v: string): boolean {
  return v.trim().toLowerCase() === "yes";
}

function isNo(v: string): boolean {
  return v.trim().toLowerCase() === "no";
}

function humanLead(v: string): string {
  const m = /^(\d+(?:\.\d+)?)\s*h$/i.exec(v.trim());
  return m ? timeLeftLabel(Number(m[1])) ?? v : v;
}

function Cell({ value }: { value: string }) {
  if (/^\d+(?:\.\d+)?\s*h$/i.test(value.trim())) return <span>{humanLead(value)}</span>;
  if (isYes(value)) {
    return (
      <span className="yes">
        <Icon name="check" size={16} /> Yes
      </span>
    );
  }
  if (isNo(value)) return <span className="no">— No</span>;
  return <span>{value}</span>;
}

export function ScorecardView({ demoFallback = false }: Props) {
  const [data, setData] = useState<ScorecardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [usedFallback, setUsedFallback] = useState(false);

  useEffect(() => {
    const ac = new AbortController();
    setLoading(true);
    setUsedFallback(false);

    async function load() {
      try {
        const next = demoFallback ? DUMMY_SCORECARD : await fetchScorecard();
        if (ac.signal.aborted) return;
        setData(next);
      } catch {
        if (ac.signal.aborted) return;
        setData(DUMMY_SCORECARD);
        setUsedFallback(!demoFallback);
      } finally {
        if (!ac.signal.aborted) setLoading(false);
      }
    }

    void load();
    return () => ac.abort();
  }, [demoFallback]);

  if (loading || !data) {
    return <LoadingBlock label="Working out the numbers…" variant="value" />;
  }

  const kitCost = data.hardware_bom.reduce((s, r) => s + r.eur, 0);
  const caughtPct = Math.round(data.event_f1 * 100);
  const correctPct = Math.round(data.precision * 100);
  const typePct = Math.round(data.fault_type_recall * 100);
  const leadRow = data.t0_vs_t1.find((r) => /lead time/i.test(r.capability));

  return (
    <div className="value-page">
      {usedFallback && (
        <div className="notice" role="status">
          <Icon name="help" size={18} />
          <span>Live numbers are not available right now. Showing example numbers.</span>
        </div>
      )}

      <section className="hero sev-ok">
        <div className="hero-icon">
          <Icon name="euro" size={28} />
        </div>
        <div className="hero-text">
          <h1>Pays for itself by preventing just one breakdown</h1>
          <p>
            Adding a few small sensors costs about <strong>€{kitCost} per pump</strong> and takes under an hour to fit. No
            changes to the existing control system.
          </p>
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>Can we trust the warnings?</h2>
          <p>Tested against recorded real-world problems</p>
        </div>
        <div className="stat-grid">
          <article className="big-stat">
            <span className="big-stat-num">{caughtPct}%</span>
            <span className="big-stat-label">overall detection accuracy</span>
          </article>
          <article className="big-stat">
            <span className="big-stat-num">{correctPct}%</span>
            <span className="big-stat-label">of warnings were correct</span>
          </article>
          <article className="big-stat">
            <span className="big-stat-num">{data.false_alarms}</span>
            <span className="big-stat-label">false alarms</span>
          </article>
          <article className="big-stat">
            <span className="big-stat-num">{typePct}%</span>
            <span className="big-stat-label">correctly named the exact problem</span>
          </article>
        </div>
        <p className="hint">
          Overall test score: <strong>{data.composite_score} out of 100</strong>
          {leadRow && (
            <>
              {" "}
              · Warns <strong>{humanLead(leadRow.t1)}</strong> ahead instead of {humanLead(leadRow.t0)}
            </>
          )}
        </p>
      </section>

      <div className="grid-2">
        <section className="card">
          <h2>What the upgrade adds</h2>
          <table className="compare">
            <thead>
              <tr>
                <th>Can it…</th>
                <th>Today</th>
                <th>With upgrade</th>
              </tr>
            </thead>
            <tbody>
              {data.t0_vs_t1.map((row) => (
                <tr key={row.capability}>
                  <td>{row.capability}</td>
                  <td>
                    <Cell value={row.t0} />
                  </td>
                  <td className="highlight">
                    <Cell value={row.t1} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card">
          <h2>Cost and payback</h2>
          <ul className="kv">
            {data.economics.map((row) => (
              <li key={row.metric}>
                <span>{row.metric}</span>
                <strong>{row.value}</strong>
              </li>
            ))}
          </ul>

          <h3>What goes on each pump</h3>
          <ul className="kv">
            {data.hardware_bom.map((row) => (
              <li key={row.item}>
                <span>{row.item}</span>
                <strong>€{row.eur}</strong>
              </li>
            ))}
            <li className="total">
              <span>Total per pump</span>
              <strong>€{kitCost}</strong>
            </li>
          </ul>
          <p className="hint">
            <Icon name="shield" size={14} /> Clip-on sensors only. Safely separated from the ship&apos;s control system.
          </p>
        </section>
      </div>
    </div>
  );
}
