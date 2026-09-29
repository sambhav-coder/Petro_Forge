import type {
  AlertsResponse,
  AnalyticsResponse,
  CyclePlanResponse,
  CycleResponse,
  DataSummary,
  DynacardResponse,
  FieldOverview,
  HistoryPoint,
  LiveStatus,
  OptimizeResponse,
  PredictResponse,
  ScenarioOverrides,
  SimulateResponse,
  TwinSnapshot,
  WellsResponse,
  WellTelemetry,
} from "./types";

export function apiBase(): string {
  const raw =
    process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  return raw.replace(/\/$/, "");
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
  optimize: (id: string) => request<OptimizeResponse>(`${well(id)}/optimize`, post()),
  simulate: (id: string, overrides: ScenarioOverrides) =>
    request<SimulateResponse>(`${well(id)}/simulate`, post(overrides)),
  cycle: (id: string) => request<CycleResponse>(`${well(id)}/cycle`),
  cyclePlan: (id: string) => request<CyclePlanResponse>(`${well(id)}/cycle/plan`, post()),
  dynacard: (id: string) => request<DynacardResponse>(`${well(id)}/dynacard`),
  predict: (id: string) => request<PredictResponse>(`${well(id)}/predict`),
  history: (id: string, limit = 240) =>
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
};
