"""Cleaning utilities (Priority 1, Part O).

Handles missing/duplicate/invalid records and produces, for every fix:
cleaned value + quality flag + reason. Raw input is never mutated.
"""

import copy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import physical
from .quality import QualityFlag, QualityStatus, merge_quality, new_quality
from .schema import QualityRecord, TelemetryRecord
from .units import FIELD_FAMILY, normalize_value, normalize_vfd, normalize_water_cut

NUMERIC_FIELDS = list(physical.HARD_BOUNDS.keys())
VALID_PHASES = {"INJECTION", "SOAK", "PRODUCTION", "IDLE"}


def parse_timestamp(raw: Any) -> Tuple[Optional[str], Optional[QualityRecord]]:
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None, new_quality(
            QualityStatus.MISSING,
            [QualityFlag.MISSING_VALUE.value],
            ["timestamp missing"],
        )
    text = str(raw).strip()
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return text, None
    except ValueError:
        return None, new_quality(
            QualityStatus.INVALID,
            [QualityFlag.TIMESTAMP_PROBLEM.value],
            [f"timestamp unparsable: {text}"],
        )


def coerce_number(raw: Any) -> Tuple[Optional[float], bool]:
    """Return (value_or_None, was_invalid). Non-numeric strings are invalid."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None, False
    if isinstance(raw, bool):
        return None, True
    try:
        return float(raw), False
    except (TypeError, ValueError):
        return None, True


def clean_telemetry(
    raw: Dict[str, Any],
    units: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[TelemetryRecord], QualityRecord]:
    """Clean one raw telemetry dict.

    Returns (record_or_None, quality). record is None only for INVALID
    records (bad timestamp, bad well_id, hard-physics violation).
    `units` maps field -> source unit for normalization; ambiguous units
    are flagged, never silently converted.
    """
    raw = copy.deepcopy(raw)
    units = units or {}
    qualities: List[QualityRecord] = []

    ts, ts_q = parse_timestamp(raw.get("timestamp"))
    if ts_q is not None:
        qualities.append(ts_q)
        if ts_q.status == QualityStatus.INVALID.value:
            return None, merge_quality(qualities)

    well_id = raw.get("well_id")
    if not isinstance(well_id, str) or not well_id.strip():
        qualities.append(
            new_quality(
                QualityStatus.INVALID,
                [QualityFlag.IMPOSSIBLE_VALUE.value],
                ["malformed well_id"],
            )
        )
        return None, merge_quality(qualities)

    values: Dict[str, Any] = {"timestamp": ts, "well_id": well_id.strip()}
    for field in NUMERIC_FIELDS:
        if field not in raw:
            continue
        value, was_invalid = coerce_number(raw[field])
        if was_invalid:
            qualities.append(
                new_quality(
                    QualityStatus.INVALID,
                    [QualityFlag.IMPOSSIBLE_VALUE.value],
                    [f"{field} non-numeric: {raw[field]}"],
                )
            )
            return None, merge_quality(qualities)
        if value is None:
            qualities.append(
                new_quality(
                    QualityStatus.MISSING,
                    [QualityFlag.MISSING_VALUE.value],
                    [f"{field} missing"],
                )
            )
            continue
        family = FIELD_FAMILY.get(field)
        if field == "water_cut_fraction":
            value, warn = normalize_water_cut(value, units.get(field))
        elif field == "vfd":
            value, warn = normalize_vfd(value, units.get(field))
        elif family is not None:
            value, warn = normalize_value(family, value, units.get(field))
        else:
            warn = None
        if warn:
            qualities.append(
                new_quality(
                    QualityStatus.WARNING,
                    [QualityFlag.AMBIGUOUS_UNIT.value, QualityFlag.UNIT_CONVERSION.value],
                    [f"{field}: {warn}"],
                )
            )
        values[field] = value

    phase = raw.get("css_phase")
    if phase is not None:
        label = str(phase).strip().upper()
        if label in VALID_PHASES:
            values["css_phase"] = label
        else:
            qualities.append(
                new_quality(
                    QualityStatus.WARNING,
                    [QualityFlag.IMPOSSIBLE_VALUE.value],
                    [f"inconsistent phase label: {phase}"],
                )
            )

    for passthrough in ("source_id", "provenance", "data_quality"):
        if passthrough in raw:
            values[passthrough] = raw[passthrough]

    invalid, warnings, _ = physical.validate_record(values)
    if invalid:
        qualities.append(
            new_quality(
                QualityStatus.INVALID,
                [QualityFlag.IMPOSSIBLE_VALUE.value],
                invalid,
            )
        )
        return None, merge_quality(qualities)
    for w in warnings:
        qualities.append(
            new_quality(QualityStatus.WARNING, [QualityFlag.OUTLIER.value], [w])
        )

    record = TelemetryRecord(**{k: v for k, v in values.items() if k in TelemetryRecord.model_fields})
    final_q = merge_quality(qualities) if qualities else new_quality()
    return record, final_q


def dedupe(
    items: List[Tuple[TelemetryRecord, QualityRecord]],
) -> Tuple[List[Tuple[TelemetryRecord, QualityRecord]], int]:
    """Deduplicate on (well_id, timestamp). Keeps first, flags the rest
    DUPLICATE. O(n) via a seen-set — no O(n^2) scans."""
    seen = set()
    kept: List[Tuple[TelemetryRecord, QualityRecord]] = []
    dupes = 0
    for record, quality in items:
        key = (record.well_id, record.timestamp)
        if key in seen:
            dupes += 1
            kept.append(
                (
                    record,
                    merge_quality(
                        [
                            quality,
                            new_quality(
                                QualityStatus.DUPLICATE,
                                [QualityFlag.DUPLICATE_RECORD.value],
                                [f"duplicate of {(record.well_id, record.timestamp)}"],
                            ),
                        ]
                    ),
                )
            )
            continue
        seen.add(key)
        kept.append((record, quality))
    return kept, dupes
