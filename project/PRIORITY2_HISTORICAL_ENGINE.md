# Priority 2: Historical / Time-Series Engine

## Overview

Priority 2 implements a trustworthy historical/time-series foundation for PetroForge, enabling future forecasting, anomaly detection, failure prediction, hybrid physics+ML intelligence, and advanced optimization.

## Key Features

### 1. Data Distinction

The system distinguishes between:
- **Actual public historical observations** - Verified Baghewala field records
- **Field-level aggregate observations** - Field-wide production metrics
- **Well-level historical observations** - Well-specific historical data
- **Live telemetry** - Real-time sensor data with historical snapshots
- **Derived values** - Calculated values (e.g., midpoints of reported ranges)
- **Synthetic/demo telemetry** - Demo data for system testing
- **Records insufficient for time-series analysis** - Sparse or low-precision data

### 2. Time Precision Preservation

The system preserves temporal precision without fabrication:
- **YEAR** - Annual observations (e.g., "2019")
- **FINANCIAL_YEAR** - Indian fiscal years (e.g., "FY2025-26")
- **MONTH** - Monthly observations (e.g., "2019-06")
- **DAY** - Daily observations (e.g., "2019-06-15")
- **DATETIME** - Exact timestamps (e.g., "2019-06-15T14:30:00Z")
- **RANGE** - Date ranges (e.g., "2022-04/2022-08")
- **APPROXIMATE** - Undated or approximate periods

**Example:** A value reported for June 2019 remains as MONTH precision, not converted to a fake daily measurement (2019-06-01 00:00:00).

### 3. Variable Registry

Controlled variable registry with metadata:
- **RESERVOIR**: reservoir_temperature_c, reservoir_pressure_bar, viscosity_cp, api_gravity
- **PRODUCTION**: oil_rate_bopd, water_cut_percent, production_volume_bbl, field_rate_bopd, annual_production_mt
- **STEAM_CSS**: steam_volume_t, steam_injection_pressure_bar, soak_time_h, css_phase, css_event, production_cutoff
- **SRP**: spm, stroke_in, vfd_percent, pump_efficiency_percent, pump_fillage_percent, rod_load, pump_intake_pressure_bar
- **SURFACE**: wellhead_pressure_bar, wellhead_temperature_c
- **ENERGY**: energy_kwh, steam_energy, pumping_energy
- **PERFORMANCE**: sor, uptime_percent, well_status

Each variable specifies:
- Canonical name and human-readable label
- Unit and physical domain
- Allowed scopes (FIELD/WELL)
- Variable kind (RATE/INSTANTANEOUS/CUMULATIVE/EVENT/CATEGORICAL)
- Chartability and ML eligibility

### 4. Historical Storage Engine

**Architecture:**
```
HistoricalObservation
    ↓
HistoricalRepository (interface)
    ↓
InMemoryHistoryRepository / JsonlHistoryRepository
    ↓
query/filter/aggregate/coverage
    ↓
API endpoints
    ↓
Frontend charts
```

**Repository Features:**
- Deterministic duplicate prevention (record_id uniqueness)
- Query by well, field, variable, time range, provenance, precision
- Safe defaults (excludes derived/synthetic by default)
- Limit protection (max 1000 records per query)
- JSONL file backing for persistence (JsonlHistoryRepository)

### 5. Public Baghewala Data Ingestion

**BGW-08 Range Preservation:**
- Reported production: 80–90 BOPD during June 2019
- System creates TWO observations:
  1. REPORTED_RANGE: 80–90 BOPD (no single value)
  2. DERIVED_MIDPOINT: 85 BOPD (explicitly marked DERIVED)
- The 85 BOPD value never appears as a raw measurement

**BGW-17 Publication Date:**
- 2022-08-02 is preserved as source_publication_date
- NOT used as an operational event date
- injection_end remains null (exact end not established)

**Field vs Well Separation:**
- Field-level production (FY2025-26, FY2024-25) stays FIELD scope
- Never attached to individual wells (BGW-01, BGW-04, BGW-08, BGW-17, BGW-40)
- Well-level observations require well_id and WELL scope

### 6. Coverage and Quality Analysis

Every query exposes quality metadata:
- observation_count
- temporal_coverage (start to end)
- timestamp_precision breakdown
- gaps_detected (90+ day gaps)
- duplicate_count
- provenance_classes (BAGHEWALA_FIELD, DERIVED, SYNTHETIC_BAGHEWALA, LIVE_TELEMETRY)
- measured_count, derived_count, synthetic_count
- time_series_safe_count, ml_safe_count

**Example Coverage Summary for BGW-08:**
```
Historical records: 1
Production observations: 1 (80-90 BOPD range + 85 BOPD derived)
CSS events: 1
Continuous telemetry: unavailable
Temporal precision: MONTH
Measured/public: 1
Derived: 1
Synthetic: 0
ML-safe observations: 0
Time-series ready: false (insufficient observations)
```

### 7. API Endpoints

**Versioned API endpoints:**
- `GET /api/v1/history` - General historical query
- `GET /api/v1/history/wells/{well_id}` - Well-specific history
- `GET /api/v1/history/field` - Field-level history
- `GET /api/v1/history/coverage/{well_id}` - Coverage summary
- `GET /api/v1/history/trend/{well_id}` - Trend analysis
- `GET /api/v1/history/aggregate` - Safe aggregation
- `GET /api/v1/history/stats` - Repository statistics

**Query Parameters:**
- `variable` - Filter by variable name
- `start`, `end` - Time range filter
- `provenance` - Filter by provenance class
- `precision` - Filter by temporal precision
- `include_derived` - Include derived observations (default: false)
- `include_synthetic` - Include synthetic observations (default: false)
- `include_live` - Include live telemetry (default: true)
- `limit` - Max records (default: 100, max: 1000)

**Safety:**
- Defaults exclude derived and synthetic data
- Queries never accidentally mix provenance classes
- Response metadata explains what was included

### 8. Live Telemetry History

Live telemetry ingestion now creates historical snapshots:
- Each telemetry ingest creates a HistoricalObservation
- Marked with data_status "LIVE_TELEMETRY"
- Preserves exact timestamp
- Separate from public historical records
- Duplicate handling: deterministic (same well_id + timestamp = duplicate)

### 9. Synthetic Data Isolation

Synthetic data is explicitly isolated:
- Reserved well IDs: BGW-DEMO, BGW-S01, BGW-S02, BGW-S03
- SYNTHETIC_BAGHEWALA provenance
- SYNTHETIC_BAGHEWALA data_status
- Excluded by default from historical queries
- Cannot silently enter public historical queries
- Explicit synthetic/demo filter available

### 10. Safe Aggregation

Supported operations with safety checks:
- `count` - Always safe
- `min`, `max` - For numeric values
- `mean`, `median` - For numeric values (refuses categorical)
- `sum` - For cumulative variables only (warns on rates)
- `latest`, `earliest` - By timestamp

**Safety Rules:**
- Refuses to aggregate categorical/event variables numerically
- Warns when summing rate variables (physically meaningless)
- Preserves source observation count
- Returns warnings for inappropriate operations

### 11. Trend and Gap Analysis

Trend analysis with strict requirements:
- Minimum 2 observations required
- Only DAY or DATETIME precision eligible
- Returns INSUFFICIENT for sparse series
- Never fabricates trends from single points
- Provides: direction, change, change_percent, min/max/mean

**Example Responses:**
- INSUFFICIENT: "No observations"
- INSUFFICIENT: "Temporal precision not eligible (MONTH, YEAR)"
- INSUFFICIENT: "Insufficient observations (need 2, have 1)"
- TREND_AVAILABLE: direction, statistics, metadata

### 12. Frontend Historical View

Added HISTORY tab to the existing Twin Inspector:
- Coverage summary with status indicators
- Provenance breakdown with color coding
- Variable distribution
- Recent observations with metadata
- Temporal precision display
- Data quality warnings
- Insufficient coverage alerts

**Coverage-First UX:**
- Clear status: TIME-SERIES READY vs INSUFFICIENT COVERAGE
- Provenance badges: BAGHEWALA_FIELD (green), DERIVED (amber), SYNTHETIC (red), LIVE_TELEMETRY (emerald)
- Temporal precision displayed for each observation
- Warnings for derived/synthetic/insufficient data
- No fabricated continuous lines for sparse data

### 13. Testing

**43 Priority 2 tests covering:**
- Variable registry structure
- Temporal precision normalization (year, month, day, FY, range, datetime)
- HistoricalObservation schema validation
- Repository operations (insert, duplicate prevention, query)
- BGW-08 range preservation
- BGW-08 midpoint marked DERIVED
- Field-level observations have no well_id
- Coverage analysis
- Safe aggregation (count, mean, categorical refusal)
- Trend analysis (insufficient cases, available case)
- Synthetic isolation
- Priority 1 contract preservation

**Total Test Suite:**
- Baseline: 128 tests (Priority 1)
- Priority 2: 43 tests
- Total: 171 tests (all passing)

### 14. Performance and Architecture

**Lightweight Implementation:**
- No Kafka, Redis, TimescaleDB, Kubernetes added
- File-backed JSONL implementation (append-safe)
- In-memory repository for performance
- Clean abstraction for future database migration
- No unnecessary dependencies

**Migration Path:**
- HistoricalRepository interface can be implemented with TimescaleDB/PostgreSQL
- JSONL backing can be replaced without API changes
- Query semantics preserved across implementations

### 15. Security

**Security Validations:**
- No secrets, API keys, or credentials in code
- No .env file exposure
- No unsafe file paths (path traversal protected)
- No arbitrary file reads through history endpoints
- Query limits (max 1000 records per request)
- Provenance isolation prevents data leakage
- Synthetic data cannot contaminate public records

## Limitations

**What Priority 2 Does NOT Provide:**
- Production forecasting ML models
- Anomaly detection ML models
- SRP failure prediction
- Pump failure prediction
- Advanced optimization beyond existing Block 3
- Pareto optimization
- New AI models
- Reservoir simulation
- Advanced CSS optimization
- Final landing-page redesign
- Production deployment

**Data Limitations:**
- Baghewala public data cannot provide continuous SCADA history
- Sparse historical points remain sparse
- Single-point series report INSUFFICIENT coverage
- No fabricated interpolation or continuous lines

## Future Migration to Time-Series Database

The clean abstraction enables future migration:
1. Implement HistoricalRepository with TimescaleDB/PostgreSQL
2. Replace JsonlHistoryRepository with database-backed version
3. No API changes required
4. Query semantics preserved
5. Historical observations stored efficiently

## Priority 3 Scope

Priority 3 will build on this foundation:
- ML models consuming only ML-safe observations
- Anomaly detection on time-series data
- Failure prediction using historical patterns
- Advanced forecasting
- Enhanced optimization with historical context

---

**Priority 2 provides the historical/time-series infrastructure. It does not create missing field telemetry.**
