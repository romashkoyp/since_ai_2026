import type { AssetStatus } from "../types/alerts";

interface Props {
  assets: AssetStatus[];
  selected: string | null;
  onSelect: (assetId: string) => void;
}

export function FleetStrip({ assets, selected, onSelect }: Props) {
  if (!assets.length) {
    return <p className="muted">No assets loaded.</p>;
  }

  return (
    <section className="fleet" aria-label="Fleet status">
      <h2>Fleet</h2>
      <ul className="fleet-grid">
        {assets.map((asset) => (
          <li key={asset.asset_id}>
            <button
              type="button"
              className={`fleet-item status-${asset.status} ${selected === asset.asset_id ? "selected" : ""}`}
              onClick={() => onSelect(asset.asset_id)}
            >
              <span className="asset-id">{asset.asset_id}</span>
              <span className="meta">
                {asset.site} · {asset.tier}
              </span>
              <span className="status-label">{asset.status.replace("_", " ")}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
