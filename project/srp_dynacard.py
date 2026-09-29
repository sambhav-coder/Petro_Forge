"""SIH26120 Digital Twin — synthetic SRP surface dynamometer card (Block 4).

=====================================================================
DOCUMENTATION (standard relations tagged [STD], assumptions [PROTO])
=====================================================================
A dynamometer card (polished-rod load vs rod position over one stroke) is
the primary field diagnostic for sucker-rod pumps. This module predicts
the card the twin EXPECTS for the current operating state, so rod
floating, fluid pound and overload are visible before a failure.

- Rod string: 7/8 in steel rods, 1.634 lb/ft, 0.601 in^2 [STD API 11L].
  Pump depth PUMP_DEPTH_M = 1100 m [PROTO; Jodhpur sandstone reported at
  ~1150 m average depth].
- Fluid SG: oil SG = 141.5 / (131.5 + API) [STD], mixed with water by
  water cut. Buoyancy factor = 1 - 0.128 * SG [STD, steel SG 7.85].
- Fluid load on plunger: Fo = 0.340 * SG * D^2 * H [STD], with the fluid
  level taken AT the pump (H = pump depth; conservative [PROTO]).
- Dynamic (Mills) acceleration factor: alpha = S * N^2 / 70500 [STD].
- Viscous rod drag: F = K_DRAG * mu_tubing * v_mean, v_mean = 2 S N / 60
  in/s [PROTO coefficient]. mu_tubing is evaluated at the mean tubing
  temperature (T_pump + SURFACE_TEMP_C) / 2: produced oil cools as it
  rises, so the rods see thicker fluid than the reservoir holds. Drag ADDS load on the upstroke and SUBTRACTS on
  the downstroke. When downstroke drag exceeds the buoyant rod weight the
  rods cannot fall freely: this is ROD FLOATING (problem-statement issue).
- PPRL = Wrf + Fo + Wr*alpha + drag;  MPRL = Wrf - Wr*alpha - drag.
- Fluid pound: with barrel fillage f < 1 the plunger carries the fluid
  load on the downstroke until it hits liquid at position f*S, then the
  load drops sharply (the classic pound card shape) — impact loading.
- Rod loading: modified Goodman diagram [STD], Grade D rod
  (T = 115 ksi), service factor 0.9:
  Sa = (T/4 + 0.5625 * Smin) * SF;  loading% = (Smax - Smin)/(Sa - Smin).
- Polished-rod horsepower from the card area (shoelace) [STD]:
  PRHP = area[in*lb] * N / (12 * 33000).
All results are engineering estimates from an uncalibrated prototype.
=====================================================================
"""

import math

import twin_physics as tp

PUMP_DEPTH_M = 1100.0         # [PROTO] anchored to ~1150 m reported reservoir depth
FT_PER_M = 3.28084
ROD_WEIGHT_LB_FT = 1.634      # [STD] 7/8 in steel rod, API 11L
ROD_AREA_IN2 = 0.601          # [STD] 7/8 in rod cross-section
ROD_TENSILE_PSI = 115000.0    # [STD] Grade D minimum tensile strength
GOODMAN_SF = 0.9              # [STD] service factor (non-corrosive)
K_DRAG = 0.35                 # [PROTO] viscous drag, lb per (cP * in/s)
SURFACE_TEMP_C = 30.0         # [PROTO] wellhead flowing temperature (Rajasthan ambient)
LOAD_TRANSFER_FRAC = 0.12     # [PROTO] stroke fraction for fluid-load transfer
CARD_POINTS = 96

FILLAGE_POUND = 0.75          # below this, incomplete fillage is flagged as fluid pound
GOODMAN_HIGH = 90.0
GOODMAN_OVER = 100.0


def fluid_specific_gravity(api_gravity: float, water_cut_fraction: float) -> float:
    """Mixed produced-fluid SG from API gravity and water cut [STD]."""
    sg_oil = 141.5 / (131.5 + max(api_gravity, 1.0))
    wc = tp.clamp(water_cut_fraction, 0.0, 1.0)
    return sg_oil * (1.0 - wc) + 1.0 * wc


def _smoothstep(u: float) -> float:
    u = tp.clamp(u, 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def _shoelace(points) -> float:
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def dynacard(snapshot: dict, api_gravity: float, pump_depth_m: float = PUMP_DEPTH_M) -> dict:
    """Predicted surface card + loads + diagnosis for one twin snapshot."""
    stroke = max(float(snapshot["stroke_in"]), 0.0)
    spm = max(float(snapshot["spm"]), 0.0)
    t_pump = float(snapshot["estimated_temperature_c"])
    t_tubing = (t_pump + SURFACE_TEMP_C) / 2.0
    mu = tp.viscosity_cp(t_tubing, api_gravity)
    fillage = tp.clamp(float(snapshot.get("estimated_pump_fillage", 1.0)), 0.0, 1.0)
    wc = float(snapshot.get("water_cut_percent", 0.0)) / 100.0

    depth_ft = max(pump_depth_m, 0.0) * FT_PER_M
    sg = fluid_specific_gravity(api_gravity, wc)
    wr = ROD_WEIGHT_LB_FT * depth_ft                     # dry rod weight
    wrf = wr * (1.0 - 0.128 * sg)                        # buoyant rod weight
    fo = 0.340 * sg * tp.PUMP_DIAMETER_IN ** 2 * depth_ft
    alpha = stroke * spm ** 2 / 70500.0
    v_mean = 2.0 * stroke * spm / 60.0
    drag = K_DRAG * mu * v_mean
    drag_peak = drag * math.pi / 2.0                     # sin-profile with the same mean

    pts = []
    transfer = max(LOAD_TRANSFER_FRAC * stroke, 1e-6)
    for i in range(CARD_POINTS):
        theta = 2.0 * math.pi * i / CARD_POINTS
        x = stroke / 2.0 * (1.0 - math.cos(theta))
        base = wrf + wr * alpha * math.cos(theta) + drag_peak * math.sin(theta)
        if theta <= math.pi:
            fluid = fo * _smoothstep(x / transfer)
        else:
            # Downstroke: fluid load stays on the rods until the plunger meets liquid.
            release_at = fillage * stroke
            fluid = fo * _smoothstep((x - (release_at - transfer)) / transfer)
        pts.append((round(x, 2), round(base + fluid, 1)))

    loads = [p[1] for p in pts]
    pprl = max(loads)
    mprl = min(loads)
    s_max = pprl / ROD_AREA_IN2
    s_min = mprl / ROD_AREA_IN2
    s_allow = (ROD_TENSILE_PSI / 4.0 + 0.5625 * s_min) * GOODMAN_SF
    goodman = 100.0 * (s_max - s_min) / max(s_allow - s_min, 1.0)
    prhp = _shoelace(pts) * spm / (12.0 * 33000.0)

    diagnosis = []
    if mprl <= 0.0:
        diagnosis.append({
            "code": "ROD_FLOAT", "severity": "HIGH",
            "detail": (f"Downstroke viscous drag {drag:.0f} lb at {mu:.0f} cP exceeds the buoyant "
                       f"rod weight {wrf:.0f} lb (min load {mprl:.0f} lb): rods cannot fall freely. "
                       "Reduce SPM, or heat the fluid (steam) before pumping harder."),
        })
    elif mprl < 0.25 * wrf:
        diagnosis.append({
            "code": "ROD_FLOAT_MARGINAL", "severity": "MODERATE",
            "detail": (f"Minimum load {mprl:.0f} lb is under 25% of buoyant rod weight "
                       f"({wrf:.0f} lb); rod-fall margin is thin at {mu:.0f} cP."),
        })
    if fillage < FILLAGE_POUND:
        diagnosis.append({
            "code": "FLUID_POUND", "severity": "HIGH" if fillage < 0.5 else "MODERATE",
            "detail": (f"Estimated barrel fillage {fillage:.2f}: the plunger strikes liquid "
                       f"{(1 - fillage) * stroke:.0f} in into the downstroke (impact loading). "
                       "Reduce SPM/stroke or lower the VFD setpoint to match inflow."),
        })
    if goodman >= GOODMAN_OVER:
        diagnosis.append({
            "code": "ROD_OVERLOAD", "severity": "HIGH",
            "detail": f"Modified-Goodman rod loading {goodman:.0f}% exceeds the 100% limit.",
        })
    elif goodman >= GOODMAN_HIGH:
        diagnosis.append({
            "code": "HIGH_ROD_STRESS", "severity": "MODERATE",
            "detail": f"Modified-Goodman rod loading {goodman:.0f}% is close to the limit.",
        })
    if not diagnosis:
        diagnosis.append({
            "code": "NORMAL", "severity": "LOW",
            "detail": (f"Full-pump card: fillage {fillage:.2f}, Goodman loading {goodman:.0f}%, "
                       f"minimum load {mprl:.0f} lb keeps the rods in tension."),
        })

    return {
        "well_id": snapshot.get("well_id"),
        "points": [{"position_in": x, "load_lb": y} for x, y in pts],
        "stroke_in": stroke,
        "spm": spm,
        "pump_depth_m": pump_depth_m,
        "fluid_sg": round(sg, 4),
        "rod_weight_lb": round(wr, 1),
        "buoyant_rod_weight_lb": round(wrf, 1),
        "fluid_load_lb": round(fo, 1),
        "mills_acceleration_factor": round(alpha, 4),
        "tubing_mean_temperature_c": round(t_tubing, 2),
        "tubing_viscosity_cp": round(mu, 2),
        "viscous_drag_lb": round(drag, 1),
        "pprl_lb": round(pprl, 1),
        "mprl_lb": round(mprl, 1),
        "max_rod_stress_psi": round(s_max, 0),
        "min_rod_stress_psi": round(s_min, 0),
        "goodman_loading_percent": round(goodman, 1),
        "polished_rod_hp": round(prhp, 3),
        "estimated_pump_fillage": round(fillage, 4),
        "diagnosis": diagnosis,
        "primary_diagnosis": diagnosis[0]["code"],
        "prototype_disclaimer": tp.PROTOTYPE_DISCLAIMER,
    }
