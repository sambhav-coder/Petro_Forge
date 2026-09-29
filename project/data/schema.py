"""Canonical Pydantic schemas (Priority 1, Parts H-K).

All measurement fields are nullable: partial datasets are first-class.
Unknown values stay null — never filled with fake numbers.
Schema version: DATA_SCHEMA_VERSION in package __init__.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from .provenance import ProvenanceClass


class DataSourceRecord(BaseModel):
    source_id: str = Field(..., min_length=1)
    source_name: str = Field(..., min_length=1)
    publisher: str = "unspecified"
    url: str = ""
    source_type: str = "other"  # official_report|tender|paper|dataset|other
    provenance_class: ProvenanceClass = ProvenanceClass.UNKNOWN
    time_period: str = "unspecified"
    geography: str = "unspecified"
    variables: List[str] = Field(default_factory=list)
    license: str = "unspecified"
    redistribution_allowed: bool = False
    confidence: str = "low"  # low|medium|high
    notes: str = ""


class WellRecord(BaseModel):
    well_id: str = Field(..., min_length=1)
    well_name: Optional[str] = None
    field: str = "Baghewala"
    reservoir: Optional[str] = None
    formation: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    surface_elevation_m: Optional[float] = None
    total_depth_m: Optional[float] = None
    completion_interval: Optional[str] = None
    reservoir_temperature_c: Optional[float] = None
    reservoir_pressure_bar: Optional[float] = None
    api_gravity: Optional[float] = None
    oil_viscosity_cp: Optional[float] = None
    lift_method: Optional[str] = None
    pump_type: Optional[str] = None
    status: Optional[str] = None
    source_id: str = "unspecified"
    provenance: ProvenanceClass = ProvenanceClass.UNKNOWN


class TelemetryRecord(BaseModel):
    timestamp: Optional[str] = None
    well_id: str = Field(..., min_length=1)
    reservoir_temperature_c: Optional[float] = None
    reservoir_pressure_bar: Optional[float] = None
    wellhead_pressure_bar: Optional[float] = None
    wellhead_temperature_c: Optional[float] = None
    oil_rate_bopd: Optional[float] = None
    water_cut_fraction: Optional[float] = None
    steam_volume_t: Optional[float] = None
    steam_injection_pressure_bar: Optional[float] = None
    steam_injection_temperature_c: Optional[float] = None
    soak_time_h: Optional[float] = None
    css_phase: Optional[str] = None
    spm: Optional[float] = None
    stroke_in: Optional[float] = None
    vfd: Optional[float] = None
    pump_fillage: Optional[float] = None
    pump_efficiency: Optional[float] = None
    rod_load: Optional[float] = None
    rod_position: Optional[float] = None
    pump_intake_pressure_bar: Optional[float] = None
    energy_kwh: Optional[float] = None
    data_quality: Optional[str] = None
    source_id: str = "unspecified"
    provenance: ProvenanceClass = ProvenanceClass.UNKNOWN


class CSSCycleRecord(BaseModel):
    cycle_id: str = Field(..., min_length=1)
    well_id: str = Field(..., min_length=1)
    injection_start: Optional[str] = None
    injection_end: Optional[str] = None
    soak_start: Optional[str] = None
    soak_end: Optional[str] = None
    production_start: Optional[str] = None
    production_end: Optional[str] = None
    steam_volume_t: Optional[float] = None
    injection_pressure_bar: Optional[float] = None
    injection_temperature_c: Optional[float] = None
    soak_time_h: Optional[float] = None
    production_cutoff: Optional[str] = None
    oil_production_bbl: Optional[float] = None
    water_production_bbl: Optional[float] = None
    sor: Optional[float] = None
    energy_kwh: Optional[float] = None
    source_id: str = "unspecified"
    provenance: ProvenanceClass = ProvenanceClass.UNKNOWN


class QualityRecord(BaseModel):
    status: str = "MISSING"  # VALID|WARNING|INVALID|MISSING|DUPLICATE
    flags: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


class FeatureRecord(BaseModel):
    name: str
    value: Optional[float] = None
    origin: str = "unspecified"       # source fields, e.g. "reservoir_temperature_c"
    method: str = "unspecified"       # e.g. "twin_physics.viscosity_cp"
    status: str = "DERIVED_PROTOTYPE"
    provenance: ProvenanceClass = ProvenanceClass.DERIVED
