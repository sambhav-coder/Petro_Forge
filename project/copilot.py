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


# ---------------- 2.0: speech-aware text + presentation planner ----------------

# Abbreviations are letter-spaced for understandable TTS; units stay English.
_SPEECH_SUBS = [
    ("bopd", "B O P D"),
    ("SPM", "S P M"),
    ("SOR", "S O R"),
    ("CSS", "C S S"),
    ("SRP", "S R P"),
    ("VFD", "V F D"),
    ("BGW", "B G W"),
    ("kWh", "kilowatt hour"),
    ("CWE", "C W E"),
]


def to_speech_text(text: str) -> str:
    """Prepare narration for speech: normalize, expand abbreviations, strip IDs/JSON.

    Never speaks raw JSON, internal IDs, or ISO timestamps as narration.
    """
    import re
    t = re.sub(r"\s+", " ", text or "").strip()
    # Drop JSON fragments, ISO timestamps and long hex IDs (UI shows them, speech skips them).
    t = re.sub(r"\{[^{}]*\}", "", t)
    t = re.sub(r"\d{4}-\d{2}-\d{2}T\d[\d:.\-+]*Z?", "", t)
    t = re.sub(r"\b(cpl-|sim-|evt-|alert-)[0-9a-fA-F\-]{4,}\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    for raw, spoken in _SPEECH_SUBS:
        t = re.sub(rf"\b{re.escape(raw)}\b", spoken, t)
    return t[:MAX_NARRATION_CHARS]


def chunk_text(text: str, max_len: int = 220) -> List[str]:
    """Split narration into short speakable segments at sentence boundaries."""
    import re
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]
    chunks: List[str] = []
    buf = ""
    for s in sentences:
        if len(s) > max_len:
            # Hard-split very long sentences on commas/semicolons.
            parts = [p.strip() for p in re.split(r"[,;]\s+", s) if p.strip()]
            for p in parts:
                if len(buf) + len(p) + 2 <= max_len:
                    buf = (buf + " " + p).strip()
                else:
                    if buf:
                        chunks.append(buf)
                    buf = p
            continue
        if len(buf) + len(s) + 1 <= max_len:
            buf = (buf + " " + s).strip()
        else:
            if buf:
                chunks.append(buf)
            buf = s
    if buf:
        chunks.append(buf)
    return chunks or [text[:max_len]]


def _fnum(value: Any, digits: int = 1) -> str:
    try:
        if value is None:
            return "unavailable"
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "unavailable"


# component_focus -> frontend camera preset + isolate target.
_FOCUS_CAMERA = {
    "well": "WELL", "wellhead": "WELL", "srp": "PUMP", "rod": "PUMP",
    "pump": "PUMP", "wellbore": "WELLBORE", "reservoir": "RESERVOIR",
    "thermal": "RESERVOIR", "overview": "FIELD", "panel": "FIELD",
}

# stage -> Inspector tab that must be visible for the chapter (single source:
# narration, camera AND panel come from the same segment spec).
_PANEL_BY_STAGE = {
    "welcome": "OVERVIEW", "model": "OVERVIEW", "telemetry": "TELEMETRY",
    "hybrid": "HYBRID", "srp": "SRP", "css": "CYCLE", "alerts": "OVERVIEW",
    "simulation": "WHAT-IF", "optimization": "OPTIMIZATION", "summary": "OVERVIEW",
}


def build_presentation_plan(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Build the ordered 10-chapter presentation from validated evidence.

    Chapters unavailable for this well are marked available=False with an
    honest unavailable_reason (never fictional measurements). Pure function of
    ctx: deterministic and testable.
    """
    well_id = ctx.get("well_id", "?")
    tele = ctx.get("telemetry") or {}
    twin = ctx.get("twin") or {}
    hybrid = ctx.get("hybrid") if isinstance(ctx.get("hybrid"), dict) else None
    dyn = ctx.get("dynacard") if isinstance(ctx.get("dynacard"), dict) else None
    cycle = ctx.get("cycle") if isinstance(ctx.get("cycle"), dict) else None
    multi = ctx.get("multi") if isinstance(ctx.get("multi"), dict) else None
    opt = ctx.get("optimization") if isinstance(ctx.get("optimization"), dict) else None
    alerts = ctx.get("alerts") or []
    analytics = ctx.get("analytics") if isinstance(ctx.get("analytics"), dict) else None
    hist_n = ctx.get("history_count", 0)
    has_tele = bool(tele)
    prov = presentation_provenance(ctx.get("provenance"))

    segs: List[Dict[str, Any]] = []

    def seg(seq: int, stage: str, title: str, text: str, focus: str,
            values: Optional[List[Dict[str, Any]]] = None,
            available: bool = True, reason: str = "",
            simulation_id: Optional[str] = None) -> None:
        spoken = to_speech_text(text)
        segs.append({
            "segment_id": f"SEG-{seq:02d}", "well_id": well_id, "sequence": seq,
            "stage": stage, "title": title,
            "narration_text": text[:1200], "spoken_text": spoken,
            "speech_chunks": chunk_text(spoken),
            "evidence_refs": [f"SEG-{seq:02d}-evidence"],
            "data_provenance": prov,
            "component_focus": focus,
            "camera_action": _FOCUS_CAMERA.get(focus, "FIELD"),
            "panel_tab": _PANEL_BY_STAGE.get(stage, "OVERVIEW"),
            "panel_section": f"copilot-{stage}",
            "related_values": values or [],
            "animation_action": "srp_cycle" if focus in ("srp", "rod", "pump") and stage == "srp" else "highlight",
            "simulation_id": simulation_id,
            "duration_hint_s": max(6, min(40, 6 + len(spoken) // 14)),
            "completion_condition": "audio_end",
            "available": available, "unavailable_reason": reason,
        })

    # Ch1 welcome
    basis = ("measured telemetry" if has_tele else
             "public record only (no live telemetry)" if ctx.get("public") else
             "limited evidence")
    seg(1, "welcome", "Welcome and well identification",
        f"Namaste, engineer. Main PetroForge AI Co-Pilot hoon. Aaj hum well {well_id} "
        f"ka complete analysis karenge. Ye session {basis} par based hai. "
        f"Main Hybrid Twin, SRP pumping, CSS cycle, alerts, simulation aur optimization "
        f"ek-ek karke explain karunga. Saare simulated numbers SIMULATION-labelled rahenge.",
        "overview")
    # Ch2 model overview
    seg(2, "model", "3D well model overview",
        "Saamne aapka 3D digital twin hai — ye schematic visualization hai, field-calibrated "
        "geometry nahi. Upar surface pumping unit, beech me wellbore with rod string, neeche "
        "pump, aur sabse neeche reservoir thermal zone. Main jiss component ki baat karunga, "
        "camera wahin focus karega.", "overview")
    # Ch3 telemetry
    if has_tele:
        calib_hint = ""
        if analytics and isinstance(analytics.get("calibration"), dict):
            cal = analytics["calibration"]
            calib_hint = (f" History calibration {cal.get('status')} over "
                          f"{cal.get('points')} points. " if cal.get("status") else "")
        seg(3, "telemetry", "Live telemetry and operating context",
            f"Current readings: phase {tele.get('css_phase')}, production "
            f"{_fnum(tele.get('oil_rate_bopd'))} bopd, SPM {_fnum(tele.get('spm'))}, "
            f"stroke {_fnum(tele.get('stroke_in'), 0)} inch, steam "
            f"{_fnum(tele.get('steam_volume_t'), 0)} tonnes, soak "
            f"{_fnum(tele.get('soak_time_h'), 0)} hours. Timestamp panel me hai. "
            f"History me {hist_n} readings available hain. {calib_hint}".strip(),
            "wellhead",
            [{"name": k, "value": tele.get(k), "provenance": OBSERVED}
             for k in ("oil_rate_bopd", "spm", "stroke_in", "steam_volume_t")])
    else:
        seg(3, "telemetry", "Live telemetry and operating context",
            "Is well ke liye current telemetry unavailable hai. Isliye aage ke chapters "
            "historical, synthetic ya model estimates par based honge — sab clearly labelled.",
            "wellhead", available=False,
            reason="no telemetry for this well")
    # Ch4 hybrid
    if hybrid and has_tele:
        cal = (hybrid.get("calibration") or {})
        div = (hybrid.get("divergence") or {})
        pred = ((hybrid.get("physics") or {}).get("prediction") or {})
        seg(4, "hybrid", "Hybrid Digital Twin",
            f"Hybrid Twin: physics prediction {_fnum(pred.get('oil_production_bopd'))} bopd, "
            f"calibration {cal.get('status', 'unknown')}, divergence "
            f"{_fnum(div.get('value_bopd'))} bopd ({div.get('severity') or 'n/a'}). "
            f"Uncertainty {((hybrid.get('uncertainty') or {}).get('status')) or 'UNAVAILABLE'} — "
            f"koi confidence percentage invent nahi kiya gaya.", "well",
            [{"name": "hybrid_oil_bopd", "value": pred.get("oil_production_bopd"),
              "provenance": PHYSICS_PREDICTION}])
    else:
        seg(4, "hybrid", "Hybrid Digital Twin",
            "Hybrid Twin ke liye telemetry chahiye. Public-only ya telemetry-less well par "
            "ye chapter skip hota hai — calibrated prediction invent nahi karenge.",
            "well", available=False, reason="hybrid requires telemetry")
    # Ch5 SRP
    if dyn and has_tele:
        perf = dyn.get("pump_performance") or {}
        eff = (perf.get("efficiency") or {})
        seg(5, "srp", "SRP operation and pumping cycle",
            f"Ab SRP dekhte hain. Surface pumping unit upstroke me rod assembly ko upar kheenchta "
            f"hai, downstroke me neeche laata hai. Dynacard diagnosis: {dyn.get('primary_diagnosis')}. "
            f"Pump fillage {_fnum(dyn.get('estimated_pump_fillage'))}, efficiency "
            f"{_fnum(eff.get('value'))} ({eff.get('status') or 'n/a'}). Ye simplified animation hai — "
            f"physically calibrated rod-string simulation nahi.", "pump",
            [{"name": "fillage", "value": dyn.get("estimated_pump_fillage"), "provenance": DERIVED}])
    else:
        seg(5, "srp", "SRP operation and pumping cycle",
            "SRP dynacard ke liye telemetry chahiye. Data unavailable hai, isliye pump "
            "diagnostics skip karke aage badhte hain.", "pump",
            available=False, reason="dynacard requires telemetry")
    # Ch6 CSS
    if cycle and has_tele:
        multi_hint = ""
        if multi and isinstance(multi.get("recommendation"), dict):
            rec = multi["recommendation"]
            multi_hint = (f" Multi-cycle outlook: next cycle "
                          f"{_fnum(rec.get('steam_volume_t'), 0)} tonnes steam, "
                          f"{_fnum(rec.get('soak_time_h'), 0)} hours soak. ")
        seg(6, "css", "CSS cycle",
            f"CSS cycle: injection {_fnum(cycle.get('injection_days'), 0)} days, soak "
            f"{_fnum(cycle.get('soak_days'), 0)} days, optimal cut-off day "
            f"{cycle.get('optimal_cutoff_production_day')}, cycle SOR "
            f"{_fnum(cycle.get('cycle_sor_t_per_bbl'), 4)}.{multi_hint}"
            f"Prototype thermal assumptions [PROTO] apply hote hain.", "reservoir",
            [{"name": "cycle_sor", "value": cycle.get("cycle_sor_t_per_bbl"), "provenance": PHYSICS_PREDICTION}])
    else:
        seg(6, "css", "CSS cycle",
            "CSS cycle analysis ke liye sufficient inputs nahi hain. Is chapter ko skip "
            "karke alerts aur simulation par chalte hain.", "reservoir",
            available=False, reason="CSS context unavailable")
    # Ch7 alerts
    if alerts:
        seg(7, "alerts", "Alerts and diagnostics",
            f"{len(alerts)} active alerts hain. Sabse important: "
            + "; ".join(f"{a.get('title', a.get('type', '?'))} [{a.get('severity')}]"
                        for a in alerts[:3])[:400]
            + ". Ye screening indicators hain — confirmed equipment failure nahi.",
            "panel")
    else:
        seg(7, "alerts", "Alerts and diagnostics",
            "Koi active alert nahi hai. Ye healthy hone ka proof nahi — sirf current "
            "screening me kuch trigger nahi hua.", "panel")
    # Ch8 simulation (planned; executed by orchestrator when telemetry exists)
    if has_tele and twin:
        seg(8, "simulation", "Autonomous simulation",
            f"Baseline {_fnum(twin.get('estimated_oil_production_bopd'))} bopd ke against ek bounded "
            f"SPM scenario run karenge. Jo inputs change honge aur jo outputs improve ya worsen "
            f"honge, wahi compare karenge. Agar engine error dega, to failure honestly report hoga.",
            "pump")
    else:
        seg(8, "simulation", "Autonomous simulation",
            "Telemetry ke bina simulation possible nahi — required inputs missing hain. "
            "Isliye simulation skip.", "pump", available=False,
            reason="simulation requires telemetry")
    # Ch9 optimization
    if opt and has_tele:
        rec = opt.get("recommended") or {}
        rec_in = rec.get("inputs") or {}
        seg(9, "optimization", "Optimization and Pareto results",
            f"Optimizer ne {opt.get('scenarios_evaluated')} scenarios evaluate kiye. Recommended: "
            f"{_fnum(rec.get('estimated_oil_production_bopd'))} bopd at "
            f"{_fnum(rec_in.get('steam_volume_t'), 0)} tonnes steam, "
            f"{_fnum(rec_in.get('soak_time_h'), 0)} hours soak, SPM "
            f"{_fnum(rec_in.get('spm'))}. Pareto frontier me "
            f"{opt.get('pareto_count')} non-dominated candidates hain — production vs SOR vs "
            f"energy vs risk ka trade-off. Ye prototype recommendation hai, field-validated nahi.",
            "overview")
    else:
        seg(9, "optimization", "Optimization and Pareto results",
            "Optimization ke liye valid inputs nahi mile, isliye ye chapter skip ho raha hai.",
            "overview", available=False, reason="optimizer inputs unavailable")
    # Ch10 summary
    seg(10, "summary", "Final engineering summary",
        f"Summary: findings panel me evidence references ke saath hain. "
        f"{'Calibration ' + str((hybrid.get('calibration') or {}).get('status')) + ' hai. ' if hybrid else ''}"
        f"Simulated values real well par apply nahi hue. Sabse useful next step: missing data "
        f"check karke WHAT-IF me alternate scenario compare karein. Dhanyavaad.",
        "overview")

    completed = sum(1 for s in segs if s["available"])
    skipped = [s for s in segs if not s["available"]]
    return {"well_id": well_id, "segments": segs,
            "coverage": {"total": len(segs), "available": completed,
                         "skipped": [{"segment_id": s["segment_id"], "title": s["title"],
                                      "reason": s["unavailable_reason"]} for s in skipped]},
            "simulation_only": True}
