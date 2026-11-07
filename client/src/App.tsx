import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAlerts, fetchAssets, fetchFleetSummary, fetchHealth } from "./api/client";
import { CockpitView } from "./components/CockpitView";
import { FleetView, StatusBadge } from "./components/FleetView";
import { Icon } from "./components/Icon";
import { LoadingBlock } from "./components/LoadingBlock";
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
  const [reloadKey, setReloadKey] = useState(0);
  const [helpOpen, setHelpOpen] = useState(false);
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
            <img className="brand-mark" src="/logo/zerofault_mark.svg" alt="" width={36} height={36} />
            <span>
              <strong>ZeroFault</strong>
              <small>Predictive Asset Intelligence</small>
            </span>
          </button>

          <div className="topbar-status">
            <div className="help-wrap">
              <button
                type="button"
                className={`icon-btn ${helpOpen ? "active" : ""}`}
                onClick={() => setHelpOpen((v) => !v)}
                aria-label="How to read this page"
                title="How to read this page"
                aria-expanded={helpOpen}
              >
                <Icon name="help" size={16} />
              </button>
              {helpOpen && (
                <div className="help-popover" role="dialog" aria-label="How to read this page">
                  <div className="help-popover-head">
                    <strong>How to read this page</strong>
                    <button type="button" className="link-btn" onClick={() => setHelpOpen(false)}>
                      Close
                    </button>
                  </div>
                  <ul>
                    <li>
                      <StatusBadge severity="act_now" /> The pump could break soon. Act today.
                    </li>
                    <li>
                      <StatusBadge severity="attention" /> Something is wearing out. Plan a check in the next few days.
                    </li>
                    <li>
                      <StatusBadge severity="sensor" /> The pump is fine, but a measuring sensor is giving wrong readings.
                    </li>
                    <li>
                      <StatusBadge severity="ok" /> Everything is normal.
                    </li>
                    <li>
                      <strong>Health</strong> is a simple 0–100% score. Higher is better.
                    </li>
                  </ul>
                </div>
              )}
            </div>
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
              onDiagnose={(id) => openPump(id, "diagnose")}
              onPredict={(id) => openPump(id, "predict")}
            />
          ))}

        {screen === "cockpit" && (
          <CockpitView
            assetId={selectedAsset}
            asset={selected}
            alert={selectedAlert}
            assetAlerts={alerts.filter((a) => a.asset_id === selectedAsset)}
            mode={cockpitMode}
            onModeChange={setCockpitMode}
            onBack={() => setScreen("fleet")}
            demoFallback={source === "demo"}
          />
        )}
      </main>

      <footer className="footer">
        <Icon name="shield" size={14} />
        This app only watches the pumps. It never changes any pump settings.
      </footer>
    </div>
  );
}
