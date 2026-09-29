/* Backend response types — mirrors project/app.py Pydantic schemas.
   Backend is the source of truth; do not duplicate physics here. */

export interface WellSummary {
  well_id: string;
  last_update: string;
  css_phase: string;
  oil_rate_bopd: number;
  spm: number;
  stroke_in: number;
}

export interface WellsResponse {
  total_wells: number;
  wells: WellSummary[];
}

export interface WellTelemetry {
  well_id: string;
  timestamp: string | null;
  reservoir_temperature_c: number;
  reservoir_pressure_bar: number;
  api_gravity: number;
  wellhead_pressure_bar: number;
  oil_rate_bopd: number;
  steam_volume_t: number;
  steam_injection_pressure_bar: number;
  soak_time_h: number;
  css_phase: string;
  spm: number;
  stroke_in: number;
  vfd_percent: number;
  water_cut_percent: number;
}

export interface RiskIndicator {
  risk_level: "LOW" | "MODERATE" | "HIGH";
  risk_score: number;
  reason: string;
}

export interface TwinSnapshot {
  well_id: string;
  timestamp: string;
  css_phase: string;
  heating_intensity: number;
  baseline_reservoir_temperature_c: number;
  estimated_temperature_c: number;
  estimated_viscosity_cp: number;
  mobility_factor: number;
  reservoir_pressure_bar: number;
  wellhead_pressure_bar: number;
  drawdown_bar: number;
  estimated_reservoir_inflow_bopd: number;
  spm: number;
  stroke_in: number;
  pump_fillage: number;
  pump_efficiency: number;
  pump_theoretical_capacity_bopd: number;
  pump_capacity_bopd: number;
  estimated_oil_production_bopd: number;
  production_limiting_factor: string;
  steam_volume_t: number;
  evaluation_window_days: number;
  estimated_oil_volume_bbl: number;
  steam_oil_ratio_t_per_bbl: number | null;
  sor_status: string;
  steam_energy_kwh: number;
  pumping_energy_kwh: number;
  total_energy_kwh: number;
  energy_per_barrel_kwh: number | null;
  rod_float_risk: RiskIndicator;
  impact_risk: RiskIndicator;
  pump_unsetting_risk: RiskIndicator;
  overall_engineering_status: string;
  recommendation: string;
  explanations: Record<string, string>;
  prototype_disclaimer: string;
}

export interface ScenarioInputs {
  steam_volume_t: number;
  steam_injection_pressure_bar: number;
  soak_time_h: number;
  spm: number;
  stroke_in: number;
  css_phase: string;
}

export interface ScenarioResult {
  rank: number;
  inputs: ScenarioInputs;
  estimated_oil_production_bopd: number;
  steam_oil_ratio_t_per_bbl: number | null;
  sor_status: string;
  total_energy_kwh: number;
  rod_float_risk: RiskIndicator;
  impact_risk: RiskIndicator;
  pump_unsetting_risk: RiskIndicator;
  overall_engineering_status: string;
  score: number;
}

export interface OptimizeResponse {
  well_id: string;
  mode: string;
  current: TwinSnapshot;
  recommended: TwinSnapshot & { score: number; inputs: ScenarioInputs };
  delta: {
    production_delta_bopd: number;
    sor_delta_t_per_bbl: number | null;
    energy_delta_kwh: number;
    status_from: string;
    status_to: string;
    status_changed: boolean;
    limiting_from: string;
    limiting_to: string;
  };
  objective_score: number;
  top_scenarios: ScenarioResult[];
  why_recommended: string[];
  assumptions: string[];
  scenarios_evaluated: number;
  prototype_disclaimer: string;
}

/* Scene selection model: every interactive object maps to a twin entity.
   casing / thermal / formation are Phase 1B splits for deep exploration. */
export type ObjectKind =
  | "well"
  | "wellhead"
  | "srp"
  | "casing"
  | "tubing"
  | "rod"
  | "pump"
  | "reservoir"
  | "thermal"
  | "formation";

export type IsolatableKind = Exclude<ObjectKind, "well" | "srp">;

export type ViewMode = "NORMAL" | "CUTAWAY" | "XRAY";

export interface SceneSelection {
  kind: ObjectKind;
  wellId: string;
  label: string;
}

export type CameraPreset = "FIELD" | "WELL" | "WELLBORE" | "RESERVOIR" | "PUMP";
