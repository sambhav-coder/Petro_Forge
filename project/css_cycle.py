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

# ---------------- Multi-cycle CSS intelligence ----------------
# Sequential cycles with explicit cycle-to-cycle state propagation. Only
# quantities the Block 2 prototype model already supports are carried:
#   reservoir_pressure_bar  declines with cumulative oil withdrawn
#                           (pressure depletion, prototype linkage)
#   reservoir_temperature_c baseline carries a fraction of the previous
#                           cycle's peak heated temperature (residual
#                           heat, prototype linkage)
# Both linkage coefficients are [PROTO]: explicit, documented, and NOT
# Baghewala-calibrated. No SCADA-learned decline is claimed.
PRESSURE_DEPLETION_BAR_PER_BBL = 0.00002  # [PROTO] ~0.06 bar per 3000 bbl cycle
HEAT_CARRYOVER_FRAC = 0.15                # [PROTO] residual-heat fraction of peak lift
MAX_MULTICYCLE = 6                        # cap: response is deterministic, not validated
MULTI_MODE_LABEL = "PROTOTYPE_MULTICYCLE"
MULTI_POLICY = ("Recommended under current prototype model: best cycle-average "
                "oil rate under the SOR ceiling on the propagated state. "
                "Not claimed globally optimal; not field-validated.")


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


def historical_css_context(observations: list) -> dict:
    """Explicit historical-data state for multi-cycle planning.

    Public Baghewala CSS records are sparse event reports (month-level
    precision, no rate series), so they can count prior cycles but can
    never calibrate a cycle-to-cycle response model.
    """
    css_obs = [o for o in observations
               if getattr(o, "variable", None) == "css_event"]
    return {
        "prior_css_events": len(css_obs),
        "usable_response_data": False,
        "status": "INSUFFICIENT_DATA",
        "note": ("Public CSS records are sparse event reports (month precision, "
                 "no production-rate series): enough to count prior cycles, "
                 "insufficient to learn cycle-to-cycle response. The multi-cycle "
                 "simulation below uses prototype physics only."),
    }


def _propagate(cur, cycle_oil_bbl: float, peak_temp_c: float, virgin_temp_c: float) -> dict:
    """Cycle N response -> cycle N+1 starting state (prototype linkage)."""
    new_pressure = max(cur.reservoir_pressure_bar
                       - PRESSURE_DEPLETION_BAR_PER_BBL * cycle_oil_bbl, 0.0)
    new_baseline = virgin_temp_c + HEAT_CARRYOVER_FRAC * (peak_temp_c - virgin_temp_c)
    return {"reservoir_pressure_bar": round(new_pressure, 3),
            "reservoir_temperature_c": round(new_baseline, 3)}


def simulate_multicycle(state, cycles: int = 3, steam_grid=None,
                        soak_grid=None, sor_limit: float = SOR_CWE_LIMIT,
                        historical_observations: list = None) -> dict:
    """Sequential CSS cycles with propagated reservoir state. Deterministic.

    Each cycle is planned (plan_cycle) on the state left by the previous
    cycle, then simulated; pressure depletes with oil withdrawn and the
    next baseline carries residual heat. Identical input -> identical output.
    """
    if not isinstance(cycles, int) or isinstance(cycles, bool):
        raise ValueError(f"cycles must be an integer 1..{MAX_MULTICYCLE}")
    if not 1 <= cycles <= MAX_MULTICYCLE:
        raise ValueError(f"cycles must be within 1..{MAX_MULTICYCLE}")
    if sor_limit is not None and not (sor_limit > 0):
        raise ValueError("sor_limit_cwe must be positive")

    virgin_temp = float(state.reservoir_temperature_c)
    cur = state
    cum_oil, cum_steam = 0.0, 0.0
    out_cycles = []
    for n in range(1, cycles + 1):
        state_in = {"reservoir_pressure_bar": round(float(cur.reservoir_pressure_bar), 3),
                    "reservoir_temperature_c": round(float(cur.reservoir_temperature_c), 3)}
        plan = plan_cycle(cur, steam_grid, soak_grid, sor_limit)
        rec = plan["recommended"]
        cyc = simulate_cycle(
            _with(cur, steam_volume_t=rec["steam_volume_t"],
                  soak_time_h=rec["soak_time_h"]),
            include_series=False)
        peak_temp = tp.effective_temperature_c(
            float(cur.reservoir_temperature_c), rec["steam_volume_t"],
            float(cur.steam_injection_pressure_bar), rec["soak_time_h"],
            "PRODUCTION", 0.0)
        cum_oil += cyc["cycle_oil_bbl"]
        cum_steam += rec["steam_volume_t"]
        state_out = _propagate(cur, cyc["cycle_oil_bbl"], float(peak_temp), virgin_temp)
        out_cycles.append({
            "cycle_number": n,
            "planned": {"steam_volume_t": rec["steam_volume_t"],
                        "soak_time_h": rec["soak_time_h"],
                        "optimal_cutoff_production_day": rec["optimal_cutoff_production_day"]},
            "state_in": state_in,
            "peak_heated_temperature_c": round(float(peak_temp), 2),
            "cycle_oil_bbl": cyc["cycle_oil_bbl"],
            "cycle_steam_t": rec["steam_volume_t"],
            "cycle_length_days": cyc["cycle_length_days"],
            "average_cycle_rate_bopd": cyc["average_cycle_rate_bopd"],
            "cycle_sor_t_per_bbl": cyc["cycle_sor_t_per_bbl"],
            "cycle_sor_cwe": cyc["cycle_sor_cwe"],
            "incremental_oil_bbl": cyc["incremental_oil_bbl"],
            "state_out": state_out,
        })
        cur = _with(cur, reservoir_pressure_bar=state_out["reservoir_pressure_bar"],
                    reservoir_temperature_c=state_out["reservoir_temperature_c"],
                    steam_volume_t=rec["steam_volume_t"],
                    soak_time_h=rec["soak_time_h"])

    cum_sor_t = cum_steam / cum_oil if cum_oil > 0 else None
    cum_sor_cwe = cum_steam * BBL_CWE_PER_T / cum_oil if cum_oil > 0 else None

    # Next-cycle recommendation on the propagated state.
    nxt = plan_cycle(cur, steam_grid, soak_grid, sor_limit)
    nrec = nxt["recommended"]
    last_avg = out_cycles[-1]["average_cycle_rate_bopd"]
    reasons = [
        f"Cycle {cycles + 1} planned on the propagated state "
        f"(pressure {cur.reservoir_pressure_bar:.2f} bar after "
        f"{cum_oil:.0f} bbl withdrawn; baseline {cur.reservoir_temperature_c:.1f} C "
        f"with residual heat vs virgin {virgin_temp:.1f} C).",
        f"Recommended {nrec['steam_volume_t']:.0f} t steam, {nrec['soak_time_h']:.0f} h soak, "
        f"cut off after {nrec['optimal_cutoff_production_day']} production days -> "
        f"expected cycle-average {nrec['average_cycle_rate_bopd']:.1f} bopd "
        f"({nrec['average_cycle_rate_bopd'] - last_avg:+.1f} vs cycle {cycles}), "
        f"SOR {nrec['cycle_sor_cwe']} bbl CWE/bbl (limit {sor_limit}).",
        f"Cumulative after {cycles} simulated cycles: {cum_oil:.0f} bbl oil, "
        f"{cum_steam:.0f} t steam" + (f", SOR {cum_sor_cwe:.2f} bbl CWE/bbl." if cum_sor_cwe is not None else "."),
        MULTI_POLICY,
    ]

    return {
        "well_id": state.well_id,
        "mode": MULTI_MODE_LABEL,
        "data_mode": "PROTOTYPE_SIMULATION",
        "cycles_requested": cycles,
        "sor_limit_cwe": sor_limit,
        "initial_state": {
            "reservoir_pressure_bar": round(float(state.reservoir_pressure_bar), 3),
            "reservoir_temperature_c": round(float(state.reservoir_temperature_c), 3),
        },
        "linkage": {
            "pressure_depletion_bar_per_bbl": PRESSURE_DEPLETION_BAR_PER_BBL,
            "heat_carryover_frac": HEAT_CARRYOVER_FRAC,
            "note": "Prototype linkage coefficients, NOT Baghewala-calibrated.",
        },
        "historical_context": historical_css_context(historical_observations or []),
        "cycles": out_cycles,
        "cumulative": {
            "cycles_simulated": cycles,
            "total_oil_bbl": round(cum_oil, 1),
            "total_steam_t": round(cum_steam, 1),
            "cumulative_sor_t_per_bbl": round(cum_sor_t, 4) if cum_sor_t is not None else None,
            "cumulative_sor_cwe": round(cum_sor_cwe, 3) if cum_sor_cwe is not None else None,
        },
        "recommendation": {
            "next_cycle_number": cycles + 1,
            "steam_volume_t": nrec["steam_volume_t"],
            "soak_time_h": nrec["soak_time_h"],
            "optimal_cutoff_production_day": nrec["optimal_cutoff_production_day"],
            "expected_average_rate_bopd": nrec["average_cycle_rate_bopd"],
            "expected_cycle_sor_cwe": nrec["cycle_sor_cwe"],
            "reasons": reasons,
            "policy": MULTI_POLICY,
        },
        "limitations": [
            "Prototype physics only: no Baghewala cycle-response history exists publicly.",
            "Linkage coefficients are explicit prototype choices, not field-calibrated.",
            "No uncertainty bands are computed.",
            "Public CSS records are sparse events; usable_response_data is always false.",
        ],
        "prototype_disclaimer": tp.PROTOTYPE_DISCLAIMER,
    }
