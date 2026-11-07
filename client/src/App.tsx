import { useEffect, useState } from "react";
import { fetchAlerts, fetchAssets, fetchHealth } from "./api/client";
import type { AlertPrediction, AssetStatus } from "./types/alerts";
import { AlertList } from "./components/AlertList";
import { FleetStrip } from "./components/FleetStrip";

export default function App() {
  const [alerts, setAlerts] = useState<AlertPrediction[]>([]);
  const [assets, setAssets] = useState<AssetStatus[]>([]);
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const health = await fetchHealth();
        if (!cancelled) setApiOk(health.status === "ok");

        const [alertData, assetData] = await Promise.all([
          fetchAlerts(selectedAsset ?? undefined),
          fetchAssets(),
        ]);
        if (cancelled) return;
        setAlerts(alertData);
        setAssets(assetData);
      } catch (err) {
        if (!cancelled) {
          setApiOk(false);
          setError(err instanceof Error ? err.message : "Failed to reach API");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedAsset]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-block">
          <p className="brand">Since AI</p>
          <h1>Operator Cockpit</h1>
          <p className="lede">Fleet triage for cooling-pump alerts — sample wiring to the Python API.</p>
        </div>
        <div className={`api-pill ${apiOk === true ? "ok" : apiOk === false ? "bad" : ""}`}>
          API {apiOk === null ? "…" : apiOk ? "connected" : "offline"}
        </div>
      </header>

      {error && <p className="banner error">{error}</p>}

      <FleetStrip
        assets={assets}
        selected={selectedAsset}
        onSelect={(id) => setSelectedAsset((prev) => (prev === id ? null : id))}
      />

      <section className="alerts-section">
        <div className="section-head">
          <h2>{selectedAsset ? `Alerts · ${selectedAsset}` : "Open alerts"}</h2>
          {selectedAsset && (
            <button type="button" className="text-btn" onClick={() => setSelectedAsset(null)}>
              Clear filter
            </button>
          )}
        </div>
        {loading ? <p className="muted">Loading…</p> : <AlertList alerts={alerts} />}
      </section>
    </div>
  );
}
