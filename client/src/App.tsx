import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAlerts, fetchAssets, fetchFleetSummary, fetchHealth } from "./api/client";
import { CockpitView } from "./components/CockpitView";
import { FleetView } from "./components/FleetView";
import { Icon } from "./components/Icon";
import { LoadingBlock } from "./components/LoadingBlock";
import { ScorecardView } from "./components/ScorecardView";
import { DUMMY_ALERTS, DUMMY_ASSETS, DUMMY_SUMMARY } from "./data/dummy";
import type {
  AlertPrediction,
  AssetStatus,
  CockpitMode,
  FleetSummary,
  ScreenId,
} from "./types/alerts";

type Source = "live" | "demo";

export default function App() {
  const [screen, setScreen] = useState<ScreenId>("fleet");
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null);
  const [cockpitMode, setCockpitMode] = useState<CockpitMode>("diagnose");

  const [summary, setSummary] = useState<FleetSummary | null>(null);
  const [assets, setAssets] = useState<AssetStatus[]>([]);
  const [alerts, setAlerts] = useState<AlertPrediction[]>([]);
  const [source, setSource] = useState<Source | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const hasData = useRef(false);

  useEffect(() => {
    const ac = new AbortController();

    async function load() {
      if (hasData.current) setRefreshing(true);
      else setInitialLoading(true);

      try {
        const health = await fetchHealth();
        if (ac.signal.aborted) return;
        if (health.status !== "ok") throw new Error("API not ready");

        const [nextSummary, nextAssets, nextAlerts] = await Promise.all([
          fetchFleetSummary(),
          fetchAssets(),
          fetchAlerts(),
        ]);
        if (ac.signal.aborted) return;

        setSummary(nextSummary);
        setAssets(nextAssets);
        setAlerts(nextAlerts);
        setSource("live");
      } catch {
        if (ac.signal.aborted) return;
        setSummary(DUMMY_SUMMARY);
        setAssets(DUMMY_ASSETS);
        setAlerts(DUMMY_ALERTS);
        setSource("demo");
      } finally {
        if (!ac.signal.aborted) {
          hasData.current = true;
          setUpdatedAt(new Date());
          setInitialLoading(false);
          setRefreshing(false);
        }
      }
    }

    void load();
    return () => ac.abort();
  }, [reloadKey]);

  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  function openPump(assetId: string, mode: CockpitMode) {
    setSelectedAsset(assetId);
    setCockpitMode(mode);
    setScreen("cockpit");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const selected = assets.find((a) => a.asset_id === selectedAsset) ?? null;
  const selectedAlert = alerts.find((a) => a.asset_id === selectedAsset) ?? null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <button type="button" className="brand" onClick={() => setScreen("fleet")}>
            <span className="brand-mark" aria-hidden>
              <Icon name="shield" size={18} />
            </span>
            <span>
              <strong>Since AI</strong>
              <small>Pump Health Monitor</small>
            </span>
          </button>

          <nav className="nav" aria-label="Main">
            <button
              type="button"
              className={screen === "fleet" ? "active" : ""}
              onClick={() => setScreen("fleet")}
            >
              Overview
            </button>
            <button
              type="button"
              className={screen === "cockpit" ? "active" : ""}
              onClick={() => setScreen("cockpit")}
              disabled={!selectedAsset}
              title={selectedAsset ? undefined : "Pick a pump on the Overview first"}
            >
              Pump details
            </button>
            <button
              type="button"
              className={screen === "scorecard" ? "active" : ""}
              onClick={() => setScreen("scorecard")}
            >
              Savings & value
            </button>
          </nav>

          <div className="topbar-status">
            {source && (
              <span className={`source-pill ${source}`}>
                <span className="dot" aria-hidden />
                {source === "live" ? "Live data" : "Demo data"}
              </span>
            )}
            <button
              type="button"
              className="icon-btn"
              onClick={refresh}
              disabled={initialLoading || refreshing}
              aria-label="Refresh data"
              title="Refresh data"
            >
              <Icon name="refresh" size={16} className={refreshing ? "spin" : ""} />
            </button>
          </div>
        </div>
      </header>

      <main className="page">
        {source === "demo" && !initialLoading && (
          <div className="notice" role="status">
            <Icon name="help" size={18} />
            <span>
              We could not reach the live system, so you are seeing <strong>example data</strong>.
              Everything still works for a walkthrough.
            </span>
            <button type="button" className="link-btn" onClick={refresh}>
              Try again
            </button>
          </div>
        )}

        {screen === "fleet" &&
          (initialLoading ? (
            <LoadingBlock label="Checking all pumps…" variant="overview" />
          ) : (
            <FleetView
              summary={summary}
              assets={assets}
              alerts={alerts}
              updatedAt={updatedAt}
              refreshing={refreshing}
              onDiagnose={(id) => openPump(id, "diagnose")}
              onPredict={(id) => openPump(id, "predict")}
            />
          ))}

        {screen === "cockpit" && (
          <CockpitView
            assetId={selectedAsset}
            asset={selected}
            alert={selectedAlert}
            mode={cockpitMode}
            onModeChange={setCockpitMode}
            onBack={() => setScreen("fleet")}
            demoFallback={source === "demo"}
          />
        )}

        {screen === "scorecard" && <ScorecardView demoFallback={source === "demo"} />}
      </main>

      <footer className="footer">
        <Icon name="shield" size={14} />
        This app only watches the pumps. It never changes any pump settings.
      </footer>
    </div>
  );
}
