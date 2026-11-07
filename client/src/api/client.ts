import type {
  AlertPrediction,
  AlertSeverity,
  AnalysisRun,
  AssetStatus,
  CockpitResponse,
  FaultGuideEntry,
  FleetSummary,
  HealthResponse,
  ModelInfo,
  ScorecardResponse,
} from "../types/alerts";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

/** HTTP error carrying the server's human-readable `detail` (FastAPI) when present */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  const body = await res.text();
  let detail = body;
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") detail = parsed.detail;
    else if (Array.isArray(parsed.detail)) {
      detail = parsed.detail
        .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg ?? ""}`)
        .join("; ");
    }
  } catch {
    /* not JSON: keep the raw text */
  }
  return new ApiError(res.status, detail || `${res.status} ${res.statusText}`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) throw await errorFrom(res);
  return res.json() as Promise<T>;
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/health", { signal });
}

export function fetchAlerts(
  assetId?: string,
  severities: AlertSeverity[] = [],
  signal?: AbortSignal,
): Promise<AlertPrediction[]> {
  const params = new URLSearchParams();
  if (assetId) params.set("asset_id", assetId);
  for (const severity of severities) params.append("severity", severity);
  const qs = params.size ? `?${params.toString()}` : "";
  return request<AlertPrediction[]>(`/api/alerts${qs}`, { signal });
}

export function fetchAssets(signal?: AbortSignal): Promise<AssetStatus[]> {
  return request<AssetStatus[]>("/api/assets", { signal });
}

export function fetchFleetSummary(signal?: AbortSignal): Promise<FleetSummary> {
  return request<FleetSummary>("/api/fleet/summary", { signal });
}

export function fetchCockpit(assetId: string, signal?: AbortSignal): Promise<CockpitResponse> {
  return request<CockpitResponse>(`/api/cockpit/${encodeURIComponent(assetId)}`, { signal });
}

export function fetchScorecard(signal?: AbortSignal): Promise<ScorecardResponse> {
  return request<ScorecardResponse>("/api/scorecard", { signal });
}

export function fetchFaultGuide(signal?: AbortSignal): Promise<FaultGuideEntry[]> {
  return request<FaultGuideEntry[]>("/api/fault-guide", { signal });
}

export function fetchModelInfo(signal?: AbortSignal): Promise<ModelInfo> {
  return request<ModelInfo>("/api/model", { signal });
}

/** The run the dashboard is showing; null before any run exists */
export async function fetchLatestAnalysis(signal?: AbortSignal): Promise<AnalysisRun | null> {
  try {
    return await request<AnalysisRun>("/api/analyses/latest", { signal });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/** Upload pump data and run the model; the new run becomes the dashboard's data */
export function createAnalysis(form: FormData, signal?: AbortSignal): Promise<AnalysisRun> {
  return request<AnalysisRun>("/api/analyses", { method: "POST", body: form, signal });
}

export function analysisAlertsCsvUrl(runId: string): string {
  return `${API_BASE}/api/analyses/${encodeURIComponent(runId)}/alerts.csv`;
}
