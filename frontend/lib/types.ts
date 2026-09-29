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
  days_in_phase: number;
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
  estimated_liquid_production_bpd: number;
  estimated_water_production_bwpd: number;
  water_cut_percent: number;
  estimated_pump_fillage: number;
  vfd_setpoint_percent: number;
  days_in_phase: number;
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
  vfd_setpoint_percent: number | null;
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

export type SnapshotDelta = OptimizeResponse["delta"];

export interface ScenarioOverrides {
  steam_volume_t?: number;
  steam_injection_pressure_bar?: number;
  soak_time_h?: number;
  spm?: number;
  stroke_in?: number;
  vfd_percent?: number;
  water_cut_percent?: number;
  days_in_phase?: number;
  css_phase?: string;
}

export interface SimulateResponse {
  well_id: string;
  mode: string;
  scenario_inputs: ScenarioInputs;
  current: TwinSnapshot;
  scenario: TwinSnapshot;
  delta: SnapshotDelta;
  prototype_disclaimer: string;
}

/* ---- Block 4: CSS cycle ---- */
export interface CyclePoint {
  day: number;
  phase: "INJECTION" | "SOAK" | "PRODUCTION";
  oil_rate_bopd: number;
  temperature_c: number | null;
  viscosity_cp: number | null;
  cum_oil_bbl: number;
}

export interface CycleResponse {
  well_id: string;
  injection_days: number;
  soak_days: number;
  cold_oil_rate_bopd: number;
  peak_oil_rate_bopd: number;
  optimal_cutoff_production_day: number;
  thermal_benefit_limit_day: number | null;
  cycle_length_days: number;
  cycle_oil_bbl: number;
  incremental_oil_bbl: number;
  average_cycle_rate_bopd: number;
  cycle_sor_t_per_bbl: number | null;
  cycle_sor_cwe: number | null;
  cutoff_rate_bopd: number;
  series: CyclePoint[];
  explanation: string;
}

export interface CycleCandidate {
  steam_volume_t: number;
  soak_time_h: number;
  optimal_cutoff_production_day: number;
  cycle_length_days: number;
  average_cycle_rate_bopd: number;
  cycle_oil_bbl: number;
  incremental_oil_bbl: number;
  cycle_sor_cwe: number | null;
  feasible: boolean;
}

export interface CyclePlanResponse {
  well_id: string;
  sor_limit_cwe: number;
  current: Omit<CycleResponse, "series">;
  recommended: CycleCandidate;
  average_rate_gain_bopd: number;
  candidates: CycleCandidate[];
  candidates_evaluated: number;
  explanation: string;
}

/* ---- Block 4: SRP dynacard ---- */
export interface Diagnosis {
  code: string;
  severity: "LOW" | "MODERATE" | "HIGH";
  detail: string;
}

export interface DynacardResponse {
  well_id: string;
  points: { position_in: number; load_lb: number }[];
  stroke_in: number;
  spm: number;
  pump_depth_m: number;
  fluid_sg: number;
  rod_weight_lb: number;
  buoyant_rod_weight_lb: number;
  fluid_load_lb: number;
  tubing_mean_temperature_c: number;
  tubing_viscosity_cp: number;
  viscous_drag_lb: number;
  pprl_lb: number;
  mprl_lb: number;
  goodman_loading_percent: number;
  polished_rod_hp: number;
  estimated_pump_fillage: number;
  diagnosis: Diagnosis[];
  primary_diagnosis: string;
}

/* ---- Block 4: ML ---- */
export interface Driver {
  feature: string;
  label: string;
  value: number;
  contribution_log_odds: number;
  direction: string;
}

export interface Prediction {
  probability: number;
  risk_band: "LOW" | "MODERATE" | "HIGH";
  horizon_days: number;
  top_drivers: Driver[];
}

export interface ModelCard {
  name: string;
  label: string;
  type: string;
  horizon_days: number;
  coefficients: Record<string, number>;
  metrics: {
    holdout_samples: number;
    holdout_positive_rate: number;
    auc: number | null;
    oracle_auc: number | null;
    accuracy_at_0_5: number;
    brier_score: number;
  };
}

export interface PredictResponse {
  well_id: string;
  predictions: Record<"rod_failure" | "pump_unsetting", Prediction>;
  features: Record<string, number>;
  dynacard_diagnosis: string;
  model_info: {
    training_samples: number;
    holdout_samples: number;
    label_source: string;
    data_statement: string;
    models: ModelCard[];
  };
}

/* ---- Block 4: history + analytics ---- */
export interface HistoryPoint {
  timestamp: string;
  css_phase: string;
  days_in_phase: number;
  oil_rate_bopd: number;
  wellhead_pressure_bar: number;
  reservoir_pressure_bar: number;
  spm: number;
  twin_oil_bopd: number;
  twin_temperature_c: number;
  pump_fillage: number;
  rod_failure_prob: number;
  pump_unsetting_prob: number;
}

export interface Anomaly {
  timestamp: string;
  metric: string;
  type: "STATISTICAL_OUTLIER" | "TWIN_DIVERGENCE";
  value: number;
  baseline_median: number;
  z_score: number | null;
  detail: string;
}

export interface AnalyticsResponse {
  well_id: string;
  summary: {
    readings?: number;
    production_readings?: number;
    mean_oil_rate_bopd?: number | null;
  };
  calibration: {
    status: "CALIBRATED" | "INSUFFICIENT_DATA";
    points: number;
    k: number;
    r2: number | null;
    mape_percent: number | null;
    uncalibrated_mape_percent?: number | null;
    outliers_excluded?: number;
    explanation: string;
  };
  anomalies: Anomaly[];
  decline: {
    status: "FITTED" | "INSUFFICIENT_DATA";
    decline_percent_per_month?: number;
    r2?: number | null;
    forecast: { day_ahead: number; oil_rate_bopd: number }[];
    forecast_cum_oil_bbl?: number;
    explanation: string;
  };
  calibrated_twin_oil_bopd: number;
  uncalibrated_twin_oil_bopd: number;
}

/* ---- Block 4: real-time ---- */
export interface Alert {
  alert_id: string;
  well_id: string;
  timestamp: string;
  type: string;
  severity: "HIGH" | "MODERATE" | "LOW";
  title: string;
  detail: string;
  acknowledged: boolean;
  active: boolean;
}

export interface AlertsResponse {
  total: number;
  unacknowledged: number;
  alerts: Alert[];
}

export interface LiveStatus {
  running: boolean;
  interval_s: number;
  ticks: number;
  sim_clock: string | null;
  hours_per_tick: number | null;
  wells: string[];
  provenance: string;
}

export interface FieldOverview {
  total_wells: number;
  producing_wells: number;
  by_phase: Record<string, number>;
  field_oil_rate_bopd: number;
  field_calibrated_twin_oil_bopd: number;
  active_alerts: number;
  unacknowledged_alerts: number;
  live: LiveStatus;
}

export interface StreamReading {
  type: "reading";
  well_id: string;
  timestamp: string;
  css_phase: string;
  oil_rate_bopd: number;
  twin_oil_bopd: number;
  calibrated_twin_oil_bopd: number;
  overall_engineering_status: string;
  dynacard: string;
  alerts: Alert[];
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
