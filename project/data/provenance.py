"""Provenance hierarchy (Priority 1, Part A).

Every value that matters must carry one of these classes. Categories are
NEVER silently upgraded: synthetic stays synthetic, reference stays reference.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class ProvenanceClass(str, Enum):
    BAGHEWALA_FIELD = "BAGHEWALA_FIELD"      # measured/reported specifically at Baghewala
    PUBLIC_REFERENCE = "PUBLIC_REFERENCE"    # legitimate public data, NOT Baghewala
    SYNTHETIC_BAGHEWALA = "SYNTHETIC_BAGHEWALA"  # generated under Baghewala constraints
    DERIVED = "DERIVED"                      # computed from another source dataset
    UNKNOWN = "UNKNOWN"                      # provenance cannot be established


@dataclass(frozen=True)
class Provenance:
    provenance_class: ProvenanceClass
    source_id: str = "unspecified"
    method: str = "unspecified"              # e.g. "twin_physics.viscosity_cp"
    assumptions: List[str] = field(default_factory=list)
    generator_version: Optional[str] = None  # required for SYNTHETIC_BAGHEWALA
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self):
        if (
            self.provenance_class == ProvenanceClass.SYNTHETIC_BAGHEWALA
            and not self.generator_version
        ):
            raise ValueError("synthetic records require a generator_version")


def synthetic_provenance(generator_version: str, constraints: str) -> Provenance:
    return Provenance(
        provenance_class=ProvenanceClass.SYNTHETIC_BAGHEWALA,
        source_id="synthetic_baghewala_generator",
        method=f"seeded generator {generator_version}",
        assumptions=[constraints],
        generator_version=generator_version,
    )
