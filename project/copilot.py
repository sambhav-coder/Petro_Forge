"""PetroForge AI Co-Pilot — evidence, findings, narration and safety core.

Simulation-only orchestration over the EXISTING engines (twin_physics,
hybrid_twin, srp_dynacard/srp_performance, css_cycle, twin_optimize,
analytics, ml.synthetic_hazard). This module never touches control systems,
never writes production telemetry/history, and never persists scenarios.

Provenance: existing source-of-truth names (PUBLIC_FIELD_RECORD,
SYNTHETIC_BAGHEWALA, BAGHEWALA_FIELD, LIVE_TELEMETRY, ...) are preserved and
mapped to presentation categories for the UI. Missing values stay missing
(never zero-filled).
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, List, Optional

# Presentation categories (UI labels). Source names are preserved alongside.
OBSERVED = "OBSERVED"
HISTORICAL = "HISTORICAL"
DERIVED = "DERIVED"
PHYSICS_PREDICTION = "PHYSICS_PREDICTION"
CALIBRATED_TWIN = "CALIBRATED_TWIN"
SIMULATION = "SIMULATION"
SYNTHETIC_DEMO = "SYNTHETIC_DEMO"
UNAVAILABLE = "UNAVAILABLE"

SIMULATION_ONLY_NOTE = (
    "Simulation-only: values labelled SIMULATION are hypothetical engine outputs. "
    "No field control was issued and no production data was written."
)

# Conservative computation budgets for autonomous sessions.
MAX_AUTO_SIMS = 3
MAX_TOOL_CALLS = 4
MAX_PARALLEL = 4
SESSION_BUDGET_S = 120.0
MAX_NARRATION_CHARS = 4000

# Tool allowlist (logical capabilities bound to existing verified endpoints).
ALLOWED_TOOLS = (
    "get_well_evidence",
    "get_hybrid_twin",
    "get_srp_diagnostics",
    "get_css_context",
    "run_css_simulation",
    "run_srp_scenario",
    "run_optimizer",
    "get_alerts",
)

BOUNDS = {
    "steam_volume_t": (0.0, 100000.0),
    "steam_injection_pressure_bar": (0.0, 300.0),
    "soak_time_h": (0.0, 720.0),
    "spm": (0.0, 20.0),
    "stroke_in": (0.0, 300.0),
}


def presentation_provenance(source: Optional[str]) -> str:
    """Map a source-of-truth provenance name to a UI presentation category."""
    s = (source or "").upper()
    if "SYNTHETIC" in s:
        return SYNTHETIC_DEMO
    if s in ("BAGHEWALA_FIELD", "PUBLIC_REFERENCE", "HISTORICAL"):
        return HISTORICAL
    if s in ("LIVE_TELEMETRY", "MEASURED", "OBSERVED"):
        return OBSERVED
    if s in ("CALIBRATED", "CALIBRATED_TWIN"):
        return CALIBRATED_TWIN
    if "PHYSICS" in s or "PROTO" in s:
        return PHYSICS_PREDICTION
    if not s or "UNAVAILABLE" in s or "INSUFFICIENT" in s:
        return UNAVAILABLE
    return DERIVED


def llm_mode() -> Dict[str, str]:
    """Provider abstraction status. Credentials stay server-side; default fallback."""
    provider = (os.environ.get("COPILOT_LLM_PROVIDER") or "").strip().lower()
    model = (os.environ.get("COPILOT_LLM_MODEL") or "").strip()
    has_key = bool((os.environ.get("COPILOT_LLM_API_KEY") or "").strip())
    if provider and provider != "none" and has_key:
        return {"mode": "LLM", "provider": provider, "model": model or "default",
                "note": "Server-side provider; keys never exposed to the client."}
    return {"mode": "FALLBACK_TEMPLATE",
            "provider": "none",
            "model": "deterministic-templates",
            "note": "No LLM credentials configured: narration is generated from "
                    "validated backend findings via labelled templates (not LLM output)."}


def new_session_id() -> str:
    return f"cpl-{uuid.uuid4().hex[:12]}"


def validate_scenario(overrides: Dict[str, Any]) -> List[str]:
    """Validate simulation overrides against existing API bounds. Returns error list."""
    errors: List[str] = []
    if not isinstance(overrides, dict) or not overrides:
        return ["empty scenario: provide at least one override"]
    allowed = set(BOUNDS) | {"vfd_percent", "water_cut_percent", "days_in_phase", "css_phase"}
    for key, value in overrides.items():
        if key not in allowed:
            errors.append(f"unknown field '{key}'")
            continue
        if key in BOUNDS:
            try:
                num = float(value)
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be numeric")
                continue
            lo, hi = BOUNDS[key]
            if not (lo <= num <= hi):
                errors.append(f"'{key}'={num} outside bounds [{lo}, {hi}]")
    return errors


def build_findings(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build structured findings from validated evidence context (no invented numbers)."""
    findings: List[Dict[str, Any]] = []
    well_id = context.get("well_id", "?")
    tele = context.get("telemetry") or {}
    twin = context.get("twin") or {}
    hybrid = context.get("hybrid") or {}
    dyn = context.get("dynacard") or {}
    alerts = context.get("alerts") or []
    calib = (hybrid.get("calibration") or {}) if isinstance(hybrid, dict) else {}
    diverg = (hybrid.get("divergence") or {}) if isinstance(hybrid, dict) else {}

    def add(fid: str, title: str, severity: str, explanation: str,
            values: Optional[List[Dict[str, Any]]] = None,
            provenance: str = DERIVED, limitation: str = "",
            simulated: bool = False) -> None:
        findings.append({
            "finding_id": fid, "well_id": well_id, "title": title,
            "severity": severity, "explanation": explanation,
            "evidence_refs": [fid + "-evidence"],
            "values": values or [], "provenance": provenance,
            "confidence": "UNAVAILABLE",
            "engineering_interpretation": explanation,
            "recommended_next": "See transcript for next investigation step.",
            "simulated": simulated, "simulation_id": None,
            "limitations": limitation or "Prototype physics [PROTO]; not field-validated.",
        })

    if tele:
        add("F-BASELINE", "Baseline operating state", "INFO",
            f"Well {well_id} phase {tele.get('css_phase')} at "
            f"{tele.get('oil_rate_bopd')} bopd (measured telemetry).",
            [{"name": "oil_rate_bopd", "value": tele.get("oil_rate_bopd"),
              "unit": "bopd", "provenance": OBSERVED}],
            provenance=OBSERVED)
    else:
        add("F-NO-TELEMETRY", "No current telemetry", "HIGH",
            "Current telemetry unavailable; only historical/synthetic/model "
            "evidence may be shown with labels.",
            provenance=UNAVAILABLE,
            limitation="Cannot establish a measured baseline without telemetry.")

    if twin:
        add("F-TWIN", "Physics twin estimate", "INFO",
            f"Twin predicts {twin.get('estimated_oil_production_bopd')} bopd, "
            f"limiting factor {twin.get('production_limiting_factor')}.",
            [{"name": "twin_oil_bopd", "value": twin.get("estimated_oil_production_bopd"),
              "unit": "bopd", "provenance": PHYSICS_PREDICTION}],
            provenance=PHYSICS_PREDICTION,
            limitation="Deterministic prototype [PROTO]; uncalibrated unless stated.")
    if calib:
        status = calib.get("status", "INSUFFICIENT_DATA")
        add("F-CALIB", "Calibration status", "INFO",
            f"Calibration: {status}. {calib.get('explanation', '')}"[:400],
            provenance=CALIBRATED_TWIN if status == "CALIBRATED" else UNAVAILABLE)
    if diverg and diverg.get("status") not in (None, "", "OK"):
        add("F-DIVERG", "Model vs measurement divergence", "MODERATE",
            f"Divergence {diverg.get('value_bopd')} bopd "
            f"({diverg.get('severity')}). {diverg.get('note', '')}"[:400],
            provenance=DERIVED)
    perf = (dyn.get("pump_performance") or {}) if isinstance(dyn, dict) else {}
    if dyn:
        add("F-SRP", "SRP diagnostics", "INFO",
            f"Dynacard: {dyn.get('primary_diagnosis')}. "
            f"Fillage {dyn.get('estimated_pump_fillage')}.",
            provenance=DERIVED,
            limitation=str((perf.get("prototype_note") or "Prototype dynacard [PROTO]."))[:200])
    if alerts:
        sev = "HIGH" if any(a.get("severity") == "HIGH" for a in alerts) else "MODERATE"
        add("F-ALERTS", f"{len(alerts)} active alert(s)", sev,
            "; ".join(f"{a.get('title', a.get('type', '?'))}" for a in alerts[:3])[:400],
            provenance=OBSERVED)
    ml_ev = hybrid.get("ml_evidence") if isinstance(hybrid, dict) else None
    if isinstance(ml_ev, dict) and ml_ev.get("status") not in (None, "UNAVAILABLE"):
        add("F-ML", "ML hazard evidence (synthetic, separate)", "INFO",
            "Synthetic-hazard demonstration probabilities only; kept separate "
            "from physics results. Not field-validated.",
            provenance=SYNTHETIC_DEMO,
            limitation="Trained on synthetic labels; production_safe=false.")
    return findings


def narrate_hinglish(stage: str, ctx: Dict[str, Any]) -> str:
    """Deterministic Hindi/Hinglish fallback narration (labelled, not LLM)."""
    well = ctx.get("well_id", "selected well")
    phase = (ctx.get("telemetry") or {}).get("css_phase", "unknown phase")
    twin_oil = (ctx.get("twin") or {}).get("estimated_oil_production_bopd", "—")
    templates = {
        "baseline": (
            f"Namaste, engineer. Main {well} ka available data analyze kar raha hoon. "
            f"Current phase {phase} hai. Pehle hum measured readings aur Hybrid Twin "
            f"prediction compare karenge (twin estimate {twin_oil} bopd)."
        ),
        "diagnostics": (
            "Ab SRP performance aur dynacard diagnostics dekhte hain. Load, capacity "
            "aur efficiency ke numbers sirf validated backend output se liye gaye hain; "
            "missing values ko zero nahi banaya gaya."
        ),
        "css": (
            "CSS cycle context check karte hain — injection, soak, production aur "
            "cut-off. Agar sufficient inputs milenge, tabhi bounded simulation chalayenge."
        ),
        "simulation": (
            "Baseline ke against ek bounded simulation run karke proposed scenario ka "
            "difference samjhaunga. Ye sab SIMULATION-labelled hai — real well par "
            "koi setting change nahi hui."
        ),
        "summary": (
            "Summary: findings evidence ke saath panel me hain. Har important claim ke "
            "peeche evidence reference hai. Limitations zaroor padhein — ye prototype "
            "model hai, field-validated nahi."
        ),
    }
    text = templates.get(stage, templates["baseline"])
    return text[:MAX_NARRATION_CHARS]


def answer_fallback(question: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Grounded fallback Q&A: refuses control requests, answers from findings."""
    q = (question or "").lower()
    control_words = ("set pressure", "change spm", "increase steam", "open valve",
                     "scada", "plc", "actuator", "apply to well", "write to")
    if any(w in q for w in control_words):
        return {"answer": (
            "Main physical equipment operate nahi kar sakta. Ye Co-Pilot sirf "
            "simulation aur explanation ke liye hai — koi SCADA/PLC command issue "
            "nahi hota. Aap WHAT-IF simulation compare kar sakte hain."),
            "grounded": True, "mode": "FALLBACK_TEMPLATE", "evidence_refs": []}
    findings = build_findings(ctx)
    top = findings[0]["explanation"] if findings else "Insufficient data."
    return {"answer": (
        f"Aapke sawaal ke context me: {top} Detail findings panel me "
        f"evidence references ke saath hain. Koi number invent nahi kiya gaya."),
        "grounded": True, "mode": "FALLBACK_TEMPLATE",
        "evidence_refs": [f["finding_id"] for f in findings[:3]]}


def started_at() -> float:
    return time.monotonic()
