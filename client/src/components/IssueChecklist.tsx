import { issueRows, type IssueRow } from "../lib/issues";
import { explainFault, friendlyTime, MACHINE_ISSUE_TYPES, plainStep, SENSOR_ISSUE_TYPES } from "../lib/plain";
import type { AlertPrediction } from "../types/alerts";
import { Icon } from "./Icon";

const pct = (v: number) => `${Math.round(v * 100)}%`;
const times = (n: number) => (n === 1 ? "once" : `${n}×`);

function ModelCheck({ row }: { row: IssueRow }) {
  if (row.verdict === "pass") {
    return (
      <span className="verdict-badge pass" title="The model's call matches the real faults">
        <Icon name="check" size={13} /> Correct
      </span>
    );
  }
  if (row.verdict === "fail") {
    return (
      <span className="verdict-badge fail" title="The model's call was wrong — confidence of the wrong call">
        <Icon name="alert" size={13} /> Wrong {row.wrongConfidence != null && pct(row.wrongConfidence)}
      </span>
    );
  }
  return null;
}

function IssueItem({ row }: { row: IssueRow }) {
  const fault = explainFault(row.type);
  const latest = row.occurrences.at(-1);
  return (
    <details className={`issue-acc ${row.occurred ? "health-detected" : "health-ok"}`}>
      <summary className="issue-acc-summary">
        <span className="issue-acc-chevron" aria-hidden />
        {row.occurred ? (
          <span className="health-badge detected" title="This issue occurred on the pump">
            <Icon name="alert" size={13} /> Fail
          </span>
        ) : (
          <span className="health-badge ok" title="No issue of this type">
            <Icon name="check" size={13} /> Pass
          </span>
        )}
        <span className="issue-acc-title">{fault.title}</span>
        {row.occurred && row.confidence != null ? (
          <span className="issue-occ" title="How often it occurred · highest confidence">
            {times(row.occurrences.length)} · <strong>{pct(row.confidence)}</strong>
            <span className="issue-acc-meter" aria-hidden>
              <span className="bg-warn" style={{ width: pct(row.confidence) }} />
            </span>
          </span>
        ) : (
          <span className="issue-occ muted">No issue</span>
        )}
        <ModelCheck row={row} />
      </summary>
      <div className="issue-acc-body">
        {row.occurred ? (
          <>
            <ol className="occ-list">
              {row.occurrences.map((a, i) => (
                <li key={`${a.alert_time_utc}-${i}`}>
                  <span className="occ-time">{friendlyTime(a.alert_time_utc)}</span>
                  <strong>{pct(a.confidence)}</strong>
                  {a.correct === false && <span className="occ-wrong">wrong call</span>}
                  {a.evidence && <span className="occ-evidence">{a.evidence}</span>}
                </li>
              ))}
            </ol>
            {latest?.recommended_action && (
              <p className="issue-action">
                <Icon name="check" size={14} /> {plainStep(latest.recommended_action)}
              </p>
            )}
          </>
        ) : (
          <p className="muted">No {fault.title.toLowerCase()} on this pump. {fault.whatItMeans}</p>
        )}
        {row.verdict !== "unchecked" && <p className="issue-reason">Model check: {row.reason}</p>}
      </div>
    </details>
  );
}

function Group({ title, rows }: { title: string; rows: IssueRow[] }) {
  const failed = rows.filter((r) => r.occurred);
  return (
    <div className="issue-group">
      <h3>
        {title} <span className="muted">· {failed.length ? `${failed.length} failed` : "all pass"}</span>
      </h3>
      <div className="issue-accordion">
        {rows.map((row) => (
          <IssueItem key={row.type} row={row} />
        ))}
      </div>
    </div>
  );
}

/** Pump page: every issue type once — Fail (occurred, how often, confidence) or Pass (no issue) */
export function IssueChecklist({ alerts }: { alerts: AlertPrediction[] }) {
  const machine = issueRows(alerts, MACHINE_ISSUE_TYPES);
  const sensor = issueRows(alerts, SENSOR_ISSUE_TYPES);
  const all = [...machine, ...sensor];
  const failedTypes = all.filter((r) => r.occurred).length;
  const checked = all.some((r) => r.verdict !== "unchecked");
  const correct = all.filter((r) => r.verdict === "pass").length;

  return (
    <section className="card diagnose-panel">
      <div className="card-title-row">
        <h2>Detected issues</h2>
        <span className="progress-pill">
          {failedTypes} of {all.length} failed · {alerts.length} alert{alerts.length === 1 ? "" : "s"}
          {checked && ` · model ${correct}/${all.length} correct`}
        </span>
      </div>
      <p className="hint issue-legend">
        <strong>Fail</strong> = the issue occurred on this pump (how often, highest confidence) ·{" "}
        <strong>Pass</strong> = no issue. Open a row to see every time it happened.
        {checked && (
          <>
            {" "}
            <strong>Correct / Wrong</strong> = the model checked against the real faults.
          </>
        )}
      </p>
      <Group title="Machine issues" rows={machine} />
      <Group title="Sensor issues" rows={sensor} />
    </section>
  );
}
