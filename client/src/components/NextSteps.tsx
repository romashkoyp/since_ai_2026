import { useEffect, useState } from "react";
import { fetchFaultGuide } from "../api/client";
import { issueRows } from "../lib/issues";
import { explainFault, friendlyTime, MACHINE_ISSUE_TYPES, SENSOR_ISSUE_TYPES } from "../lib/plain";
import type { AlertPrediction, FaultGuideEntry, UrgencyLevel } from "../types/alerts";
import { Icon } from "./Icon";

/** Colours and order as defined in fault_actions.json (_how_to_use) */
const URGENCY: Record<UrgencyLevel, { label: string; order: number }> = {
  act_now: { label: "Act now", order: 0 },
  within_a_day: { label: "Within a day", order: 1 },
  next_planned_stop: { label: "At the next planned stop", order: 2 },
  check_sensor: { label: "Check the sensor", order: 3 },
};

let guideCache: Promise<Record<string, FaultGuideEntry>> | null = null;

function loadGuide(): Promise<Record<string, FaultGuideEntry>> {
  guideCache ??= fetchFaultGuide()
    .then((list) => Object.fromEntries(list.map((g) => [g.fault_type, g])))
    .catch((e) => {
      guideCache = null; // allow a retry on the next visit
      throw e;
    });
  return guideCache;
}

/** "What happens next?": for every failed issue on this pump, what to do (fault_actions.json) */
export function NextSteps({ alerts }: { alerts: AlertPrediction[] }) {
  const [guide, setGuide] = useState<Record<string, FaultGuideEntry> | null>(null);
  const [failedToLoad, setFailedToLoad] = useState(false);

  useEffect(() => {
    let alive = true;
    loadGuide()
      .then((g) => alive && setGuide(g))
      .catch(() => alive && setFailedToLoad(true));
    return () => {
      alive = false;
    };
  }, []);

  const failed = issueRows(alerts, [...MACHINE_ISSUE_TYPES, ...SENSOR_ISSUE_TYPES]).filter((r) => r.occurred);
  const urgencyOf = (type: string) => guide?.[type]?.urgency_level ?? "within_a_day";
  const ordered = [...failed].sort(
    (a, b) => URGENCY[urgencyOf(a.type)].order - URGENCY[urgencyOf(b.type)].order || (b.confidence ?? 0) - (a.confidence ?? 0),
  );

  if (failed.length === 0) {
    return (
      <section className="card next-steps-empty">
        <Icon name="check" size={22} />
        <div>
          <h2>Nothing to do</h2>
          <p className="muted">No issues were found on this pump. Keep the normal watch routine.</p>
        </div>
      </section>
    );
  }

  return (
    <div className="next-steps">
      <p className="hint">
        {failed.length} issue{failed.length === 1 ? "" : "s"} failed on this pump. What to do for each, most urgent first.
      </p>
      {failedToLoad && (
        <div className="notice" role="status">
          <Icon name="help" size={18} />
          <span>The action guide could not be loaded right now, so only the issue names are shown.</span>
        </div>
      )}
      {ordered.map((row) => {
        const g = guide?.[row.type];
        const level = g?.urgency_level ?? null;
        const last = row.occurrences.at(-1);
        return (
          <section key={row.type} className={`card next-step ${level ? `urgency-${level}` : ""}`}>
            <header className="next-step-head">
              <div>
                <h2>{g?.plain_name ?? explainFault(row.type).title}</h2>
                <p className="muted next-step-meta">
                  {row.occurrences.length === 1 ? "Occurred once" : `Occurred ${row.occurrences.length}×`}
                  {last && ` · last ${friendlyTime(last.alert_time_utc)}`}
                  {row.confidence != null && ` · ${Math.round(row.confidence * 100)}% confidence`}
                </p>
              </div>
              {level && <span className={`urgency-chip urgency-${level}`}>{URGENCY[level].label}</span>}
            </header>

            <p>{g?.what_it_means ?? explainFault(row.type).whatItMeans}</p>
            {g?.urgency_text && (
              <p className="next-step-when">
                <Icon name="clock" size={15} /> {g.urgency_text}
              </p>
            )}

            {g && g.what_to_do.length > 0 && (
              <>
                <h3>What to do</h3>
                <ol className="next-step-list">
                  {g.what_to_do.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              </>
            )}

            {g?.not_to_confuse_with && (
              <p className="hint next-step-confuse">
                <Icon name="help" size={14} /> Not to confuse with: {g.not_to_confuse_with}
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}
