"""PetroForge data foundation (Priority 1).

Provenance-first pipeline: RAW -> PARSE -> SCHEMA -> UNITS -> QUALITY
-> CLEAN -> FEATURES -> CANONICAL RECORD -> REPOSITORY.

Reproducibility anchors:
- DATA_SCHEMA_VERSION: canonical schema version
- SYNTHETIC_GENERATOR_VERSION: synthetic generator version
- All physics-derived features reuse twin_physics (never duplicated).
"""

DATA_SCHEMA_VERSION = "1.0"
SYNTHETIC_GENERATOR_VERSION = "synthetic_baghewala/1.0"
DEFAULT_SYNTHETIC_SEED = 42

from .provenance import Provenance, ProvenanceClass
from .schema import (
    CSSCycleRecord,
    DataSourceRecord,
    FeatureRecord,
    QualityRecord,
    TelemetryRecord,
    WellRecord,
)

__all__ = [
    "DATA_SCHEMA_VERSION",
    "SYNTHETIC_GENERATOR_VERSION",
    "DEFAULT_SYNTHETIC_SEED",
    "Provenance",
    "ProvenanceClass",
    "CSSCycleRecord",
    "DataSourceRecord",
    "FeatureRecord",
    "QualityRecord",
    "TelemetryRecord",
    "WellRecord",
]
