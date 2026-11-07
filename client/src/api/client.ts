import type {
  AlertPrediction,
  AlertSeverity,
  AssetStatus,
  CockpitResponse,
  FleetSummary,
  HealthResponse,
  ScorecardResponse,
} from "../types/alerts";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health");
}

export function fetchAlerts(assetId?: string, severities: AlertSeverity[] = []): Promise<AlertPrediction[]> {
  const params = new URLSearchParams();
  if (assetId) params.set("asset_id", assetId);
  for (const severity of severities) params.append("severity", severity);
  const qs = params.size ? `?${params.toString()}` : "";
  return getJson<AlertPrediction[]>(`/api/alerts${qs}`);
}

export function fetchAssets(): Promise<AssetStatus[]> {
  return getJson<AssetStatus[]>("/api/assets");
}

export function fetchFleetSummary(): Promise<FleetSummary> {
  return getJson<FleetSummary>("/api/fleet/summary");
}

export function fetchCockpit(assetId: string): Promise<CockpitResponse> {
  return getJson<CockpitResponse>(`/api/cockpit/${encodeURIComponent(assetId)}`);
}

export function fetchScorecard(): Promise<ScorecardResponse> {
  return getJson<ScorecardResponse>("/api/scorecard");
}
