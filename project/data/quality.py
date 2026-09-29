"""Data quality model (Priority 1, Part L).

Statuses: VALID | WARNING | INVALID | MISSING | DUPLICATE.
Questionable data is flagged with reasons — never silently deleted.
"""

from enum import Enum
from typing import List

from .schema import QualityRecord


class QualityStatus(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"
    MISSING = "MISSING"
    DUPLICATE = "DUPLICATE"


class QualityFlag(str, Enum):
    MISSING_VALUE = "missing_value"
    OUTLIER = "outlier"
    UNIT_CONVERSION = "unit_conversion"
    TIMESTAMP_PROBLEM = "timestamp_problem"
    IMPOSSIBLE_VALUE = "impossible_value"
    DUPLICATE_RECORD = "duplicate_record"
    SOURCE_CONFLICT = "source_conflict"
    SYNTHETIC = "synthetic"
    DERIVED = "derived"
    AMBIGUOUS_UNIT = "ambiguous_unit"


def new_quality(
    status: QualityStatus = QualityStatus.VALID,
    flags: List[str] | None = None,
    reasons: List[str] | None = None,
) -> QualityRecord:
    return QualityRecord(
        status=status.value,
        flags=list(flags or []),
        reasons=list(reasons or []),
    )


def merge_quality(records: List[QualityRecord]) -> QualityRecord:
    """Worst-status-wins merge: INVALID > DUPLICATE > MISSING > WARNING > VALID."""
    order = ["VALID", "WARNING", "MISSING", "DUPLICATE", "INVALID"]
    worst = "VALID"
    flags: List[str] = []
    reasons: List[str] = []
    for r in records:
        if order.index(r.status) > order.index(worst):
            worst = r.status
        for f in r.flags:
            if f not in flags:
                flags.append(f)
        reasons.extend(r.reasons)
    return QualityRecord(status=worst, flags=flags, reasons=reasons)
