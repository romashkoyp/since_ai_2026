import { useState } from "react";
import { CockpitView } from "./components/CockpitView";
import { FleetView } from "./components/FleetView";
import { ScorecardView } from "./components/ScorecardView";
import {
  DUMMY_ALERTS,
  DUMMY_ASSETS,
  DUMMY_SUMMARY,
} from "./data/dummy";
import type { ScreenId } from "./types/alerts";

export default function App() {
  const [screen, setScreen] = useState<ScreenId>("fleet");
  const [selectedAsset, setSelectedAsset] = useState<string | null>("PUMP-08");

  function openCockpit(assetId: string) {
    setSelectedAsset(assetId);
    setScreen("cockpit");
  }

  return (
    <div className="app-shell">
      <header className="shell-top">
        <div className="brand-block">
          <p className="brand">Since AI</p>
          <p className="product">RETROFIT operator cockpit · demo data</p>
        </div>
        <nav className="tabs" aria-label="Screens">
          <button
            type="button"
            className={screen === "fleet" ? "active" : ""}
            onClick={() => setScreen("fleet")}
          >
            Fleet triage
          </button>
          <button
            type="button"
            className={screen === "cockpit" ? "active" : ""}
            onClick={() => setScreen("cockpit")}
          >
            Asset cockpit
          </button>
          <button
            type="button"
            className={screen === "scorecard" ? "active" : ""}
            onClick={() => setScreen("scorecard")}
          >
            Retrofit scorecard
          </button>
        </nav>
        <div className="api-pill ok">Demo mode</div>
      </header>

      {screen === "fleet" && (
        <FleetView
          summary={DUMMY_SUMMARY}
          assets={DUMMY_ASSETS}
          alerts={DUMMY_ALERTS}
          selected={selectedAsset}
          onSelect={openCockpit}
        />
      )}
      {screen === "cockpit" && (
        <CockpitView assetId={selectedAsset} onBack={() => setScreen("fleet")} />
      )}
      {screen === "scorecard" && <ScorecardView />}
    </div>
  );
}
