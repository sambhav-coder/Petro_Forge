"""SIH26120 Digital Twin — full CSS cycle simulation + cycle planning (Block 4).

=====================================================================
DOCUMENTATION (prototype/demo assumptions)
=====================================================================
The Block 2 snapshot answers "what is the well doing now". CSS decisions
(steam volume, soak time, WHEN TO CUT OFF production and re-steam) need
the whole cycle over time. This module steps one cycle day by day through
the SAME twin_snapshot physics (no duplicated equations):

  INJECTION  steam_volume_t / INJECTION_RATE_T_PER_DAY days, well shut in
  SOAK       soak_time_h / 24 days, well shut in
  PRODUCTION day d: twin_snapshot(phase=PRODUCTION, days_in_phase=d)
             -> heated zone cools with TAU_PROD_D, viscosity rises, oil
             rate declines toward the cold (unstimulated) rate.

Cycle metrics
- cold_rate: oil rate with no steam (baseline you would get anyway).
- cumulative oil, incremental oil = cum_oil - cold_rate * cycle_days
  (the shut-in days are an opportunity cost).
- cycle SOR in two units: t/bbl, and the industry form bbl CWE / bbl oil
  (1 t steam = 6.29 bbl cold-water-equivalent [STD]).
- OPTIMAL CUT-OFF (marginal value rule [STD in cyclic operations]):
  the cycle's average oil rate R(t) = cum_oil(t) / (inj + soak + t) is
  maximised; past that day re-steaming yields more oil per day than
  continuing. Also reported: the thermal-benefit limit where the rate
  falls below COLD_RATE_MARGIN x the cold rate.

Cycle planner: grid over steam volume x soak time, each simulated to its
own optimal cut-off; ranked by average cycle oil rate subject to a
cycle SOR ceiling (prototype limit SOR_CWE_LIMIT).
=====================================================================
"""

from types import SimpleNamespace

import twin_physics as tp

INJECTION_RATE_T_PER_DAY = 100.0   # [PROTO] steam generator delivery rate
MAX_PRODUCTION_DAYS = 180          # simulation horizon for the production phase
BBL_CWE_PER_T = 6.29               # [STD] 1 tonne water = 6.29 bbl
COLD_RATE_MARGIN = 1.10            # thermal benefit considered exhausted below 110% cold rate
SOR_CWE_LIMIT = 8.0                # [PROTO] planner SOR ceiling, bbl CWE / bbl oil

PLAN_STEAM_T = [400.0, 600.0, 800.0, 1000.0, 1200.0]
PLAN_SOAK_H = [24.0, 48.0, 72.0, 96.0, 120.0]


def _with(state, **updates):
    """Copy of a WellTelemetry (pydantic) or plain namespace with updates."""
    if hasattr(state, "model_copy"):
        return state.model_copy(update=updates)
    data = dict(vars(state))
    data.update(updates)
    return SimpleNamespace(**data)


def simulate_cycle(state, max_production_days: int = MAX_PRODUCTION_DAYS,
                   include_series: bool = True) -> dict:
    """Day-by-day CSS cycle for the state's steam/soak/SRP settings."""
    inj_days = max(state.steam_volume_t, 0.0) / INJECTION_RATE_T_PER_DAY
    soak_days = max(state.soak_time_h, 0.0) / 24.0
    downtime = inj_days + soak_days

    cold = tp.twin_snapshot(_with(state, steam_volume_t=0.0, steam_injection_pressure_bar=0.0,
                                  css_phase="PRODUCTION", days_in_phase=0.0))
    cold_rate = cold["estimated_oil_production_bopd"]

    series = []
    if include_series:
        for d in range(int(round(inj_days))):
            series.append({"day": d, "phase": "INJECTION", "oil_rate_bopd": 0.0,
                           "temperature_c": None, "viscosity_cp": None, "cum_oil_bbl": 0.0})
        start = len(series)
        for d in range(int(round(soak_days))):
            series.append({"day": start + d, "phase": "SOAK", "oil_rate_bopd": 0.0,
                           "temperature_c": None, "viscosity_cp": None, "cum_oil_bbl": 0.0})

    cum = 0.0
    best_avg, best_day, best_cum = -1.0, 0, 0.0
    thermal_limit_day = None
    peak_rate = 0.0
    prod_rates = []
    for d in range(max_production_days):
        snap = tp.twin_snapshot(_with(state, css_phase="PRODUCTION", days_in_phase=float(d)))
        q = snap["estimated_oil_production_bopd"]
        peak_rate = max(peak_rate, q)
        cum += q
        prod_rates.append(q)
        avg = cum / (downtime + d + 1)
        if avg > best_avg + 1e-9:
            best_avg, best_day, best_cum = avg, d + 1, cum
        if thermal_limit_day is None and q <= cold_rate * COLD_RATE_MARGIN:
            thermal_limit_day = d + 1
        if include_series:
            series.append({
                "day": int(round(downtime)) + d, "phase": "PRODUCTION",
                "oil_rate_bopd": round(q, 3),
                "temperature_c": snap["estimated_temperature_c"],
                "viscosity_cp": snap["estimated_viscosity_cp"],
                "cum_oil_bbl": round(cum, 1),
            })

    cycle_days = downtime + best_day
    steam = max(state.steam_volume_t, 0.0)
    sor_t = steam / best_cum if best_cum > 0 else None
    sor_cwe = steam * BBL_CWE_PER_T / best_cum if best_cum > 0 else None
    incremental = best_cum - cold_rate * cycle_days

    return {
        "well_id": state.well_id,
        "inputs": {
            "steam_volume_t": state.steam_volume_t,
            "steam_injection_pressure_bar": state.steam_injection_pressure_bar,
            "soak_time_h": state.soak_time_h,
            "spm": state.spm,
            "stroke_in": state.stroke_in,
        },
        "injection_days": round(inj_days, 2),
        "soak_days": round(soak_days, 2),
        "cold_oil_rate_bopd": round(cold_rate, 3),
        "peak_oil_rate_bopd": round(peak_rate, 3),
        "optimal_cutoff_production_day": best_day,
        "thermal_benefit_limit_day": thermal_limit_day,
        "cycle_length_days": round(cycle_days, 2),
        "cycle_oil_bbl": round(best_cum, 1),
        "incremental_oil_bbl": round(incremental, 1),
        "average_cycle_rate_bopd": round(best_avg, 3),
        "cycle_sor_t_per_bbl": round(sor_t, 4) if sor_t is not None else None,
        "cycle_sor_cwe": round(sor_cwe, 3) if sor_cwe is not None else None,
        "cutoff_rate_bopd": round(prod_rates[best_day - 1], 3) if prod_rates else 0.0,
        "series": series,
        "explanation": (
            f"{inj_days:.1f} d injection + {soak_days:.1f} d soak, then production declines from "
            f"{peak_rate:.1f} toward the cold rate {cold_rate:.1f} bopd as the heated zone cools. "
            f"Average cycle rate peaks at {best_avg:.1f} bopd on production day {best_day}: "
            f"cut off and re-steam then (cycle {cycle_days:.0f} d, {best_cum:.0f} bbl, "
            + (f"SOR {sor_cwe:.2f} bbl CWE/bbl)." if sor_cwe is not None else "SOR undefined).")
        ),
        "prototype_disclaimer": tp.PROTOTYPE_DISCLAIMER,
    }


def plan_cycle(state, steam_grid=None, soak_grid=None, sor_limit: float = SOR_CWE_LIMIT) -> dict:
    """Search steam volume x soak time; each candidate uses its own optimal cut-off."""
    steam_grid = steam_grid or PLAN_STEAM_T
    soak_grid = soak_grid or PLAN_SOAK_H
    current = simulate_cycle(state, include_series=False)
    candidates = []
    for steam in steam_grid:
        for soak in soak_grid:
            res = simulate_cycle(_with(state, steam_volume_t=steam, soak_time_h=soak),
                                 include_series=False)
            feasible = res["cycle_sor_cwe"] is not None and res["cycle_sor_cwe"] <= sor_limit
            candidates.append({
                "steam_volume_t": steam,
                "soak_time_h": soak,
                "optimal_cutoff_production_day": res["optimal_cutoff_production_day"],
                "cycle_length_days": res["cycle_length_days"],
                "average_cycle_rate_bopd": res["average_cycle_rate_bopd"],
                "cycle_oil_bbl": res["cycle_oil_bbl"],
                "incremental_oil_bbl": res["incremental_oil_bbl"],
                "cycle_sor_cwe": res["cycle_sor_cwe"],
                "feasible": feasible,
            })
    ranked = sorted(
        candidates,
        key=lambda c: (not c["feasible"], -c["average_cycle_rate_bopd"],
                       c["cycle_sor_cwe"] if c["cycle_sor_cwe"] is not None else float("inf")),
    )
    best = ranked[0]
    gain = best["average_cycle_rate_bopd"] - current["average_cycle_rate_bopd"]
    return {
        "well_id": state.well_id,
        "sor_limit_cwe": sor_limit,
        "current": {k: v for k, v in current.items() if k != "series"},
        "recommended": best,
        "average_rate_gain_bopd": round(gain, 3),
        "candidates": ranked,
        "candidates_evaluated": len(candidates),
        "explanation": (
            f"Best plan: {best['steam_volume_t']:.0f} t steam, {best['soak_time_h']:.0f} h soak, "
            f"cut off after {best['optimal_cutoff_production_day']} production days -> "
            f"{best['average_cycle_rate_bopd']:.1f} bopd cycle-average "
            f"({gain:+.1f} vs current plan), SOR {best['cycle_sor_cwe']} bbl CWE/bbl "
            f"(limit {sor_limit})."
        ),
        "prototype_disclaimer": tp.PROTOTYPE_DISCLAIMER,
    }
