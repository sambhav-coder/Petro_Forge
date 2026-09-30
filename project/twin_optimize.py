"""SIH26120 Digital Twin — what-if simulation + joint CSS/SRP optimization (Block 3).

=====================================================================
DOCUMENTATION (prototype/demo assumptions)
=====================================================================
- SEARCH GRID (defaults, all inside Block 1 input-safety ranges):
    steam_volume_t:              [600, 800, 1000] t
    steam_injection_pressure_bar:[50, 65, 80] bar
    soak_time_h:                 [24, 48, 72] h
    spm:                         [4, 6, 8]
    stroke_in:                   [72, 84, 96] in
  Default space = 3^5 = 243 deterministic evaluations. Custom grids are
  accepted (1-5 values per dimension, max 2000 combinations).
- OBJECTIVE (transparent weighted score, PROTOTYPE DEMONSTRATION
  WEIGHTS — NOT provided by Oil India):
    score = 0.40*norm_production - 0.25*norm_sor
            - 0.15*norm_energy - 0.20*mean_risk
  norm_* are min-max normalizations across the evaluated candidates
  (higher production is better; lower SOR/energy is better). Undefined
  SOR or per-barrel energy (zero production) scores the worst penalty
  (1.0). mean_risk is the raw mean of the three Block 2 indicator
  scores (already 0..1). Ties break deterministically by production,
  then SOR, then energy, then grid order.
- CONSTRAINTS: every candidate must satisfy the Block 1 input-safety
  ranges (steam 0-100000 t, soak 0-720 h, SPM 0-20, stroke 0-300 in,
  pressure 0-300 bar). Out-of-range grid values are REJECTED (HTTP
  422), never silently clamped.
- WHY GRID SEARCH: transparent, deterministic, dependency-free,
  millisecond-scale for this space, and every candidate is explainable
  — appropriate for a hackathon demonstration. No scipy required.
- PARETO FRONTIER: non-dominated candidates over (max production, min
  SOR, min per-barrel energy, min mean risk) using the same quantities
  as the weighted score. The recommendation is the highest weighted
  score AMONG frontier candidates — "recommended under current
  objective weights", never globally optimal. No uncertainty bands.
- VFD (Block 4): the VFD is the actuator that sets SPM. The grid still
  searches SPM (the variable the pump physics consumes) and every
  candidate reports the VFD setpoint that delivers it
  (twin_physics.vfd_for_spm), so the recommendation is directly
  actionable at the drive. steam_injection_pressure is searched too: it
  genuinely drives heating_intensity in twin_physics.
- SIMULATION vs FIELD OPERATION: simulate/optimize answer
  "what would the prototype model predict if...". They are engineering
  estimates from an uncalibrated demonstration model, NOT field
  measurements, guarantees, or control commands. No automatic dispatch
  to equipment exists.
- LIMITATIONS: uncalibrated prototype physics; fixed fillage/
  efficiency defaults; SOR/energy use a 30-day prototype window;
  weights are demonstrative; search is limited to the grid.
=====================================================================
"""

import itertools

import twin_physics as tp

# ---------------- Search grid + objective (prototype demo choices) ----------------
STEAM_GRID_T = [600.0, 800.0, 1000.0]
PRESSURE_GRID_BAR = [50.0, 65.0, 80.0]
SOAK_GRID_H = [24.0, 48.0, 72.0]
SPM_GRID = [4.0, 6.0, 8.0]
STROKE_GRID_IN = [72.0, 84.0, 96.0]

W_PROD = 0.40
W_SOR = 0.25
W_ENERGY = 0.15
W_RISK = 0.20

TOP_K = 5
MAX_COMBINATIONS = 2000

# Safety bounds mirrored from the Block 1 input model (rejection, not clamping).
BOUNDS = {
    "steam_volume_t": (0.0, 100000.0),
    "steam_injection_pressure_bar": (0.0, 300.0),
    "soak_time_h": (0.0, 720.0),
    "spm": (0.0, 20.0),
    "stroke_in": (0.0, 300.0),
}

SIM_MODE_LABEL = "PROTOTYPE_SIMULATION"
OPT_MODE_LABEL = "PROTOTYPE_OPTIMIZATION"

# Pareto / multi-objective reporting (prototype demonstration).
# Objectives reuse the exact quantities the weighted score consumes:
#   maximize production, minimize SOR, minimize per-barrel energy,
#   minimize mean risk. Undefined SOR / per-barrel energy (zero
#   production) is +inf: worst on that axis, never silently dropped.
# Uncertainty quantification is NOT supported (see UNCERTAINTY_NOTE).
RECOMMENDATION_POLICY = (
    "Recommended under current objective weights "
    f"(production {W_PROD}, SOR {W_SOR}, energy {W_ENERGY}, risk {W_RISK}): "
    "highest weighted score among non-dominated (Pareto-optimal) candidates. "
    "Not claimed globally optimal."
)
UNCERTAINTY_NOTE = (
    "Uncertainty quantification is not supported: candidates are deterministic "
    "point evaluations of uncalibrated prototype physics. No confidence bands "
    "are computed or implied."
)

_LEVEL_RANK = {"LOW": 0, "MODERATE": 1, "HIGH": 2}


# ---------------- Scenario helpers ----------------
def default_grid() -> dict:
    """Documented default search grid (243 combinations)."""
    return {
        "steam_volume_t": list(STEAM_GRID_T),
        "steam_injection_pressure_bar": list(PRESSURE_GRID_BAR),
        "soak_time_h": list(SOAK_GRID_H),
        "spm": list(SPM_GRID),
        "stroke_in": list(STROKE_GRID_IN),
    }


def validate_grid(grid: dict) -> dict:
    """Reject out-of-bounds/oversized grids with a clear message (no silent clamping)."""
    errors = []
    total = 1
    for key, (lo, hi) in BOUNDS.items():
        values = grid.get(key, [])
        if not values:
            errors.append(f"{key}: grid must contain at least one value")
            continue
        for v in values:
            if not (lo <= v <= hi):
                errors.append(f"{key}={v}: outside safety range [{lo}, {hi}]")
        total *= len(values)
    if total > MAX_COMBINATIONS:
        errors.append(
            f"search space {total} exceeds the {MAX_COMBINATIONS} combination limit; "
            "shrink the grid"
        )
    if errors:
        raise ValueError("; ".join(errors))
    return grid


def apply_scenario(state, overrides: dict):
    """Hypothetical state copy. Never mutates the stored well record."""
    clean = {k: v for k, v in overrides.items() if v is not None}
    return state.model_copy(update=clean)


# ---------------- Comparison ----------------
def compare_snapshots(current: dict, other: dict) -> dict:
    """Scenario-vs-current deltas. Sign convention: other MINUS current."""
    prod_delta = round(other["estimated_oil_production_bopd"] - current["estimated_oil_production_bopd"], 3)
    sor_delta = None
    if other["steam_oil_ratio_t_per_bbl"] is not None and current["steam_oil_ratio_t_per_bbl"] is not None:
        sor_delta = round(other["steam_oil_ratio_t_per_bbl"] - current["steam_oil_ratio_t_per_bbl"], 4)
    energy_delta = round(other["total_energy_kwh"] - current["total_energy_kwh"], 3)
    return {
        "production_delta_bopd": prod_delta,
        "sor_delta_t_per_bbl": sor_delta,
        "energy_delta_kwh": energy_delta,
        "status_from": current["overall_engineering_status"],
        "status_to": other["overall_engineering_status"],
        "status_changed": current["overall_engineering_status"] != other["overall_engineering_status"],
        "limiting_from": current["production_limiting_factor"],
        "limiting_to": other["production_limiting_factor"],
    }


# ---------------- Objective ----------------
def _minmax(values):
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def score_candidates(evaluated: list) -> list:
    """Attach transparent weighted scores (higher = better). Deterministic.

    Each item of `evaluated` must hold a 'snapshot' dict. Undefined SOR /
    per-barrel energy (zero production) take the worst penalty (1.0).
    """
    prods = [e["snapshot"]["estimated_oil_production_bopd"] for e in evaluated]
    sors = [
        e["snapshot"]["steam_oil_ratio_t_per_bbl"]
        if e["snapshot"]["steam_oil_ratio_t_per_bbl"] is not None else None
        for e in evaluated
    ]
    engs = [
        e["snapshot"]["energy_per_barrel_kwh"]
        if e["snapshot"]["energy_per_barrel_kwh"] is not None else None
        for e in evaluated
    ]
    risks = [
        (e["snapshot"]["rod_float_risk"]["risk_score"]
         + e["snapshot"]["impact_risk"]["risk_score"]
         + e["snapshot"]["pump_unsetting_risk"]["risk_score"]) / 3.0
        for e in evaluated
    ]
    n_prod = _minmax(prods)
    finite_sor = [s for s in sors if s is not None]
    n_sor_raw = _minmax(finite_sor) if finite_sor else []
    it = iter(n_sor_raw)
    n_sor = [next(it) if s is not None else 1.0 for s in sors]
    finite_eng = [v for v in engs if v is not None]
    n_eng_raw = _minmax(finite_eng) if finite_eng else []
    jt = iter(n_eng_raw)
    n_eng = [next(jt) if v is not None else 1.0 for v in engs]

    for i, e in enumerate(evaluated):
        e["score"] = round(
            W_PROD * n_prod[i] - W_SOR * n_sor[i] - W_ENERGY * n_eng[i] - W_RISK * risks[i],
            4,
        )
        e["mean_risk"] = round(risks[i], 4)
    return evaluated


def _rank_key(item):
    snap = item["snapshot"]
    sor = snap["steam_oil_ratio_t_per_bbl"]
    eng = snap["energy_per_barrel_kwh"]
    return (
        -item["score"],
        -snap["estimated_oil_production_bopd"],
        float("inf") if sor is None else sor,
        float("inf") if eng is None else eng,
        item["grid_index"],
    )


# ---------------- Pareto frontier (multi-objective) ----------------
# Objective vector per candidate: (production [max], sor [min],
# energy-per-barrel [min], mean risk [min]). A dominates B when A is no
# worse on every objective and strictly better on at least one. Ties and
# duplicate vectors never dominate each other. Pure vector comparison:
# deterministic and independent of candidate ordering.
def _objective_tuple(objectives: dict) -> tuple:
    sor = objectives["sor_t_per_bbl"]
    eng = objectives["energy_per_barrel_kwh"]
    return (
        objectives["production_bopd"],
        float("inf") if sor is None else sor,
        float("inf") if eng is None else eng,
        objectives["mean_risk"],
    )


def pareto_flags(vectors: list) -> list:
    """Non-dominated flags for (production, sor, energy, risk) tuples.

    vectors use +inf for undefined minimize-quantities. Returns a bool
    per vector: True = pareto-optimal. Empty input -> [].
    """
    n = len(vectors)
    flags = [True] * n
    for i in range(n):
        if not flags[i]:
            continue
        pi, si, ei, ri = vectors[i]
        for j in range(n):
            if i == j:
                continue
            pj, sj, ej, rj = vectors[j]
            # j dominates i: no worse everywhere (prod max, rest min)...
            if pj >= pi and sj <= si and ej <= ei and rj <= ri:
                # ...and strictly better on at least one axis.
                if pj > pi or sj < si or ej < ei or rj < ri:
                    flags[i] = False
                    break
    return flags


def attach_pareto(evaluated: list) -> list:
    """Attach 'objectives' dicts + 'pareto_optimal' flags (in place).

    Requires 'mean_risk' (set by score_candidates) on each item.
    """
    for e in evaluated:
        snap = e["snapshot"]
        e["objectives"] = {
            "production_bopd": snap["estimated_oil_production_bopd"],
            "sor_t_per_bbl": snap["steam_oil_ratio_t_per_bbl"],
            "energy_per_barrel_kwh": snap["energy_per_barrel_kwh"],
            "mean_risk": e["mean_risk"],
        }
    vectors = [_objective_tuple(e["objectives"]) for e in evaluated]
    for e, flag in zip(evaluated, pareto_flags(vectors)):
        e["pareto_optimal"] = flag
    return evaluated


def objective_summary(evaluated: list) -> dict:
    """Finite min/max per objective + direction (for trade-off display)."""
    def finite(key):
        vals = [e["objectives"][key] for e in evaluated
                if e["objectives"][key] is not None
                and e["objectives"][key] != float("inf")]
        return vals
    out = {}
    for key, direction in (("production_bopd", "maximize"),
                           ("sor_t_per_bbl", "minimize"),
                           ("energy_per_barrel_kwh", "minimize"),
                           ("mean_risk", "minimize")):
        vals = finite(key)
        total = len(evaluated)
        out[key] = {
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
            "direction": direction,
            "undefined_count": total - len(vals),
        }
    return out


def constraint_report() -> list:
    """Prototype input-safety constraints (rejection, never clamping).

    These are engineering input-safety ranges, NOT field-validated
    Baghewala operating limits.
    """
    labels = {
        "steam_volume_t": "steam volume (t)",
        "steam_injection_pressure_bar": "injection pressure (bar)",
        "soak_time_h": "soak time (h)",
        "spm": "SPM",
        "stroke_in": "stroke (in)",
    }
    return [{
        "variable": key,
        "label": labels[key],
        "min": lo,
        "max": hi,
        "kind": "prototype_input_safety_range",
        "note": "Out-of-range grid values are rejected (HTTP 422), never silently clamped. "
                "Not a field-validated Baghewala limit.",
    } for key, (lo, hi) in BOUNDS.items()]


# ---------------- Optimization ----------------
def optimize_well(state, grid: dict = None) -> dict:
    """Joint CSSxSRP grid search over the Block 2 physics. Fully deterministic."""
    grid = validate_grid(grid or default_grid())
    keys = ["steam_volume_t", "steam_injection_pressure_bar", "soak_time_h", "spm", "stroke_in"]
    # CSS phase is held at the well's current value during optimization;
    # it is echoed in each candidate's inputs for a complete record.
    phase = state.css_phase.value if hasattr(state.css_phase, "value") else str(state.css_phase)

    evaluated = []
    for idx, combo in enumerate(itertools.product(*(grid[k] for k in keys))):
        overrides = dict(zip(keys, combo))
        hypo = apply_scenario(state, overrides)
        snap = tp.twin_snapshot(hypo)
        evaluated.append(
            {"grid_index": idx,
             "inputs": dict(overrides, css_phase=phase,
                            vfd_setpoint_percent=tp.vfd_for_spm(overrides["spm"])),
             "snapshot": snap}
        )

    score_candidates(evaluated)
    attach_pareto(evaluated)
    ranked = sorted(evaluated, key=_rank_key)
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    frontier = sorted(
        [e for e in evaluated if e["pareto_optimal"]],
        key=lambda e: (-e["objectives"]["production_bopd"], e["grid_index"]),
    )
    # Recommendation: highest weighted score among non-dominated candidates
    # ("recommended under current objective weights", never globally optimal).
    pool = frontier or ranked
    pareto_best = sorted(pool, key=_rank_key)[0]

    current = tp.twin_snapshot(state)
    best = pareto_best
    delta = compare_snapshots(current, best["snapshot"])
    reasons = build_reasons(current, best["snapshot"])
    reasons.insert(
        0,
        f"Non-dominated Pareto-optimal candidate (rank #{best['rank']} overall, "
        f"1 of {len(frontier)} on the frontier of {len(evaluated)} evaluated). "
        f"{RECOMMENDATION_POLICY}",
    )

    return {
        "current": current,
        "best": best,
        "ranked": ranked,
        "frontier": frontier,
        "pareto_count": len(frontier),
        "objective_summary": objective_summary(evaluated),
        "constraints": constraint_report(),
        "recommendation_policy": RECOMMENDATION_POLICY,
        "uncertainty_note": UNCERTAINTY_NOTE,
        "delta": delta,
        "why_recommended": reasons,
        "scenarios_evaluated": len(evaluated),
        "grid": grid,
    }


# ---------------- Recommendation reasons (value-traceable) ----------------
def build_reasons(current: dict, recommended: dict) -> list:
    """Human-readable Digital Twin explanations; each tied to actual numbers."""
    reasons = []
    cp = current["estimated_oil_production_bopd"]
    rp = recommended["estimated_oil_production_bopd"]
    cs = current["steam_oil_ratio_t_per_bbl"]
    rs = recommended["steam_oil_ratio_t_per_bbl"]

    reasons.append(
        f"Estimated production {rp:.1f} vs current {cp:.1f} bopd "
        f"(delta {rp - cp:+.1f}). The {'reservoir remained' if recommended['production_limiting_factor'] == 'INFLOW_LIMITED' else 'pump remained'} "
        f"the limiting side of the well-to-surface system."
    )

    d_temp = recommended["estimated_temperature_c"] - current["estimated_temperature_c"]
    if abs(d_temp) > 0.05:
        verb = "reduced" if recommended["estimated_viscosity_cp"] < current["estimated_viscosity_cp"] else "raised"
        reasons.append(
            f"Simulated temperature {recommended['estimated_temperature_c']:.1f} C vs current "
            f"{current['estimated_temperature_c']:.1f} C {verb} estimated viscosity to "
            f"{recommended['estimated_viscosity_cp']:.1f} cP (current {current['estimated_viscosity_cp']:.1f} cP)."
        )
        mob_verb = "increased" if recommended["mobility_factor"] > current["mobility_factor"] else "decreased"
        reasons.append(
            f"Viscosity change {mob_verb} the mobility factor to {recommended['mobility_factor']:.3f} "
            f"(current {current['mobility_factor']:.3f})."
        )

    c_spm, r_spm = current["spm"], recommended["spm"]
    if r_spm < c_spm and current["pump_capacity_bopd"] > current["estimated_reservoir_inflow_bopd"]:
        reasons.append(
            f"Reduce SPM from {c_spm:.1f} to {r_spm:.1f} because pump capacity "
            f"({current['pump_capacity_bopd']:.1f} bopd) exceeded estimated reservoir inflow "
            f"({current['estimated_reservoir_inflow_bopd']:.1f} bopd); the selected SPM reduces "
            "pump/inflow mismatch."
        )
    elif r_spm > c_spm:
        reasons.append(
            f"Increase SPM from {c_spm:.1f} to {r_spm:.1f} because estimated inflow supports "
            f"additional pump capacity (recommended pump {recommended['pump_capacity_bopd']:.1f} bopd)."
        )
    elif r_spm == c_spm:
        reasons.append(
            f"Maintain current SPM ({c_spm:.1f}): the optimizer found no meaningful benefit "
            "from changing it within the searched grid."
        )
    else:
        reasons.append(
            f"Adjust SPM from {c_spm:.1f} to {r_spm:.1f} as part of the jointly optimized "
            f"trade-off (production {rp:.1f} bopd, SOR {rs}, energy "
            f"{recommended['total_energy_kwh']:.0f} kWh)."
        )

    if r_spm != c_spm:
        reasons.append(
            f"Set the VFD to {tp.vfd_for_spm(r_spm):.0f}% (from {tp.vfd_for_spm(c_spm):.0f}%) to deliver "
            f"{r_spm:.1f} SPM at the prototype drive ratio of {tp.SPM_AT_FULL_VFD:.0f} SPM at full speed."
        )

    c_stm, r_stm = current["steam_volume_t"], recommended["steam_volume_t"]
    if r_stm > c_stm:
        reasons.append(
            f"Increase steam volume from {c_stm:.0f} to {r_stm:.0f} t to raise heating "
            f"intensity ({recommended['heating_intensity']:.2f} vs {current['heating_intensity']:.2f}); "
            f"simulated viscosity is {recommended['estimated_viscosity_cp']:.1f} cP."
        )
    elif r_stm < c_stm:
        reasons.append(
            f"Reduce steam volume from {c_stm:.0f} to {r_stm:.0f} t because the SOR/energy "
            f"penalty outweighed the production gain (recommended SOR {rs} vs current {cs})."
        )
    else:
        reasons.append(
            f"Maintain current steam volume ({c_stm:.0f} t): changing it within the grid "
            "did not improve the weighted trade-off."
        )

    c_str, r_str = current["stroke_in"], recommended["stroke_in"]
    if r_str == c_str:
        reasons.append(
            f"Maintain current stroke ({c_str:.0f} in): the optimizer found no meaningful "
            "benefit from changing it within the searched grid."
        )
    else:
        verb = "Increasing" if r_str > c_str else "Reducing"
        reasons.append(
            f"{verb} stroke from {c_str:.0f} to {r_str:.0f} in adjusts pump capacity to "
            f"{recommended['pump_capacity_bopd']:.1f} bopd against estimated inflow "
            f"{recommended['estimated_reservoir_inflow_bopd']:.1f} bopd."
        )

    if cs is not None and rs is not None:
        if rs < cs:
            reasons.append(
                f"The recommended scenario reduced SOR to {rs:.4f} from {cs:.4f} t/bbl."
            )
        elif rs > cs:
            reasons.append(
                f"The recommendation accepts higher SOR ({rs:.4f} vs {cs:.4f} t/bbl) in "
                "exchange for the production/risk trade-off above."
            )

    rank_now = _LEVEL_RANK[current["overall_engineering_status"]] if current["overall_engineering_status"] in _LEVEL_RANK else 0
    rank_rec = _LEVEL_RANK[recommended["overall_engineering_status"]] if recommended["overall_engineering_status"] in _LEVEL_RANK else 0
    if rank_rec < rank_now:
        reasons.append(
            f"Overall engineering status improved from {current['overall_engineering_status']} "
            f"to {recommended['overall_engineering_status']}."
        )
    elif rank_rec > rank_now:
        reasons.append(
            f"Note: overall status changed from {current['overall_engineering_status']} to "
            f"{recommended['overall_engineering_status']}; the prototype weighting judged the "
            "production/SOR/energy gains to outweigh this."
        )
    return reasons


def assumption_lines(grid: dict) -> list:
    """Explicit prototype assumptions attached to every optimize response."""
    return [
        f"Search grid (steam t): {grid['steam_volume_t']}",
        f"Search grid (pressure bar): {grid['steam_injection_pressure_bar']}",
        f"Search grid (soak h): {grid['soak_time_h']}",
        f"Search grid (SPM): {grid['spm']}",
        f"Search grid (stroke in): {grid['stroke_in']}",
        f"Objective weights (prototype demonstration, not Oil India provided): "
        f"production {W_PROD}, SOR {W_SOR}, energy {W_ENERGY}, risk {W_RISK}",
        "Grid search over Block 2 prototype physics: transparent, deterministic, no ML.",
        f"VFD setpoint derived from SPM: SPM = {tp.SPM_AT_FULL_VFD:.0f} x VFD% / 100 (prototype drive ratio).",
        "Oil rate = liquid rate x (1 - water cut); the pump lifts total liquid.",
        tp.PROTOTYPE_DISCLAIMER,
    ]
