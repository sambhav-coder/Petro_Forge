"""Deterministic ingestion pipeline (Priority 1, Part M).

RAW -> PARSE -> SCHEMA -> UNITS -> QUALITY -> CLEAN -> (FEATURES) -> STORE.
Same input -> same report. Traceability preserved throughout.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .cleaning import clean_telemetry, dedupe
from .features import engineer_pairwise, engineer_record
from .provenance import ProvenanceClass
from .quality import QualityStatus
from .repository import DataRepository
from .schema import FeatureRecord, QualityRecord, TelemetryRecord


@dataclass
class IngestReport:
    accepted: int = 0
    rejected: int = 0
    duplicates: int = 0
    warnings: int = 0
    quality_by_status: Dict[str, int] = field(default_factory=dict)
    provenance: str = ProvenanceClass.UNKNOWN.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "duplicates": self.duplicates,
            "warnings": self.warnings,
            "quality_by_status": self.quality_by_status,
            "provenance": self.provenance,
        }


def ingest_telemetry_batch(
    raw_records: List[Dict[str, Any]],
    repo: DataRepository,
    source_id: str = "unspecified",
    provenance: str = ProvenanceClass.UNKNOWN.value,
    units: Optional[Dict[str, str]] = None,
    with_features: bool = True,
) -> tuple[IngestReport, List[FeatureRecord]]:
    """Run the full pipeline and store accepted records. Deterministic."""
    report = IngestReport(provenance=provenance)
    cleaned: List[tuple[TelemetryRecord, QualityRecord]] = []
    for raw in raw_records:
        item = dict(raw)
        item.setdefault("source_id", source_id)
        item.setdefault("provenance", provenance)
        record, quality = clean_telemetry(item, units)
        report.quality_by_status[quality.status] = (
            report.quality_by_status.get(quality.status, 0) + 1
        )
        if record is None:
            report.rejected += 1
            continue
        if quality.status == QualityStatus.WARNING.value:
            report.warnings += 1
        cleaned.append((record, quality))

    kept, dupes = dedupe(cleaned)
    report.duplicates = dupes
    accepted_records = [r for r, _ in kept]
    repo.save_telemetry(accepted_records)
    report.accepted = len(accepted_records)

    features: List[FeatureRecord] = []
    if with_features:
        for record, _ in kept:
            features.extend(engineer_record(record))
        by_well: Dict[str, List[TelemetryRecord]] = {}
        for record, _ in kept:
            by_well.setdefault(record.well_id, []).append(record)
        for records in by_well.values():
            ordered = sorted(records, key=lambda r: r.timestamp or "")
            for prev, curr in zip(ordered, ordered[1:]):
                features.extend(engineer_pairwise(prev, curr))
    return report, features
