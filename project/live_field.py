"""SIH26120 Digital Twin — live field simulator for real-time monitoring (Block 4).

=====================================================================
DOCUMENTATION
=====================================================================
No SCADA feed from Baghewala is available, so the real-time pipeline is
exercised by a SYNTHETIC FIELD that walks each demo well through
repeated CSS cycles (INJECTION -> SOAK -> PRODUCTION -> re-steam) and
emits telemetry readings that go through the SAME ingest path as real
data (validation, audit hash, twin, analytics, ML, alerts, stream).

- Each well has a hidden "true productivity" factor K_TRUE (the field
  produces K_TRUE x the uncalibrated twin). The analytics layer must
  DISCOVER it via auto-calibration — nothing is handed to the twin.
- Measurement noise is Gaussian; random FAULT EVENTS (pump wear,
  wellhead pressure surge) are injected so anomaly detection and
  alerting have something real to catch. Seeded -> reproducible.
- Well IDs use the SIM- prefix so synthetic wells can never be confused
  with real Baghewala well records (BGW-xx public data).
- Every reading is tagged provenance SYNTHETIC_BAGHEWALA in the event
  stream. Profiles are prototype assumptions inside the documented
  Baghewala bands (17-19 API, 46-48 C, 5-60 bopd per well).
=====================================================================
"""

import datetime
from typing import Dict, List, Optional

import numpy as np

import css_cycle
import twin_physics as tp

SEED = 26120
DEFAULT_HOURS_PER_TICK = 12.0
FAULT_PROBABILITY = 0.025
FAULT_TICKS = (2, 5)
START_TIME = datetime.datetime(2026, 7, 1, 6, 0, tzinfo=datetime.timezone.utc)

PROFILES: List[Dict] = [
    {"well_id": "SIM-01", "reservoir_pressure_bar": 30.0, "wellhead_pressure_bar": 10.0,
     "api_gravity": 18.2, "reservoir_temperature_c": 47.2, "steam_volume_t": 850.0,
     "steam_injection_pressure_bar": 65.0, "soak_time_h": 48.0, "spm": 5.0, "stroke_in": 96.0,
     "water_cut_percent": 35.0, "k_true": 0.28, "offset_days": 0.0},
    {"well_id": "SIM-02", "reservoir_pressure_bar": 24.0, "wellhead_pressure_bar": 11.0,
     "api_gravity": 17.4, "reservoir_temperature_c": 46.4, "steam_volume_t": 600.0,
     "steam_injection_pressure_bar": 55.0, "soak_time_h": 72.0, "spm": 7.5, "stroke_in": 100.0,
     "water_cut_percent": 45.0, "k_true": 0.22, "offset_days": 9.0},
    {"well_id": "SIM-03", "reservoir_pressure_bar": 38.0, "wellhead_pressure_bar": 9.0,
     "api_gravity": 18.8, "reservoir_temperature_c": 47.8, "steam_volume_t": 1000.0,
     "steam_injection_pressure_bar": 75.0, "soak_time_h": 36.0, "spm": 4.0, "stroke_in": 120.0,
     "water_cut_percent": 25.0, "k_true": 0.32, "offset_days": 17.0},
    {"well_id": "SIM-04", "reservoir_pressure_bar": 21.0, "wellhead_pressure_bar": 12.0,
     "api_gravity": 17.2, "reservoir_temperature_c": 46.1, "steam_volume_t": 450.0,
     "steam_injection_pressure_bar": 45.0, "soak_time_h": 24.0, "spm": 8.5, "stroke_in": 110.0,
     "water_cut_percent": 50.0, "k_true": 0.25, "offset_days": 4.0},
]

_STATIC_KEYS = ("reservoir_pressure_bar", "wellhead_pressure_bar", "api_gravity",
                "reservoir_temperature_c", "steam_volume_t", "steam_injection_pressure_bar",
                "soak_time_h", "spm", "stroke_in", "water_cut_percent")


class _Well:
    def __init__(self, profile: Dict):
        self.p = profile
        self.inj_days = profile["steam_volume_t"] / css_cycle.INJECTION_RATE_T_PER_DAY
        self.soak_days = profile["soak_time_h"] / 24.0
        plan = css_cycle.simulate_cycle(self._state("PRODUCTION", 0.0), include_series=False)
        # Operators cut off near the twin's optimum but not exactly (+/- a few days).
        self.prod_days = float(plan["optimal_cutoff_production_day"]) + 6.0
        self.cycle_days = self.inj_days + self.soak_days + self.prod_days
        self.t_cycle = profile["offset_days"] % self.cycle_days
        self.cycle_no = 1
        self.fault: Optional[Dict] = None

    def _state(self, phase: str, days: float):
        from types import SimpleNamespace
        return SimpleNamespace(well_id=self.p["well_id"], timestamp="", css_phase=phase,
                               days_in_phase=days, oil_rate_bopd=0.0,
                               vfd_percent=tp.vfd_for_spm(self.p["spm"]),
                               **{k: self.p[k] for k in _STATIC_KEYS})

    def phase(self):
        t = self.t_cycle
        if t < self.inj_days:
            return "INJECTION", t
        if t < self.inj_days + self.soak_days:
            return "SOAK", t - self.inj_days
        return "PRODUCTION", t - self.inj_days - self.soak_days


class FieldSimulator:
    """Deterministic multi-well CSS field. step() returns one reading per well."""

    def __init__(self, seed: int = SEED, hours_per_tick: float = DEFAULT_HOURS_PER_TICK):
        self.rng = np.random.RandomState(seed)
        self.hours_per_tick = hours_per_tick
        self.clock = START_TIME
        self.ticks = 0
        self.wells = [_Well(p) for p in PROFILES]

    def well_ids(self) -> List[str]:
        return [w.p["well_id"] for w in self.wells]

    def _reading(self, w: _Well) -> Dict:
        rng = self.rng
        phase, days = w.phase()
        spm = w.p["spm"]
        whp = w.p["wellhead_pressure_bar"]
        state = w._state(phase, days)
        oil = 0.0
        if phase == "PRODUCTION":
            snap = tp.twin_snapshot(state)
            oil = w.p["k_true"] * snap["estimated_oil_production_bopd"] * (1 + rng.normal(0, 0.05))
        event = None
        if w.fault is None and phase == "PRODUCTION" and rng.random_sample() < FAULT_PROBABILITY:
            kind = "PUMP_WEAR" if rng.random_sample() < 0.6 else "WELLHEAD_SURGE"
            w.fault = {"kind": kind, "left": int(rng.randint(*FAULT_TICKS))}
        if w.fault is not None:
            event = w.fault["kind"]
            if w.fault["kind"] == "PUMP_WEAR":
                oil *= 0.4
            else:
                whp *= 1.9
            w.fault["left"] -= 1
            if w.fault["left"] <= 0:
                w.fault = None
        reading = {
            "well_id": w.p["well_id"],
            "timestamp": self.clock.isoformat(),
            "reservoir_temperature_c": round(w.p["reservoir_temperature_c"] + rng.normal(0, 0.3), 2),
            "reservoir_pressure_bar": round(max(w.p["reservoir_pressure_bar"] + rng.normal(0, 0.4), 0.0), 2),
            "api_gravity": w.p["api_gravity"],
            "wellhead_pressure_bar": round(max(whp + rng.normal(0, 0.25), 0.0), 2),
            "oil_rate_bopd": round(min(max(oil, 0.0), 5000.0), 2),
            "steam_volume_t": w.p["steam_volume_t"],
            "steam_injection_pressure_bar": w.p["steam_injection_pressure_bar"],
            "soak_time_h": w.p["soak_time_h"],
            "css_phase": phase,
            "days_in_phase": round(days, 3),
            # SRP setpoints are reported in every phase (unit configured, stopped while shut in).
            "spm": round(max(spm + rng.normal(0, 0.08), 0.0), 2),
            "stroke_in": w.p["stroke_in"],
            "vfd_percent": tp.vfd_for_spm(spm),
            "water_cut_percent": round(min(max(w.p["water_cut_percent"] + rng.normal(0, 1.0), 0.0), 100.0), 2),
        }
        return {"reading": reading, "fault_event": event, "cycle_no": w.cycle_no}

    def step(self) -> List[Dict]:
        out = [self._reading(w) for w in self.wells]
        dt_days = self.hours_per_tick / 24.0
        for w in self.wells:
            w.t_cycle += dt_days
            if w.t_cycle >= w.cycle_days:
                w.t_cycle -= w.cycle_days
                w.cycle_no += 1
        self.clock += datetime.timedelta(hours=self.hours_per_tick)
        self.ticks += 1
        return out
