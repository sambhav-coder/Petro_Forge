/* Backend response types — mirrors project/app.py Pydantic schemas.
   Backend is the source of truth; do not duplicate physics here. */

export interface DataSummary {
  schema_version: string;
  synthetic_generator_version: string;
  store: { telemetry: number; wells: number; cycles: number };
  by_provenance: Record<string, number>;
  cataloged_sources: number;
}

export interface WellSummary {
  well_id: string;
  last_update: string | null;
  css_phase: string | null;
  oil_rate_bopd: number | null;
  spm: number | null;
  stroke_in: number | null;
  provenance: string;
  data_status: string;
}

export interface PublicWellDetail {
  well_id: string;
  data_status: string;
  provenance: string;
  field: string | null;
  reservoir: string | null;
  status: string | null;
  status_as_of: string | null;
  status_as_of_kind?: string | null;
  temporal_note?: string | null;
  source_publication_date?: string | null;
  date_precision?: string | null;
  lift_method: string | null;
  css_status: string | null;
  css_cycle_count: number | null;
  css: Array<Record<string, unknown>>;
  production: Array<Record<string, unknown>>;
  telemetry: null;
  source_id: string | null;
  confidence: string | null;
  notes: string | null;
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

/* Priority 2: Historical time-series types */
export interface HistoricalObservation {
  record_id: string;
  timestamp_start: string;
  timestamp_end: string | null;
  timestamp_precision: string;
  original_period: string;
  approximate: boolean;
  well_id: string | null;
  scope: string;
  variable: string;
  value: number | null;
  value_str: string | null;
  reported_min: number | null;
  reported_max: number | null;
  unit: string;
  value_kind: string;
  derivation: string | null;
  derived_from: string | null;
  source_id: string;
  provenance: string;
  data_status: string;
  source_publication_date: string | null;
  time_series_safe: boolean;
  ml_safe: boolean;
  data_quality: string;
  notes: string;
}

export interface HistoryCoverage {
  observation_count: number;
  temporal_coverage: string;
  has_gaps: boolean;
  duplicate_count: number;
  provenance_classes: string[];
  measured_count: number;
  derived_count: number;
  synthetic_count: number;
  insufficient_count: number;
  time_series_safe_count: number;
  ml_safe_count: number;
  precision_breakdown: Record<string, number>;
}

export interface WellCoverageSummary {
  well_id: string;
  coverage: HistoryCoverage;
  variables: Record<string, number>;
  time_series_ready: boolean;
  ml_ready: boolean;
}

export interface HistoryResponse {
  query: Record<string, unknown>;
  count: number;
  observations: HistoricalObservation[];
  coverage: HistoryCoverage;
  metadata: {
    include_derived: boolean;
    include_synthetic: boolean;
    include_live: boolean;
  };
}

export interface TrendAnalysis {
  status: "INSUFFICIENT" | "TREND_AVAILABLE";
  reason?: string;
  observation_count: number;
  numeric_count?: number;
  temporal_precision?: Set<string>;
  first_value?: number;
  last_value?: number;
  change?: number;
  change_percent?: number | null;
  direction?: string;
  min_value?: number;
  max_value?: number;
  mean_value?: number;
}
