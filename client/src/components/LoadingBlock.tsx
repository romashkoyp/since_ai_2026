interface Props {
  label?: string;
  variant?: "overview" | "pump" | "value";
}

/** Skeleton that mirrors page layout so content does not jump when data arrives. */
export function LoadingBlock({ label = "Loading…", variant = "overview" }: Props) {
  return (
    <div className="skeleton-page" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      <p className="skeleton-label">
        <span className="spinner" aria-hidden />
        {label}
      </p>
      {variant === "overview" && (
        <>
          <div className="sk sk-hero" />
          <div className="sk-row">
            <div className="sk sk-card" />
            <div className="sk sk-card" />
            <div className="sk sk-card" />
          </div>
          <div className="sk-grid">
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="sk sk-tile" />
            ))}
          </div>
        </>
      )}
      {variant === "pump" && (
        <>
          <div className="sk sk-hero" />
          <div className="sk-row two">
            <div className="sk sk-panel" />
            <div className="sk sk-panel" />
          </div>
        </>
      )}
      {variant === "value" && (
        <div className="sk-row">
          <div className="sk sk-panel" />
          <div className="sk sk-panel" />
          <div className="sk sk-panel" />
        </div>
      )}
    </div>
  );
}
