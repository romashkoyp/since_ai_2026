import type { AlertPrediction, AssetStatus, HealthResponse } from "../types/alerts";

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

export function fetchAlerts(assetId?: string): Promise<AlertPrediction[]> {
  const qs = assetId ? `?asset_id=${encodeURIComponent(assetId)}` : "";
  return getJson<AlertPrediction[]>(`/api/alerts${qs}`);
}

export function fetchAssets(): Promise<AssetStatus[]> {
  return getJson<AssetStatus[]>("/api/assets");
}
