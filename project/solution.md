# SIH26120 Technical Solution — Baghewala Field Well-to-Surface Digital Twin

**Problem Statement ID:** `SIH26120`
**Title:** Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation (CSS) and Sucker Rod Pump (SRP) Operations for Heavy Oil Wells of Baghewala Field
**Organization:** Oil India Limited · **Theme:** Smart Automation · **Field:** Baghewala, Rajasthan

> This document describes the **implemented prototype**. Every coefficient is labeled
> **[PS]** (taken from the problem statement), **[STD]** (standard unit conversion), or
> **[PROTO]** (prototype/demo assumption — not field-calibrated, not Oil India provided).

---

## 1. Problem Statement

Baghewala Field (Jodhpur Sandstone, Rajasthan) produces heavy crude **[PS: 17–19° API]**
under **[PS]** high viscosity, high asphaltene content, low reservoir pressure, low reservoir
temperature **[PS: 46–48 °C]**, and poor primary-recovery mobility. CSS cycle design and SRP
operation are currently optimized separately from historical experience, causing high SOR,
excess energy use, rod floating / impact loading / pump unsetting / rod failures, and lost
production. The required solution is an AI-enabled well-to-surface Digital Twin that
integrates reservoir, wellbore, and surface systems for monitoring, prediction, and
optimization. This repository implements a **deterministic prototype** of that twin
(56 automated tests passing); trained ML forecasting is explicitly future work.

## 2. Existing Operational Challenge

```
Reservoir (cold, viscous, low pressure)
  → Wellbore (inflow limited by drawdown × mobility)
    → SRP (stroke/SPM lift capacity, fillage losses)
      → Surface (oil rate, SOR, energy)
```

Steam heating thins the oil (mobility ↑ → inflow ↑), but steam costs energy and raises SOR.
The SRP can only lift what the reservoir delivers, and an oversized pump against weak inflow
creates impact loading and unsetting risk. Manual/reactive setpoints on the two sides
create this mismatch. The twin therefore couples **both sides in one calculation**.

## 3. Proposed Digital Twin

```
Telemetry (POST /api/v1/telemetry/ingest, Pydantic-validated)
  ↓
Well State (in-memory WELL_STORE per well_id + SHA-256 audit log)
  ↓
Physics Engine (twin_physics.py — deterministic, unit-aware)
  ↓
Risk Engine (deterministic prototype indicators, NOT ML)
  ↓
Simulation (side-effect-free what-if) / Optimization (243-scenario grid search)
  ↓
Dashboard (project/index.html — real fetch() calls, no mock values)
```

## 4. CSS Representation

Per-well state carries **[PS-derived field names, PROTO ranges are input-safety only]**:
`steam_volume_t` (0–100000), `steam_injection_pressure_bar` (0–300),
`soak_time_h` (0–720), `css_phase` ∈ {INJECTION, SOAK, PRODUCTION, IDLE}.
`soak_time_h` doubles as the representative thermal-exposure duration **[PROTO choice]**.
Phase is visualized, not auto-transitioned (no state machine physics yet).

## 5. Reservoir / Thermal Model (implemented, `twin_physics.py`)

Heating intensity **[PROTO]** blends normalized steam inputs:

```
I = clamp(0.5·V/1000 + 0.5·P/70, 0, 1)      # V in t, P in bar; refs 1000 t / 70 bar [PROTO]
```

Bounded first-order response **[PROTO]**:

```
Heating: T = T_base + 180·I·(1 − exp(−t/72))     # 180 °C max rise, τ = 72 h [PROTO]
Cooling: T = T_base + (T_peak − T_base)·exp(−t/72)
```

`T_base` comes from the well input; the snapshot evaluates heating at `soak_time_h`, and
`IDLE` applies the cooling branch (fallback 48 h) so post-steam cooldown is representable.
Output clamped to [0, 350] °C. No random terms.

## 6. Viscosity / Mobility (prototype approximation — NOT a calibrated PVT model)

Arrhenius-style **[PROTO]** correlation, exponent clamped to ±10, result to [0.1, 100000] cP:

```
μ(T) = 350 · exp(4500·(1/(T+273.15) − 1/(47+273.15))) · clamp(1 − 0.01·(API−18), 0.7, 1.3)
```

Anchors: μ_ref = 350 cP **[PROTO]** at T_ref = 47 °C **[PS: midpoint of 46–48 °C]**,
B = 4500 K **[PROTO]**, API_ref = 18 **[PS: midpoint of 17–19° API]**.
Hotter → thinner; always positive and finite. Mobility proxy **[PROTO]**:

```
mobility = 350 / μ     # = 1 at reference viscosity; dimensionless
```

## 7. Reservoir Inflow (simplified IPR with caps — caps are never removed)

```
q_inflow = 0.8 · max(P_res − P_wh, 0) · mobility,  capped at 5000 bopd
```

J = 0.8 bopd/bar **[PROTO]**. Higher drawdown → higher inflow; P_res ≤ P_wh → exactly
zero (never negative); thicker oil (lower mobility) → lower inflow.

## 8. SRP Model

Positive-displacement proxy **[PROTO]** with standard conversions **[STD]**:

```
Q_theoretical = (π/4·D²) · stroke · SPM · 1440 / 9702        [bopd]
Q_actual      = Q_theoretical · fillage · efficiency
```

D = 2.0 in bore **[PROTO]**; fillage = 0.85 and efficiency = 0.75 **[PROTO fixed defaults,
clearly marked — no measured fillage input exists yet]**; 1440 min/day, 9702 in³/bbl
**[STD]**. SPM and stroke increase capacity monotonically; output never negative.
`vfd_percent` is recorded but **excluded from physics/scenario controls** because no
implemented function consumes it (SPM is the speed variable) — documented, not faked.

## 9. Production Coupling

```
production = min(reservoir_inflow, pump_actual_capacity)
limiting   = INFLOW_LIMITED if inflow ≤ pump else PUMP_LIMITED
```

The key twin relationship: the well produces what the reservoir delivers **and** what the
pump can lift, whichever binds. Verified live (e.g. BGW-DEMO: 142.683 bopd, PUMP_LIMITED).

## 10. Risk Indicators (deterministic prototype engineering indicators — NOT ML)

| Indicator | Proxy **[PROTO]** | Intuition |
|---|---|---|
| Rod floating | clamp(μ/2000, 0, 1) | thicker oil supports/floats the rod string |
| Impact loading | 0.6·clamp((Q_pump/max(q_in,ε)−1)/2,0,1) + 0.4·clamp(SPM/20,0,1) | oversized pump demand + aggressive speed |
| Pump unsetting | 0.7·\|Q_pump−q_in\|/(Q_pump+q_in) + 0.3·clamp(WHP/P_res,0,1) | inflow/pump mismatch + pressure transient |

Each returns `risk_level` (LOW <0.33 / MODERATE <0.66 / HIGH), `risk_score` 0–1
(**engineering indicator, never a probability**), and a `reason` embedding the actual
numbers. Fully reproducible; verified identical across repeated calls.

## 11. SOR and Energy (prototype conventions, honestly labeled)

```
SOR (prototype units: t/bbl) = steam_volume_t / (production_bopd × 30 days)
```

Zero production → `(None, "UNDEFINED_ZERO_OIL")`; never divides by zero. Steam is metered
in **tonnes** and oil in **barrels**, so this is a **prototype steam-to-oil mass/volume
ratio**, not a claim of field-standard SOR convention. Energy per 24 h operating day
**[PROTO coefficients]**:

```
steam_energy   = steam_volume_t × 750 kWh/t
pumping_energy = SPM × stroke_in × 0.5 kWh
energy_per_barrel = total / production   (None at zero production; all ≥ 0)
```

## 12. What-if Simulation

`POST /api/v1/wells/{well_id}/simulate` accepts optional overrides
(steam volume/pressure, soak, SPM, stroke, phase), builds a hypothetical state copy, and
returns current + scenario full snapshots with `scenario − current` deltas
(production, SOR, energy, status/limiting change). **Side-effect free — verified:**
well record, twin, audit log, and well count are byte-identical before/after.

## 13. Optimization (deterministic grid search, no scipy)

- **Default grid:** steam [600, 800, 1000] t × pressure [50, 65, 80] bar × soak
  [24, 48, 72] h × SPM [4, 6, 8] × stroke [72, 84, 96] in → **3⁵ = 243 scenarios**.
- **Objective (prototype demonstration weights — NOT Oil India provided):**
  `score = 0.40·norm(production) − 0.25·norm(SOR) − 0.15·norm(energy/bbl) − 0.20·mean_risk`,
  min-max normalized per run (undefined SOR/energy = worst penalty 1.0); deterministic
  tie-break by production → SOR → energy → grid order.
- **Constraints:** Block 1 safety ranges enforced by rejection (HTTP 422), never silent
  clamping; custom grids 1–5 values/dimension, max 2000 combinations.
- Returns recommended scenario (+score/inputs), current-vs-recommended delta, **top-5
  scenarios** (ranked, distinct, score-descending — verified), and `why_recommended[]`
  reasons generated from actual value comparisons (not generative AI).
- Live example (BGW-DEMO): recommended {600 t, 65 bar, 72 h, 8 SPM, 96 in} —
  142.7 → 228.3 bopd (**+85.6**), SOR 0.1986 → 0.0876 (**−0.111**), energy
  637740 → 450384 kWh (**−187356**), NOMINAL → NOMINAL.

## 14. Explainability

Every `why_recommended[]` item is emitted only when its numeric condition holds
(e.g. "reduced SOR" appears only if recommended SOR < current SOR — unit-tested), and
every twin `explanations{}` entry embeds the computed numbers. Called "Digital Twin
reasoning" in the UI; never "AI reasoning".

## 15. Dashboard (`project/index.html`)

Same stack as the original shell (Tailwind + Chart.js + Lucide, dark glass). Sections:
header (backend status, well selector from `GET /wells`, refresh, BGW-DEMO loader) →
6 KPI cards (BOPD / °C / cP / prototype SOR / kWh / risk) →
Reservoir→Wellbore→SRP→Surface flow → CSS phase + operating state →
what-if panel (current vs scenario + deltas) → optimization panel (recommended, deltas,
top-5, reasons) → 4 real-data bar charts → risk cards → backend explanations →
audit timeline → system status. Loading/error/empty states throughout; nulls render
"—". No `Math.random`, no mock engineering values, no fabricated history.

## 16. Architecture

```
Telemetry (validated ingest)
   ↓
FastAPI (app.py — routes, validation, stores)
   ↓
Well State (WELL_STORE dict + capped SHA-256 audit list; in-memory by design)
   ↓
Twin Physics (twin_physics.py — §5–§11)
   ↓
Risk Engine (deterministic indicators — §10)
   ↓
Simulation / Optimization (twin_optimize.py — §12–§14)
   ↓
Dashboard (index.html — fetch() only)
```

## 17. Security / Safety Boundary

Decision-support simulator only: simulate/optimize endpoints **do not issue field
commands** and are not connected to equipment. No secrets, API keys, credentials, auth,
or blockchain in the dashboard. CORS open for local demo; no PII handled.

## 18. Validation (this block — no field validation claimed)

- **56/56 pytest passing** (19 well/telemetry + 21 physics + 16 simulation/optimization).
- **38/38 live E2E checks**: full journey (all 9 routes incl. `/docs` 200), simulate +
  optimize side-effect freedom, double-run determinism, directional physics A–H,
  risk reproducibility, 243-grid/bounds/top-5/determinism, single-candidate,
  invalid/oversize-grid and unknown-well 404/422, boundary min/max acceptance,
  zero-production SOR safety.
- **9/9 dashboard contract checks**: every field the UI renders verified present.

## 19. Limitations

Uncalibrated prototype physics; fixed fillage/efficiency (0.85/0.75); prototype SOR
(t/bbl) convention; prototype energy coefficients; prototype objective weights;
in-memory state (restart wipes data); no historical time-series modeling; no trained ML;
no field-control integration; grid-bounded optimization; CDN-dependent dashboard.

## 20. Future Work (not implemented)

Field-data calibration; time-series storage; proper PVT/fluid models; trained production
forecasting; anomaly detection from historical failure data; advanced constrained
optimization; real-time telemetry; role-based operations; field validation; controlled
deployment.

## Appendix A — Parameter Provenance

| Parameter | Value | Source | Type |
|---|---|---|---|
| Reservoir reference temperature | 47 °C | Midpoint of PS 46–48 °C | PS-derived reference |
| API gravity reference | 18° API | Midpoint of PS 17–19° API | PS-derived reference |
| Thermal τ / ΔTmax | 72 h / 180 °C | Chosen for demo dynamics | Prototype assumption |
| Steam/pressure norm refs | 1000 t / 70 bar | Chosen grid-relevant scale | Prototype assumption |
| Reference viscosity 350 cP, B = 4500 K | — | Heavy-oil placeholder | Prototype assumption |
| API viscosity slope 0.01, factor [0.7, 1.3] | — | Placeholder sensitivity | Prototype assumption |
| Productivity index J = 0.8 bopd/bar; inflow cap 5000 | — | Placeholder | Prototype assumption |
| Pump bore 2.0 in; fillage 0.85; efficiency 0.75 | — | Placeholder | Prototype assumption |
| SOR window 30 days; 750 kWh/t steam; 0.5 kWh/(SPM·in·day) | — | Placeholder accounting | Prototype assumption |
| Objective weights 0.40/0.25/0.15/0.20 | — | Demo trade-off | Prototype assumption |
| Risk bands 0.33/0.66; float ref 2000 cP | — | Placeholder bands | Prototype assumption |
| in³/bbl 9702; min/day 1440 | — | Unit conversions | Standard |
| Grid 600/800/1000 t, 50/65/80 bar, 24/48/72 h, 4/6/8 SPM, 72/84/96 in | — | Demo search space | Prototype assumption |

## Appendix B — Recommended 3–5 Minute Demo Flow

- **0:00–0:30 — Problem:** Baghewala heavy oil (17–19° API, 46–48 °C): cold viscous crude
  needs steam heat *and* rod-pump lift, tuned separately today → mismatch, high SOR,
  rod/pump failures.
- **0:30–1:00 — Twin:** dashboard flow Reservoir → Wellbore → SRP → Surface; select
  BGW-DEMO (header loader ingests the baseline live if the store is empty).
- **1:00–1:45 — Current state:** KPIs (production BOPD, temperature °C, viscosity cP,
  prototype SOR, energy kWh, risk), CSS phase highlight, operating setpoints, risk cards.
- **1:45–2:30 — What-if:** raise steam to 1000 t / SPM to 6 → run; read scenario deltas;
  note "simulation only — does not change field operating state".
- **2:30–3:30 — Optimization:** run; 243 scenarios evaluated; recommended scenario card
  with production/SOR/energy deltas (live numbers, e.g. +85.6 BOPD, SOR halved).
- **3:30–4:00 — Why:** read 2–3 `why_recommended` reasons; each cites twin values.
- **4:00–4:30 — Risk + audit:** indicator levels/reasons; audit timeline hash entries.
- **4:30–5:00 — Honesty close:** prototype assumptions (this table), uncalibrated model,
  future field calibration. All numbers generated live, never hardcoded.
