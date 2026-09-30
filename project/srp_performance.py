"""SIH26120 Digital Twin — SRP pump performance + structured diagnostics (P5).

Builds ON TOP OF srp_dynacard.py and twin_physics.py (no duplicated
equations, no rewritten card logic). Additive layer:

  pump performance  theoretical capacity (existing geometry) vs actual
                    liquid production -> pump efficiency with explicit
                    CALCULATED / UNAVAILABLE / INVALID states.
  diagnostics       structured screening indications derived from the
                    dynacard + snapshot, each with indicators, evidence
                    and tied operating recommendations. Wording is
                    deliberately non-confirmatory ("possible",
                    "suspected", "indication"): nothing here confirms a
                    field failure.
  ML evidence       canonical ml.srp_health assessment attached with its
                    own (synthetic) provenance, never merged into the
                    physics diagnosis.

Conventions: [STD] standard relations, [PROTO] prototype coefficients or
thresholds (explicit, NOT Baghewala-calibrated). Horsepower itself is
computed inside srp_dynacard.dynacard from the card area (shoelace)
[STD: PRHP = area[in*lb] * SPM / (12 * 33000)]; this module surfaces and
contextualises it, it does not redefine it.
"""

import math
from typing import Any, Dict, List, Optional

import twin_physics as tp

# ---------------- Prototype thresholds (explicit, not field limits) ----------------
EFFICIENCY_LOW = 0.50          # [PROTO] below this, pump performance is flagged
DRAG_HIGH_FRAC = 0.50          # [PROTO] drag vs buoyant rod weight -> excessive drag
MISMATCH_UNSET_FRAC = 2.0      # [PROTO] pump/inflow ratio -> suspected unsetting
HP_RISK_KW_PER_HP = 0.7457     # [STD] 1 hp = 0.7457 kW (display conversion only)

PUMP_MODE = "PROTOTYPE_PHYSICS"
BORE_NOTE = ("Pump bore %.1f in is a prototype geometry assumption "
             "(twin_physics.PUMP_DIAMETER_IN), NOT a field-verified Baghewala dimension.")


def pump_capacity_breakdown(spm: float, stroke_in: float,
                            diameter_in: float = tp.PUMP_DIAMETER_IN) -> Dict[str, Any]:
    """Theoretical pump capacity from existing bore geometry.

    Returns the displacement chain with inputs, units and the bore
    assumption exposed. Never claims field-specific geometry.
    """
    spm = max(float(spm or 0.0), 0.0)
    stroke_in = max(float(stroke_in or 0.0), 0.0)
    diameter_in = max(float(diameter_in or 0.0), 0.0)
    area_in2 = (math.pi / 4.0) * diameter_in ** 2
    disp_in3_per_day = area_in2 * stroke_in * spm * tp.MIN_PER_DAY
    theoretical_bopd = max(disp_in3_per_day / tp.IN3_PER_BBL, 0.0)
    return {
        "spm": spm,
        "stroke_in": stroke_in,
        "bore_diameter_in": diameter_in,
        "bore_area_in2": round(area_in2, 4),
        "displacement_in3_per_day": round(disp_in3_per_day, 1),
        "theoretical_capacity_bopd": round(theoretical_bopd, 3),
        "unit": "bopd",
        "geometry_note": BORE_NOTE % diameter_in,
    }


def pump_efficiency(actual_liquid_bpd: Optional[float],
                    theoretical_bopd: Optional[float]) -> Dict[str, Any]:
    """Pump efficiency = actual liquid / theoretical capacity.

    States: CALCULATED (value may exceed 1 -> flagged, never hidden),
    UNAVAILABLE (no positive theoretical capacity), INVALID (negative or
    non-finite inputs). Units must match (bbl/day both sides).
    """
    def _num(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if math.isfinite(f) else None

    actual = _num(actual_liquid_bpd)
    theo = _num(theoretical_bopd)
    base = {"actual_liquid_bpd": actual, "theoretical_capacity_bopd": theo,
            "unit": "fraction", "mode": PUMP_MODE}
    if actual is None or theo is None:
        return {**base, "status": "UNAVAILABLE", "value": None,
                "note": "Missing production or capacity input: efficiency cannot be computed."}
    if actual < 0 or theo < 0:
        return {**base, "status": "INVALID", "value": None,
                "note": "Negative production or capacity is physically impossible."}
    if theo <= 0:
        return {**base, "status": "UNAVAILABLE", "value": None,
                "note": "Zero theoretical capacity (e.g. SPM/stroke at zero): ratio undefined."}
    value = actual / theo
    if value > 1.0:
        return {**base, "status": "CALCULATED", "value": round(value, 4),
                "above_unity": True,
                "note": ("Efficiency above unity: the pump is inflow-limited or the prototype "
                         "bore/fillage assumptions understate displacement. Investigate, do not "
                         "treat as super-efficient pumping.")}
    return {**base, "status": "CALCULATED", "value": round(value, 4),
            "above_unity": False,
            "note": "Actual liquid production over theoretical displacement."}


def _diag(code: str, severity: str, indicators: List[str], evidence: List[str],
          recommended_actions: List[str]) -> Dict[str, Any]:
    return {"code": code, "severity": severity,
            "wording": "diagnostic indication (screening signal, not a confirmed field failure)",
            "indicators": indicators, "evidence": evidence,
            "recommended_actions": recommended_actions}


def diagnose_loading(card: Dict[str, Any], snapshot: Dict[str, Any],
                     efficiency: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Structured screening diagnoses from dynacard + snapshot + efficiency.

    Only observed/calculated indicators trigger entries; each entry carries
    its evidence and tied actions. Conditions use the same thresholds as
    srp_dynacard.dynacard plus explicit [PROTO] additions documented below.
    """
    out: List[Dict[str, Any]] = []
    codes = {d["code"] for d in card.get("diagnosis", [])}
    mprl = card.get("mprl_lb", 0.0)
    wrf = card.get("buoyant_rod_weight_lb", 1.0) or 1.0
    drag = card.get("viscous_drag_lb", 0.0)
    mu = card.get("tubing_viscosity_cp", 0.0)
    goodman = card.get("goodman_loading_percent", 0.0)
    fillage = card.get("estimated_pump_fillage", 1.0)
    stroke = card.get("stroke_in", 0.0)
    spm = snapshot.get("spm", card.get("spm", 0.0))
    eff_val = efficiency.get("value")

    if "ROD_FLOAT" in codes:
        out.append(_diag(
            "ROD_FLOAT", "HIGH",
            ["minimum_rod_load_nonpositive", "viscous_drag_exceeds_buoyant_weight"],
            [f"MPRL {mprl:.0f} lb <= 0", f"drag {drag:.0f} lb vs buoyant weight {wrf:.0f} lb",
             f"tubing viscosity {mu:.0f} cP"],
            ["Consider reducing SPM from current %.1f" % spm,
             "Inspect downstroke loading behavior for free rod fall",
             "Reassess stroke/SPM combination before increasing rate",
             "Review thermal state: heating the fluid lowers drag"]))
    elif "ROD_FLOAT_MARGINAL" in codes:
        out.append(_diag(
            "ROD_FLOAT_MARGINAL", "MODERATE",
            ["thin_rod_fall_margin"],
            [f"MPRL {mprl:.0f} lb under 25% of buoyant weight ({wrf:.0f} lb)"],
            ["Watch downstroke loads on the next readings",
             "Avoid raising SPM until margin recovers"]))

    if "FLUID_POUND" in codes:
        out.append(_diag(
            "POSSIBLE_FLUID_POUND", "HIGH" if fillage < 0.5 else "MODERATE",
            ["incomplete_barrel_fillage", "downstroke_liquid_impact"],
            [f"fillage {fillage:.2f} below 0.75 threshold",
             f"plunger strikes liquid {(1 - fillage) * stroke:.0f} in into the downstroke"],
            ["Consider reducing SPM/stroke or lowering the VFD setpoint to match inflow",
             "Review pump fillage and fluid-level/inflow assumptions",
             "Inspect for impact-loading signatures before resuming rate"]))

    if "ROD_OVERLOAD" in codes:
        out.append(_diag(
            "SUSPECTED_ROD_OVERLOAD", "HIGH",
            ["goodman_loading_above_limit"],
            [f"modified-Goodman loading {goodman:.0f}% >= 100% limit"],
            ["Review stroke/SPM against the operating envelope immediately",
             "Inspect the load envelope for peak-stress excursions"]))
    elif "HIGH_ROD_STRESS" in codes:
        out.append(_diag(
            "ELEVATED_ROD_LOADING", "MODERATE",
            ["goodman_loading_near_limit"],
            [f"modified-Goodman loading {goodman:.0f}% in 90-100% band"],
            ["Review stroke/SPM; avoid rate increases without re-checking loads"]))

    # [PROTO] excessive viscous drag vs buoyant weight.
    if drag > DRAG_HIGH_FRAC * wrf and "ROD_FLOAT" not in codes:
        out.append(_diag(
            "EXCESSIVE_VISCOUS_DRAG", "MODERATE",
            ["drag_fraction_of_buoyant_weight_high"],
            [f"drag {drag:.0f} lb exceeds {DRAG_HIGH_FRAC:.0%} of buoyant weight ({wrf:.0f} lb)",
             f"tubing viscosity {mu:.0f} cP at mean tubing temperature"],
            ["Consider thermal/viscosity state before raising pumping rate",
             "Review pumping rate against fluid-property assumptions"]))

    # [PROTO] low pump efficiency screening.
    if eff_val is not None and eff_val < EFFICIENCY_LOW:
        out.append(_diag(
            "LOW_PUMP_EFFICIENCY", "MODERATE",
            ["actual_far_below_theoretical_displacement"],
            [f"efficiency {eff_val:.2f} below {EFFICIENCY_LOW:.2f} screening level"],
            ["Inspect fillage and compare actual vs theoretical capacity",
             "Evaluate inflow limitations before assuming mechanical failure"]))

    # [PROTO] suspected pump unsetting: pump vastly outruns inflow.
    inflow = snapshot.get("estimated_reservoir_inflow_bopd")
    pump_cap = snapshot.get("pump_capacity_bopd")
    if inflow is not None and pump_cap is not None and float(inflow) > 0:
        ratio = float(pump_cap) / float(inflow)
        if ratio >= MISMATCH_UNSET_FRAC:
            out.append(_diag(
                "POSSIBLE_PUMP_UNSETTING", "MODERATE",
                ["pump_capacity_far_above_inflow"],
                [f"pump {pump_cap:.1f} bopd vs inflow {inflow:.1f} bopd (ratio {ratio:.2f})"],
                ["Reduce SPM/stroke toward the inflow the reservoir can deliver",
                 "Inspect seating/nipple integrity if mismatch persists"]))

    if not out:
        out.append(_diag(
            "NORMAL_OPERATION", "LOW",
            ["full_pump_card", "loads_within_envelope"],
            [f"fillage {fillage:.2f}, Goodman {goodman:.0f}%, MPRL {mprl:.0f} lb in tension"],
            ["Maintain current operating point; continue routine surveillance"]))
    return out


def operating_recommendations(diagnostics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten diagnostic actions; NORMAL_OPERATION yields routine note only."""
    recs = []
    for d in diagnostics:
        if d["code"] == "NORMAL_OPERATION":
            continue
        for action in d["recommended_actions"]:
            recs.append({"for_diagnosis": d["code"], "severity": d["severity"],
                         "action": action})
    if not recs:
        recs.append({"for_diagnosis": "NORMAL_OPERATION", "severity": "LOW",
                     "action": "Maintain current operating point; continue routine surveillance."})
    return recs


def performance_summary(snapshot: Dict[str, Any], card: Dict[str, Any],
                        ml_health: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Combined SRP evidence: power, capacity, efficiency, diagnostics,
    recommendations, and separately-labeled ML health evidence."""
    spm = float(snapshot.get("spm", card.get("spm", 0.0)) or 0.0)
    stroke = float(snapshot.get("stroke_in", card.get("stroke_in", 0.0)) or 0.0)
    capacity = pump_capacity_breakdown(spm, stroke)
    theoretical = tp.theoretical_pump_capacity_bopd(spm, stroke)
    eff = pump_efficiency(snapshot.get("estimated_liquid_production_bpd"), theoretical)
    diags = diagnose_loading(card, snapshot, eff)
    prhp = card.get("polished_rod_hp")
    power = {
        "polished_rod_hp": prhp,
        "polished_rod_kw": round(prhp * HP_RISK_KW_PER_HP, 3) if prhp is not None else None,
        "unit": "hp",
        "method": "card-area (shoelace) x SPM / (12 x 33000) [STD]; surfaced from srp_dynacard, not redefined",
        "mode": PUMP_MODE,
    }
    ml_block: Dict[str, Any]
    if ml_health is None:
        ml_block = {"status": "INSUFFICIENT_DATA",
                    "note": "No ML health assessment attached to this response."}
    else:
        ml_block = {"status": "ATTACHED_SEPARATE_EVIDENCE",
                    "mode": ml_health.get("mode", "SYNTHETIC"),
                    "production_safe": ml_health.get("production_safe", False),
                    "assessment": ml_health,
                    "note": ("Canonical ML risk is separate evidence: demonstration output, "
                             "never merged into the physics diagnosis.")}
    return {
        "power": power,
        "capacity": capacity,
        "efficiency": eff,
        "diagnostics": diags,
        "recommendations": operating_recommendations(diags),
        "ml_health": ml_block,
        "mode": PUMP_MODE,
        "prototype_note": ("Engineering estimates from uncalibrated prototype relations; "
                           "diagnoses are screening indications, not confirmed field failures."),
    }
