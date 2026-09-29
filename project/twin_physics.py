"""SIH26120 Digital Twin — deterministic engineering/physics foundation (Block 2).

=====================================================================
ENGINEERING DOCUMENTATION (prototype/demo assumptions)
=====================================================================
This module is a TRANSPARENT HACKATHON PROTOTYPE, not a field-calibrated
simulator. Every coefficient below is a prototype/demo assumption UNLESS
marked [FROM-PS] (taken directly from the SIH problem statement text).

1. TEMPERATURE MODEL (bounded first-order thermal response)
   Heating:   T = T_base + DT_MAX_C * I * (1 - exp(-t / TAU_H))
   Cooling:   T = T_base + (T_peak - T_base) * exp(-t / TAU_H)
   - T_base comes from the well input (reservoir_temperature_c).
   - I (heating intensity, 0..1) blends normalized steam volume and
     steam injection pressure against reference values.
   - The snapshot uses soak_time_h as the representative thermal
     exposure duration (documented prototype choice). IDLE phase applies
     the cooling branch so post-steam cooldown is representable.
   - Output is clamped to [0, 350] C. No random terms.

2. VISCOSITY MODEL (Arrhenius-style, numerically clamped)
   mu(T) = MU_REF_CP * exp(B * (1/(T+273.15) - 1/(T_REF_C+273.15)))
   - MU_REF_CP / T_REF_C: reference viscosity/temperature anchor.
     T_REF_C = 47 C is [FROM-PS] (Baghewala 46-48 C); MU_REF_CP is a
     prototype heavy-oil assumption.
   - API gravity adjusts the estimate linearly around API_REF = 18
     [FROM-PS] (17-19 API): factor = 1 - 0.01*(api - 18), clamped to
     [0.7, 1.3]. Lighter oil (higher API) -> slightly lower viscosity.
   - Exponent clamped to [-10, 10]; result clamped to [0.1, 100000] cP,
     always positive. Units: centipoise.

3. MOBILITY (normalized proxy)
   mobility = MU_REF_CP / mu. Equals 1 at reference viscosity; rises as
   oil thins, falls as oil thickens. Always non-negative.

4. INFLOW (simplified IPR)
   q_inflow = J * max(P_res - P_wh, 0) * mobility, capped at 5000 bopd.
   - Higher drawdown -> higher inflow; P_res <= P_wh -> zero (never
     negative); higher viscosity (lower mobility) -> lower inflow.
   - J (productivity index) is a prototype assumption. Units: bopd.

5. SRP PUMP CAPACITY (positive-displacement proxy)
   Q_theoretical = (pi/4 * D^2) * stroke * SPM * 1440 / 9702  [bopd]
   Q_actual = Q_theoretical * fillage * efficiency
   - D (pump diameter) is a prototype assumption (documented below).
   - fillage, efficiency in [0, 1] (clamped); defaults are prototype
     assumptions used when no measured fillage is available.
   - 1440 min/day, 9702 in^3 per barrel. Output never negative.

6. PRODUCTION COUPLING
   production = min(reservoir_inflow, pump_actual_capacity).
   The well can only produce what the reservoir delivers AND what the
   pump can lift; the lower of the two binds. A limiting-factor label
   (INFLOW_LIMITED / PUMP_LIMITED) records which side bound.

7. SOR (steam-oil ratio, prototype mass/volume form)
   SOR = steam_volume_t / (production_bopd * SOR_WINDOW_DAYS)
   evaluated over a documented 30-day prototype window. Zero production
   -> SOR undefined (None, status UNDEFINED_ZERO_OIL); never divides
   by zero. Units: tonnes of steam per barrel of oil (prototype form).

8. ENERGY (prototype operating-day estimate)
   steam_energy_kwh   = steam_volume_t * KWH_PER_T_STEAM
   pumping_energy_kwh = SPM * stroke_in * K_PUMP_KWH_PER_SPM_IN_PER_DAY
   (per 24 h operating day). energy_per_barrel = total / production.
   Coefficients are prototype assumptions, not thermodynamic metering.
   All outputs non-negative; per-barrel is None at zero production.

9. ENGINEERING RISK INDICATORS (deterministic proxies, NOT ML/AI,
   NOT failure probabilities)
   - Rod floating: viscous-drag proxy mu/2000 clamped to [0,1]; thicker
     oil -> higher score (buoyancy/drag vs rod weight intuition).
   - Impact/loading: pump-demand-vs-inflow mismatch plus SPM aggressiveness.
   - Pump unsetting: inflow/pump mismatch fraction plus wellhead-vs-
     reservoir pressure factor (load-transient intuition).
   Each returns risk_level (LOW <0.33 / MODERATE <0.66 / HIGH),
   risk_score 0..1 (ENGINEERING INDICATOR, not a probability), and a
   human-readable reason embedding the actual computed numbers.
=====================================================================
"""

import math

# ---------------- Prototype constants (demo assumptions) ----------------
# Thermal response
TAU_H = 72.0            # thermal time constant, hours (prototype)
DT_MAX_C = 180.0        # max temperature rise above baseline at I=1, C (prototype)
V_REF_T = 1000.0        # steam-volume normalization reference, tonnes (prototype)
P_REF_BAR = 70.0        # injection-pressure normalization reference, bar (prototype)
IDLE_COOL_H = 48.0      # fallback cooling duration for IDLE with soak=0, h (prototype)
T_MIN_C = 0.0           # physical clamp floor, C
T_MAX_C = 350.0         # physical clamp ceiling, C

# Viscosity (Arrhenius-style)
MU_REF_CP = 350.0       # reference viscosity at T_REF_C, cP (prototype heavy-oil assumption)
T_REF_C = 47.0          # reference temperature, C [FROM-PS: Baghewala 46-48 C]
ARRHENIUS_B_K = 4500.0  # temperature sensitivity, Kelvin (prototype)
API_REF = 18.0          # reference API gravity [FROM-PS: Baghewala 17-19 API]
API_VISC_SLOPE = 0.01   # viscosity change per API degree off reference (prototype)
MU_MIN_CP = 0.1         # numerical floor, cP
MU_MAX_CP = 100000.0    # numerical ceiling, cP
_EXP_CLAMP = 10.0       # exponent clamp against overflow/underflow

# Inflow
PRODUCTIVITY_J = 0.8    # prototype productivity index, bopd/bar (prototype)
Q_INFLOW_MAX_BOPD = 5000.0  # numerical cap, bopd

# SRP pump (positive-displacement proxy)
PUMP_DIAMETER_IN = 2.0  # prototype pump bore assumption, inches (prototype)
FILLAGE_DEFAULT = 0.85  # default pump fillage fraction (prototype)
EFFICIENCY_DEFAULT = 0.75  # default mechanical/volumetric efficiency (prototype)
MIN_PER_DAY = 1440.0
IN3_PER_BBL = 9702.0    # cubic inches per barrel

# SOR evaluation window
SOR_WINDOW_DAYS = 30.0  # prototype accounting window, days

# Energy coefficients (prototype)
KWH_PER_T_STEAM = 750.0  # steam-generation energy per tonne injected, kWh/t (prototype)
K_PUMP_KWH = 0.5         # pumping energy per (SPM*inch) per 24 h day, kWh (prototype)

# Risk thresholds (prototype indicator bands, NOT calibrated probabilities)
RISK_LOW_MAX = 0.33
RISK_MOD_MAX = 0.66
MU_FLOAT_REF_CP = 2000.0  # viscosity scaling reference for float proxy, cP (prototype)

_EPS = 1e-9

PROTOTYPE_DISCLAIMER = (
    "Prototype/demo engineering estimates. Coefficients are documented prototype "
    "assumptions, not Oil India certified or field-calibrated values."
)


# ---------------- Small numeric helpers ----------------
def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp x into [lo, hi]. Guards NaN by mapping it to lo."""
    if isinstance(x, bool) or not math.isfinite(x):
        return lo
    return max(lo, min(hi, x))


def _risk_level(score: float) -> str:
    if score < RISK_LOW_MAX:
        return "LOW"
    if score < RISK_MOD_MAX:
        return "MODERATE"
    return "HIGH"


# ---------------- Part 1: temperature response ----------------
def heating_intensity(steam_volume_t: float, steam_injection_pressure_bar: float) -> float:
    """Dimensionless heating intensity in [0, 1].

    Blends normalized steam volume and injection pressure with equal
    weights against prototype references. Zero steam -> zero intensity.
    """
    vol_term = max(steam_volume_t, 0.0) / V_REF_T
    pres_term = max(steam_injection_pressure_bar, 0.0) / P_REF_BAR
    return clamp(0.5 * vol_term + 0.5 * pres_term, 0.0, 1.0)


def heating_temperature(
    baseline_c: float,
    intensity: float,
    duration_h: float,
    tau_h: float = TAU_H,
    dt_max_c: float = DT_MAX_C,
) -> float:
    """Bounded first-order heating: T_base + DT_MAX*I*(1-exp(-t/tau))."""
    t = max(duration_h, 0.0)
    rise = dt_max_c * clamp(intensity, 0.0, 1.0) * (1.0 - math.exp(-t / max(tau_h, _EPS)))
    return clamp(baseline_c + rise, T_MIN_C, T_MAX_C)


def cooling_temperature(
    elevated_c: float,
    baseline_c: float,
    duration_h: float,
    tau_h: float = TAU_H,
) -> float:
    """Exponential cooldown of an elevated temperature toward baseline."""
    t = max(duration_h, 0.0)
    decayed = baseline_c + (elevated_c - baseline_c) * math.exp(-t / max(tau_h, _EPS))
    return clamp(decayed, T_MIN_C, T_MAX_C)


def effective_temperature_c(
    baseline_c: float,
    steam_volume_t: float,
    steam_injection_pressure_bar: float,
    soak_time_h: float,
    css_phase: str,
) -> float:
    """Snapshot temperature: heating branch, or cooling branch when IDLE.

    soak_time_h is the representative thermal exposure duration
    (documented prototype choice). IDLE represents post-steam cooldown.
    """
    intensity = heating_intensity(steam_volume_t, steam_injection_pressure_bar)
    heated = heating_temperature(baseline_c, intensity, soak_time_h)
    if str(css_phase).upper() == "IDLE":
        cool_for = soak_time_h if soak_time_h > 0 else IDLE_COOL_H
        return cooling_temperature(heated, baseline_c, cool_for)
    return heated


# ---------------- Part 2: viscosity ----------------
def viscosity_cp(temperature_c: float, api_gravity: float = API_REF) -> float:
    """Arrhenius-style viscosity in cP. Hotter -> thinner. Always positive."""
    t_k = max(temperature_c, T_MIN_C) + 273.15
    t_ref_k = T_REF_C + 273.15
    exponent = clamp(ARRHENIUS_B_K * (1.0 / t_k - 1.0 / t_ref_k), -_EXP_CLAMP, _EXP_CLAMP)
    mu = MU_REF_CP * math.exp(exponent)
    api_factor = clamp(1.0 - API_VISC_SLOPE * (api_gravity - API_REF), 0.7, 1.3)
    return clamp(mu * api_factor, MU_MIN_CP, MU_MAX_CP)


# ---------------- Part 3: mobility ----------------
def mobility_factor(viscosity_cp_value: float) -> float:
    """Normalized mobility proxy: MU_REF_CP / mu. Thinner oil -> higher."""
    return MU_REF_CP / max(viscosity_cp_value, MU_MIN_CP)


# ---------------- Part 4: inflow / IPR ----------------
def reservoir_inflow_bopd(
    reservoir_pressure_bar: float,
    wellhead_pressure_bar: float,
    viscosity_cp_value: float,
    productivity_j: float = PRODUCTIVITY_J,
) -> float:
    """q = J * max(P_res - P_wh, 0) * mobility. Never negative."""
    drawdown = max(reservoir_pressure_bar - wellhead_pressure_bar, 0.0)
    q = max(productivity_j, 0.0) * drawdown * mobility_factor(viscosity_cp_value)
    return clamp(q, 0.0, Q_INFLOW_MAX_BOPD)


# ---------------- Part 5: SRP pump capacity ----------------
def theoretical_pump_capacity_bopd(
    spm: float, stroke_in: float, diameter_in: float = PUMP_DIAMETER_IN
) -> float:
    """Ideal positive-displacement rate from bore area x stroke x SPM."""
    area_in2 = (math.pi / 4.0) * max(diameter_in, 0.0) ** 2
    disp_in3_per_day = area_in2 * max(stroke_in, 0.0) * max(spm, 0.0) * MIN_PER_DAY
    return max(disp_in3_per_day / IN3_PER_BBL, 0.0)


def actual_pump_capacity_bopd(
    theoretical_bopd: float,
    fillage: float = FILLAGE_DEFAULT,
    efficiency: float = EFFICIENCY_DEFAULT,
) -> float:
    """Derate ideal rate by fillage and efficiency, each clamped to [0, 1]."""
    return max(theoretical_bopd, 0.0) * clamp(fillage, 0.0, 1.0) * clamp(efficiency, 0.0, 1.0)


# ---------------- Part 6: production coupling ----------------
def couple_production_bopd(reservoir_inflow_bopd_value: float, pump_capacity_bopd_value: float):
    """production = min(inflow, pump capacity) plus the binding-side label."""
    inflow = max(reservoir_inflow_bopd_value, 0.0)
    pump = max(pump_capacity_bopd_value, 0.0)
    production = min(inflow, pump)
    limiting = "INFLOW_LIMITED" if inflow <= pump else "PUMP_LIMITED"
    return production, limiting


# ---------------- Part 7: SOR ----------------
def steam_oil_ratio(steam_volume_t: float, oil_volume_bbl: float):
    """SOR = steam / oil over the accounting window.

    Returns (value_or_None, status). Zero/negative oil -> (None,
    'UNDEFINED_ZERO_OIL'); never divides by zero.
    """
    if oil_volume_bbl <= 0:
        return None, "UNDEFINED_ZERO_OIL"
    return max(steam_volume_t, 0.0) / oil_volume_bbl, "DEFINED"


# ---------------- Part 8: energy ----------------
def energy_estimate_kwh(
    steam_volume_t: float, spm: float, stroke_in: float, production_bopd: float
) -> dict:
    """Prototype operating-day energy split: steam generation vs pumping."""
    steam_energy = max(steam_volume_t, 0.0) * KWH_PER_T_STEAM
    pumping_energy = max(spm, 0.0) * max(stroke_in, 0.0) * K_PUMP_KWH
    total = steam_energy + pumping_energy
    per_barrel = (total / production_bopd) if production_bopd > 0 else None
    return {
        "steam_energy_kwh": round(steam_energy, 3),
        "pumping_energy_kwh": round(pumping_energy, 3),
        "total_energy_kwh": round(total, 3),
        "energy_per_barrel_kwh": round(per_barrel, 3) if per_barrel is not None else None,
    }


# ---------------- Part 9: engineering risk indicators ----------------
def rod_float_risk(viscosity_cp_value: float) -> dict:
    """Viscous-drag proxy: thicker oil increasingly supports/floats the rod string."""
    score = round(clamp(viscosity_cp_value / MU_FLOAT_REF_CP, 0.0, 1.0), 3)
    return {
        "risk_level": _risk_level(score),
        "risk_score": score,
        "reason": (
            f"Estimated viscosity {viscosity_cp_value:.1f} cP gives a rod-float "
            f"indicator of {score:.2f}; heavier (more viscous) fluid increases "
            "buoyancy/drag support on the rod string."
        ),
    }


def impact_loading_risk(pump_capacity_bopd_value: float, inflow_bopd: float, spm: float) -> dict:
    """Pump-demand-vs-inflow mismatch plus SPM aggressiveness proxy."""
    demand_ratio = pump_capacity_bopd_value / max(inflow_bopd, _EPS)
    mismatch = clamp((demand_ratio - 1.0) / 2.0, 0.0, 1.0)
    spm_factor = clamp(max(spm, 0.0) / 20.0, 0.0, 1.0)
    score = round(clamp(0.6 * mismatch + 0.4 * spm_factor, 0.0, 1.0), 3)
    return {
        "risk_level": _risk_level(score),
        "risk_score": score,
        "reason": (
            f"Pump demand {pump_capacity_bopd_value:.1f} bopd vs estimated inflow "
            f"{inflow_bopd:.1f} bopd (ratio {demand_ratio:.2f}) at {spm:.1f} SPM "
            f"gives an impact/loading indicator of {score:.2f}; oversized pump "
            "demand and aggressive stroke rates raise impact loading."
        ),
    }


def pump_unsetting_risk(
    pump_capacity_bopd_value: float,
    inflow_bopd: float,
    wellhead_pressure_bar: float,
    reservoir_pressure_bar: float,
) -> dict:
    """Inflow/pump mismatch fraction plus wellhead-vs-reservoir pressure factor."""
    denom = max(pump_capacity_bopd_value + inflow_bopd, _EPS)
    mismatch_frac = clamp(abs(pump_capacity_bopd_value - inflow_bopd) / denom, 0.0, 1.0)
    pressure_factor = (
        clamp(wellhead_pressure_bar / max(reservoir_pressure_bar, _EPS), 0.0, 1.0)
        if reservoir_pressure_bar > 0
        else 0.0
    )
    score = round(clamp(0.7 * mismatch_frac + 0.3 * pressure_factor, 0.0, 1.0), 3)
    return {
        "risk_level": _risk_level(score),
        "risk_score": score,
        "reason": (
            f"Inflow/pump mismatch fraction {mismatch_frac:.2f} with wellhead "
            f"{wellhead_pressure_bar:.1f} bar vs reservoir "
            f"{reservoir_pressure_bar:.1f} bar gives a pump-unsetting indicator "
            f"of {score:.2f}; severe mismatch and adverse pressure transients "
            "raise unsetting tendency."
        ),
    }


# ---------------- Part 10: combined snapshot ----------------
def twin_snapshot(state) -> dict:
    """Deterministic engineering snapshot for one well state.

    Accepts a WellTelemetry (or any object with the same attributes).
    Pure function of the input: identical input -> identical output.
    """
    phase = str(state.css_phase.value if hasattr(state.css_phase, "value") else state.css_phase)

    intensity = heating_intensity(state.steam_volume_t, state.steam_injection_pressure_bar)
    temperature = effective_temperature_c(
        state.reservoir_temperature_c,
        state.steam_volume_t,
        state.steam_injection_pressure_bar,
        state.soak_time_h,
        phase,
    )
    viscosity = viscosity_cp(temperature, state.api_gravity)
    mobility = mobility_factor(viscosity)

    drawdown = max(state.reservoir_pressure_bar - state.wellhead_pressure_bar, 0.0)
    inflow = reservoir_inflow_bopd(
        state.reservoir_pressure_bar, state.wellhead_pressure_bar, viscosity
    )

    pump_theoretical = theoretical_pump_capacity_bopd(state.spm, state.stroke_in)
    pump_actual = actual_pump_capacity_bopd(pump_theoretical, FILLAGE_DEFAULT, EFFICIENCY_DEFAULT)
    production, limiting = couple_production_bopd(inflow, pump_actual)

    oil_window_bbl = production * SOR_WINDOW_DAYS
    sor_value, sor_status = steam_oil_ratio(state.steam_volume_t, oil_window_bbl)

    energy = energy_estimate_kwh(
        state.steam_volume_t, state.spm, state.stroke_in, production
    )

    float_risk = rod_float_risk(viscosity)
    impact_risk = impact_loading_risk(pump_actual, inflow, state.spm)
    unsetting_risk = pump_unsetting_risk(
        pump_actual, inflow, state.wellhead_pressure_bar, state.reservoir_pressure_bar
    )

    levels = [float_risk["risk_level"], impact_risk["risk_level"], unsetting_risk["risk_level"]]
    if "HIGH" in levels:
        overall = "HIGH_RISK"
    elif "MODERATE" in levels:
        overall = "ELEVATED"
    else:
        overall = "NOMINAL"

    worst = max(
        [float_risk, impact_risk, unsetting_risk], key=lambda r: r["risk_score"]
    )
    if overall == "NOMINAL":
        recommendation = (
            f"Operating within prototype envelope. Estimated production "
            f"{production:.1f} bopd is {limiting.lower().replace('_', ' ')}; "
            "no engineering indicator exceeds LOW."
        )
    else:
        recommendation = (
            f"Priority indicator ({worst['risk_level']}, "
            f"{worst['risk_score']:.2f}): {worst['reason']}"
        )

    explanations = {
        "temperature": (
            f"Steam heating (intensity {intensity:.2f} from "
            f"{state.steam_volume_t:.0f} t at {state.steam_injection_pressure_bar:.0f} bar) "
            f"raises reservoir temperature from baseline {state.reservoir_temperature_c:.1f} C "
            f"to an estimated {temperature:.1f} C over {state.soak_time_h:.0f} h exposure "
            f"(phase {phase})."
        ),
        "viscosity": (
            f"Higher temperature reduces estimated viscosity in the prototype "
            f"Arrhenius correlation: {temperature:.1f} C at {state.api_gravity:.1f} API -> "
            f"{viscosity:.1f} cP."
        ),
        "mobility": (
            f"Normalized mobility {mobility:.3f} is inversely proportional to "
            f"viscosity (reference {MU_REF_CP:.0f} cP)."
        ),
        "inflow": (
            f"Drawdown {drawdown:.1f} bar x J={PRODUCTIVITY_J} bopd/bar x mobility "
            f"{mobility:.3f} gives estimated inflow {inflow:.1f} bopd."
        ),
        "pump_capacity": (
            f"Bore {PUMP_DIAMETER_IN:.1f} in x stroke {state.stroke_in:.0f} in x "
            f"{state.spm:.1f} SPM x fillage {FILLAGE_DEFAULT} x efficiency "
            f"{EFFICIENCY_DEFAULT} gives {pump_actual:.1f} bopd pump capacity."
        ),
        "production": (
            f"Estimated production {production:.1f} bopd is the lower of reservoir "
            f"inflow ({inflow:.1f}) and SRP pump capacity ({pump_actual:.1f}): "
            f"{limiting.lower().replace('_', ' ')}."
        ),
        "sor": (
            f"SOR {sor_value:.3f} t/bbl over the {SOR_WINDOW_DAYS:.0f}-day prototype "
            f"window ({state.steam_volume_t:.0f} t steam / {oil_window_bbl:.0f} bbl oil)."
            if sor_value is not None
            else "SOR undefined: estimated oil production is zero, so steam volume "
            "cannot be normalized (no division by zero performed)."
        ),
        "energy": (
            f"Steam generation {energy['steam_energy_kwh']:.0f} kWh plus pumping "
            f"{energy['pumping_energy_kwh']:.0f} kWh per operating day."
        ),
    }

    return {
        "well_id": state.well_id,
        "timestamp": state.timestamp,
        "css_phase": phase,
        "heating_intensity": round(intensity, 4),
        "baseline_reservoir_temperature_c": state.reservoir_temperature_c,
        "estimated_temperature_c": round(temperature, 3),
        "estimated_viscosity_cp": round(viscosity, 3),
        "mobility_factor": round(mobility, 4),
        "reservoir_pressure_bar": state.reservoir_pressure_bar,
        "wellhead_pressure_bar": state.wellhead_pressure_bar,
        "drawdown_bar": round(drawdown, 3),
        "estimated_reservoir_inflow_bopd": round(inflow, 3),
        "spm": state.spm,
        "stroke_in": state.stroke_in,
        "pump_fillage": FILLAGE_DEFAULT,
        "pump_efficiency": EFFICIENCY_DEFAULT,
        "pump_theoretical_capacity_bopd": round(pump_theoretical, 3),
        "pump_capacity_bopd": round(pump_actual, 3),
        "estimated_oil_production_bopd": round(production, 3),
        "production_limiting_factor": limiting,
        "steam_volume_t": state.steam_volume_t,
        "evaluation_window_days": SOR_WINDOW_DAYS,
        "estimated_oil_volume_bbl": round(oil_window_bbl, 3),
        "steam_oil_ratio_t_per_bbl": round(sor_value, 4) if sor_value is not None else None,
        "sor_status": sor_status,
        "steam_energy_kwh": energy["steam_energy_kwh"],
        "pumping_energy_kwh": energy["pumping_energy_kwh"],
        "total_energy_kwh": energy["total_energy_kwh"],
        "energy_per_barrel_kwh": energy["energy_per_barrel_kwh"],
        "rod_float_risk": float_risk,
        "impact_risk": impact_risk,
        "pump_unsetting_risk": unsetting_risk,
        "overall_engineering_status": overall,
        "recommendation": recommendation,
        "explanations": explanations,
        "prototype_disclaimer": PROTOTYPE_DISCLAIMER,
    }
