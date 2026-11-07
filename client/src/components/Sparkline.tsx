interface Props {
  values: number[];
  threshold?: number | null;
  label: string;
  unit: string;
}

export function Sparkline({ values, threshold, label, unit }: Props) {
  if (!values.length) return null;

  const w = 220;
  const h = 56;
  const min = Math.min(...values, threshold ?? values[0]);
  const max = Math.max(...values, threshold ?? values[0]);
  const span = max - min || 1;

  const coords = values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * w;
      const y = h - ((v - min) / span) * (h - 8) - 4;
      return `${x},${y}`;
    })
    .join(" ");

  const thrY =
    threshold == null ? null : h - ((threshold - min) / span) * (h - 8) - 4;

  return (
    <div className="spark">
      <div className="spark-head">
        <span>{label}</span>
        <strong>
          {values[values.length - 1].toFixed(1)} {unit}
        </strong>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="spark-svg" aria-hidden>
        {thrY != null && (
          <line x1="0" y1={thrY} x2={w} y2={thrY} className="spark-thr" />
        )}
        <polyline points={coords} className="spark-line" fill="none" />
      </svg>
    </div>
  );
}
