import type {
  AlertPrediction,
  AlertSeverity,
  AnalysisJob,
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

/** Readable text for error pages produced by a proxy in front of the API (e.g. nginx HTML pages) */
function proxyMessage(status: number, statusText: string): string {
  if (status === 413) {
    return (
      "The upload is too large for the web server in front of the API (nginx client_max_body_size). " +
      "Ask the administrator to raise that limit, or upload smaller files."
    );
  }
  if (status === 502 || status === 503 || status === 504) {
    return "The API is not reachable or took too long to answer. Try again in a moment.";
  }
  return `${status} ${statusText}`.trim();
}

async function errorFrom(res: Response): Promise<ApiError> {
  const body = await res.text();
  const isHtml = (res.headers.get("content-type") ?? "").includes("text/html") || /^\s*</.test(body);
  if (isHtml) return new ApiError(res.status, proxyMessage(res.status, res.statusText));
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

/** Upload pump data; the server checks the files and queues the model run (answers 202 with a job) */
export function submitAnalysis(form: FormData, signal?: AbortSignal): Promise<AnalysisJob> {
  return request<AnalysisJob>("/api/analyses", { method: "POST", body: form, signal });
}

export function fetchAnalysisJob(jobId: string, signal?: AbortSignal): Promise<AnalysisJob> {
  return request<AnalysisJob>(`/api/analyses/jobs/${encodeURIComponent(jobId)}`, { signal });
}

const POLL_MS = 1500;
const MAX_WAIT_MS = 30 * 60 * 1000;

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

/**
 * Upload pump data and wait for the model run; the new run becomes the dashboard's data.
 * The run happens in the background on the server, so a slow analysis cannot hit a proxy timeout.
 * `onProgress` gets every job update (queued -> running -> completed / failed).
 */
export async function createAnalysis(
  form: FormData,
  signal?: AbortSignal,
  onProgress?: (job: AnalysisJob) => void,
): Promise<AnalysisRun> {
  let job = await submitAnalysis(form, signal);
  const started = Date.now();
  for (;;) {
    onProgress?.(job);
    if (job.status === "completed" && job.run) return job.run;
    if (job.status === "failed") throw new ApiError(job.error_status ?? 500, job.error ?? "The analysis failed.");
    if (Date.now() - started > MAX_WAIT_MS) throw new ApiError(504, "The analysis is taking unusually long. Refresh the page later to see if it finished.");
    await wait(POLL_MS, signal);
    job = await fetchAnalysisJob(job.job_id, signal);
  }
}

export function analysisAlertsCsvUrl(runId: string): string {
  return `${API_BASE}/api/analyses/${encodeURIComponent(runId)}/alerts.csv`;
}
