"""Reproducible synthetic Baghewala-constrained generator (Priority 1, Parts S-T).

PROVENANCE IS ALWAYS SYNTHETIC_BAGHEWALA. This module never claims to be
field data. Deterministic via fixed seed (numpy RandomState).
Includes deliberately injected bad records so the cleaning pipeline
can prove it catches them.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import numpy as np

from . import DEFAULT_SYNTHETIC_SEED, SYNTHETIC_GENERATOR_VERSION
from .baghewala_constraints import ENGINEERING_ASSUMPTIONS as EA
from .provenance import ProvenanceClass

PHASES = ["INJECTION", "SOAK", "PRODUCTION"]
WELL_IDS = ["BGW-S01", "BGW-S02", "BGW-S03"]

CONSTRAINT_NOTE = (
    "SOURCE-CONSTRAINED: 17-19 API context, 46-48 C baseline, 3-phase CSS, "
    "SRP lift, thermal response. ENGINEERING ASSUMPTIONS: operating bands, "
    "noise scales, failure rates (see baghewala_constraints.py)."
)


def _band(rng: np.random.RandomState, band: List[float], n: int) -> np.ndarray:
    lo, hi = band
    return rng.uniform(lo, hi, size=n)


def generate(
    wells: List[str] | None = None,
    cycles_per_well: int = 3,
    seed: int = DEFAULT_SYNTHETIC_SEED,
    include_bad: bool = True,
) -> List[Dict[str, Any]]:
    """Generate synthetic telemetry dicts. Same seed -> identical output."""
    wells = wells or list(WELL_IDS)
    rng = np.random.RandomState(seed)
    base_time = datetime(2025, 1, 6, 6, 0, 0, tzinfo=timezone.utc)
    records: List[Dict[str, Any]] = []
    step = 0
    for well_id in wells:
        for cycle in range(cycles_per_well):
            steam = float(_band(rng, EA["steam_volume_band_t"]["value"], 1)[0])
            soak = float(_band(rng, EA["soak_band_h"]["value"], 1)[0])
            spm = float(_band(rng, EA["spm_operating_band"]["value"], 1)[0])
            stroke = float(_band(rng, EA["stroke_band_in"]["value"], 1)[0])
            oil = float(_band(rng, EA["oil_rate_band_bopd"]["value"], 1)[0])
            water = float(_band(rng, EA["water_cut_band"]["value"], 1)[0])
            temp = float(rng.uniform(46.0, 48.0) + rng.uniform(0.0, 90.0) * (steam / 1200.0))
            res_p = float(rng.uniform(15.0, 45.0))
            for phase in PHASES:
                ts = base_time + timedelta(hours=step * 36)
                step += 1
                records.append({
                    "timestamp": ts.isoformat(),
                    "well_id": well_id,
                    "cycle_id": f"{well_id}-C{cycle + 1:02d}",
                    "reservoir_temperature_c": round(temp + float(rng.normal(0, 1.5)), 2),
                    "reservoir_pressure_bar": round(res_p + float(rng.normal(0, 1.0)), 2),
                    "wellhead_pressure_bar": round(max(0.0, res_p - rng.uniform(5.0, 18.0)), 2),
                    "oil_rate_bopd": round(max(0.0, oil + float(rng.normal(0, 2.0))), 2),
                    "water_cut_fraction": round(min(1.0, max(0.0, water)), 3),
                    "steam_volume_t": round(steam, 1),
                    "steam_injection_pressure_bar": round(float(rng.uniform(40.0, 80.0)), 1),
                    "soak_time_h": round(soak, 1),
                    "css_phase": phase,
                    "spm": round(spm + float(rng.normal(0, 0.2)), 2),
                    "stroke_in": round(stroke, 1),
                    "vfd": round(float(rng.uniform(40.0, 70.0)), 1),
                    "rod_failure": bool(rng.random() < EA["rod_failure_rate"]["value"]),
                    "pump_unsetting": bool(rng.random() < EA["pump_unsetting_rate"]["value"]),
                    "source_id": "synthetic_baghewala_generator",
                    "provenance": ProvenanceClass.SYNTHETIC_BAGHEWALA.value,
                    "generator_version": SYNTHETIC_GENERATOR_VERSION,
                    "generation_seed": seed,
                    "constraints_note": CONSTRAINT_NOTE,
                })
    if include_bad:
        records.extend(_bad_records(base_time, seed))
    return records


def _bad_records(base_time: datetime, seed: int) -> List[Dict[str, Any]]:
    """Deliberately broken records the pipeline must catch. Deterministic."""
    good_ts = (base_time).isoformat()

    def base(**over):
        rec = {
            "timestamp": good_ts, "well_id": "BGW-S01",
            "reservoir_temperature_c": 47.0, "reservoir_pressure_bar": 28.0,
            "oil_rate_bopd": 20.0, "spm": 5.0, "stroke_in": 96.0,
            "css_phase": "PRODUCTION",
            "source_id": "synthetic_baghewala_generator",
            "provenance": ProvenanceClass.SYNTHETIC_BAGHEWALA.value,
            "generator_version": SYNTHETIC_GENERATOR_VERSION,
            "generation_seed": seed,
        }
        rec.update(over)
        return rec

    return [
        base(timestamp=None),                                            # missing timestamp
        base(timestamp=good_ts),                                         # duplicate
        base(timestamp="not-a-time"),                                    # bad timestamp
        base(reservoir_pressure_bar=-5.0, timestamp=(base_time + timedelta(hours=1)).isoformat()),
        base(reservoir_temperature_c=5000.0, timestamp=(base_time + timedelta(hours=2)).isoformat()),
        base(well_id="   ", timestamp=(base_time + timedelta(hours=3)).isoformat()),
        base(css_phase="BOILING", timestamp=(base_time + timedelta(hours=4)).isoformat()),
        base(oil_rate_bopd="lots", timestamp=(base_time + timedelta(hours=5)).isoformat()),
    ]
