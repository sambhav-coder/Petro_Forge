import type {
  AlertsResponse,
  AnalyticsResponse,
  CyclePlanResponse,
  CycleResponse,
  MultiCycleResponse,
  DataSummary,
  DynacardResponse,
  FieldOverview,
  HistoryPoint,
  HistoryResponse,
  HybridTwinResponse,
  LiveStatus,
  MLAnomalyRequest,
  MLAnomalyResult,
  MLFailureRequest,
  MLFailureResult,
  MLForecastRequest,
  MLForecastResult,
  MLHealthRequest,
  MLHealthResult,
  MLStatus,
  OptimizeResponse,
  PredictResponse,
  ScenarioOverrides,
  SimulateResponse,
  TwinSnapshot,
  WellCoverageSummary,
  WellsResponse,
  WellTelemetry,
} from "./types";

export const LOCAL_API_FALLBACK = "http://127.0.0.1:8000";

function isLocalHostname(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

/** Resolve the backend base URL.
 *
 * NEXT_PUBLIC_API_BASE_URL is public configuration (not a secret) and must
 * be set in production (Vercel). A localhost fallback applies ONLY when the
 * page itself runs on localhost, so a misconfigured production build fails
 * loudly instead of silently calling a developer machine.
 */
export function apiBase(): string {
  const raw = (process.env.NEXT_PUBLIC_API_BASE_URL || "").trim();
  if (raw) return raw.replace(/\/$/, "");
  if (typeof window !== "undefined" && isLocalHostname(window.location.hostname)) {
    return LOCAL_API_FALLBACK;
  }
  throw new Error(
    "NEXT_PUBLIC_API_BASE_URL is not configured: set it to the backend base URL " +
      "(production: https://petro-forge.onrender.com). Refusing localhost fallback outside local development."
  );
}

/** Non-throwing label for status/error UI. Never used for requests. */
export function apiBaseLabel(): string {
  try {
    return apiBase();
  } catch {
    return "unconfigured backend (set NEXT_PUBLIC_API_BASE_URL)";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep status text */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return (await res.json()) as T;
}

const well = (id: string) => `/api/v1/wells/${encodeURIComponent(id)}`;
const post = (body: unknown = {}): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<{ problem_id: string; version: string }>("/"),
  wells: () => request<WellsResponse>("/api/v1/wells"),
  well: (id: string) => request<WellTelemetry>(well(id)),
  twin: (id: string) => request<TwinSnapshot>(`${well(id)}/twin`),
  hybridTwin: (id: string) => request<HybridTwinResponse>(`${well(id)}/twin/hybrid`),
  optimize: (id: string) => request<OptimizeResponse>(`${well(id)}/optimize`, post()),
  simulate: (id: string, overrides: ScenarioOverrides) =>
    request<SimulateResponse>(`${well(id)}/simulate`, post(overrides)),
  cycle: (id: string) => request<CycleResponse>(`${well(id)}/cycle`),
  cyclePlan: (id: string) => request<CyclePlanResponse>(`${well(id)}/cycle/plan`, post()),
  cycleMulti: (id: string, cycles = 3) =>
    request<MultiCycleResponse>(`${well(id)}/cycle/multi`, post({ cycles })),
  dynacard: (id: string) => request<DynacardResponse>(`${well(id)}/dynacard`),
  predict: (id: string) => request<PredictResponse>(`${well(id)}/predict`),
  wellHistory: (id: string, limit = 240) =>
    request<{ well_id: string; count: number; points: HistoryPoint[] }>(
      `${well(id)}/history?limit=${limit}`
    ),
  analytics: (id: string) => request<AnalyticsResponse>(`${well(id)}/analytics`),
  alerts: (limit = 50) => request<AlertsResponse>(`/api/v1/alerts?limit=${limit}`),
  ackAlert: (alertId: string) =>
    request<unknown>(`/api/v1/alerts/${encodeURIComponent(alertId)}/ack`, post()),
  overview: () => request<FieldOverview>(`/api/v1/field/overview`),
  seedField: (days = 45) => request<unknown>(`/api/v1/demo/seed`, post({ days })),
  liveStart: (intervalS = 2) => request<LiveStatus>(`/api/v1/live/start`, post({ interval_s: intervalS })),
  liveStop: () => request<LiveStatus>(`/api/v1/live/stop`, post()),
  streamUrl: () => `${apiBase()}/api/v1/stream`,
  dataSummary: () => request<DataSummary>(`/api/v1/data/summary`),
  ingestDemo: (wellId: string) =>
    request<unknown>(`/api/v1/telemetry/ingest`, post({
      well_id: wellId,
      reservoir_temperature_c: 47.0,
      reservoir_pressure_bar: 28.5,
      api_gravity: 18.0,
      wellhead_pressure_bar: 12.0,
      oil_rate_bopd: 22.5,
      steam_volume_t: 850.0,
      steam_injection_pressure_bar: 65.0,
      soak_time_h: 48.0,
      css_phase: "PRODUCTION",
      spm: 5.0,
      stroke_in: 96.0,
      vfd_percent: 55.0,
      water_cut_percent: 35.0,
    })),
  history: (params: {
    well_id?: string;
    include_derived?: boolean;
    include_synthetic?: boolean;
    include_live?: boolean;
    limit?: number;
  }) => request<HistoryResponse>(`/api/v1/history?${new URLSearchParams(params as Record<string, string>).toString()}`),
  historyCoverage: (wellId: string) => request<WellCoverageSummary>(`/api/v1/history/coverage/${encodeURIComponent(wellId)}`),
  
  // Priority 3: ML Intelligence API
  mlStatus: () => request<MLStatus>("/api/v1/ml/status"),
  mlForecast: (body: MLForecastRequest) =>
    request<MLForecastResult>("/api/v1/ml/forecast", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  mlAnomaly: (body: MLAnomalyRequest) =>
    request<MLAnomalyResult>("/api/v1/ml/anomaly", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  mlHealth: (body: MLHealthRequest) =>
    request<MLHealthResult>("/api/v1/ml/srp-health", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  mlFailure: (body: MLFailureRequest) =>
    request<MLFailureResult>("/api/v1/ml/failure-risk", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
