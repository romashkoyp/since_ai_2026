interface Props {
  values: number[];
  threshold?: number | null;
  label: string;
  unit: string;
}

function trendNote(values: number[], threshold?: number | null): { text: string; tone: "bad" | "warn" | "ok" } {
  const first = values[0];
  const last = values[values.length - 1];
  if (threshold == null) {
    return Math.abs(last - first) / (Math.abs(first) || 1) > 0.1
      ? { text: "Changing", tone: "warn" }
      : { text: "Steady", tone: "ok" };
  }
  const startedAbove = first > threshold;
  const nowAbove = last > threshold;
  if (startedAbove !== nowAbove) return { text: "Crossed the safe limit", tone: "bad" };
  if (Math.abs(last - threshold) < Math.abs(first - threshold)) {
    return { text: "Moving toward the limit", tone: "warn" };
  }
  return { text: "Within normal range", tone: "ok" };
}

export function Sparkline({ values, threshold, label, unit }: Props) {
  if (!values.length) return null;

  const w = 320;
  const h = 96;
  const pad = 8;
  const min = Math.min(...values, threshold ?? values[0]);
  const max = Math.max(...values, threshold ?? values[0]);
  const span = max - min || 1;
  const y = (v: number) => h - pad - ((v - min) / span) * (h - pad * 2);
  const x = (i: number) => (i / Math.max(values.length - 1, 1)) * w;

  const line = values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const area = `0,${h} ${line} ${w},${h}`;
  const thrY = threshold == null ? null : y(threshold);
  const note = trendNote(values, threshold);
  const last = values[values.length - 1];

  return (
    <figure className="trend">
      <figcaption className="trend-head">
        <span className="trend-label">{label}</span>
        <span className="trend-value">
          {last.toFixed(1)} <small>{unit}</small>
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${w} ${h}`} className="trend-svg" preserveAspectRatio="none" role="img" aria-label={`${label}: ${note.text}`}>
        <polygon points={area} className={`trend-area tone-${note.tone}`} />
        {thrY != null && <line x1="0" y1={thrY} x2={w} y2={thrY} className="trend-limit" />}
        <polyline points={line} className={`trend-line tone-${note.tone}`} fill="none" />
        <circle cx={x(values.length - 1)} cy={y(last)} r="4" className={`trend-dot tone-${note.tone}`} />
      </svg>
      <div className="trend-foot">
        <span className={`trend-note tone-${note.tone}`}>{note.text}</span>
        {threshold != null && (
          <span className="trend-legend">
            <span className="limit-swatch" aria-hidden /> Safe limit {threshold} {unit}
          </span>
        )}
      </div>
    </figure>
  );
}
