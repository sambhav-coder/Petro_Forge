import type { DataSummary, OptimizeResponse, TwinSnapshot, WellsResponse, WellTelemetry } from "./types";

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

export const api = {
  health: () => request<{ problem_id: string; version: string }>("/"),
  wells: () => request<WellsResponse>("/api/v1/wells"),
  well: (id: string) =>
    request<WellTelemetry>(`/api/v1/wells/${encodeURIComponent(id)}`),
  twin: (id: string) =>
    request<TwinSnapshot>(`/api/v1/wells/${encodeURIComponent(id)}/twin`),
  optimize: (id: string) =>
    request<OptimizeResponse>(`/api/v1/wells/${encodeURIComponent(id)}/optimize`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  dataSummary: () => request<DataSummary>(`/api/v1/data/summary`),
  ingestDemo: (wellId: string) =>    request<unknown>(`/api/v1/telemetry/ingest`, {
      method: "POST",
      body: JSON.stringify({
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
      }),
    }),
};
