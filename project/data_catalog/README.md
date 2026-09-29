# PetroForge Data Foundation

> Honest summary: **Public Baghewala data includes field-level information and
> a subset of well-specific historical/status/CSS/production records
> (5 verified wells). Complete continuous well-by-well SCADA telemetry was not
> found publicly. Granular operational telemetry that is not publicly available
> is represented only through explicitly labeled synthetic data.**

## 1. What data is available

- **Baghewala aggregates** (rates, well counts, geology, equipment) from OIL,
  press reports of officials, government records, peer-reviewed geology papers.
- **5 publicly verified well records**: BGW-01 (discovery, 1991-94
  tests), BGW-04 (1991-94 tests), BGW-08 (first CSS Dec 2018, reported
  80–90 bopd post-pilot with derived midpoint 85 BOPD), BGW-17 (2022
  injection completion, ~17 days reported, exact dates not established),
  BGW-40 (fishbones) — Baghewala field contains additional wells; only
  wells with sufficient publicly verifiable well-specific evidence are
  represented in this public registry — see
  `../data/public/baghewala_well_coverage.json` (mirrored here as
  `baghewala_well_coverage.json`). 5 verified well records with
  historical/status evidence; **no continuous telemetry** (all
  `telemetry_data: false`, all `time_series_safe: false`).
- **Public reference datasets/papers** (Mendeley SRP failure data, Volve open
  field data, dynamometer-card literature) for *methods*, never for Baghewala facts.
- **Synthetic Baghewala-constrained telemetry** generated on demand
  (`project.data.synthetic`, seed 42) — every record labeled `SYNTHETIC_BAGHEWALA`.
- **Derived features** computed by reusing `twin_physics` (labeled `DERIVED_PROTOTYPE`).
- **Bootstrap**: `project/data/public/*.json` load at startup into the
  well list, so the twin never opens empty. Telemetry ingests supersede
  (never overwrite) public records.

## 2. Baghewala-specific public data found

See `data_sources.json` + `provenance.json`: 17–19° API, 46–48 °C baseline,
Jodhpur Sandstone ~1150 m, SRP + thermal wellhead + VIT completions, CSS since
2018 pilot, 19 CSS wells (FY25-26), field rates 600 → 705 → 1202 bopd over
reporting years, 25 MT in-place / 53 MT bitumen (historical). Conflicts
(area 200 vs 200.26 vs 210; wells 35/23 vs 52/33) are **retained with reasons**
(different years/scopes), never silently resolved.

## 3. What was NOT found

**Complete continuous well-by-well SCADA telemetry was not found publicly.**
No public source provides timestamped pressure/temperature/steam/SPM/stroke/VFD
streams. Per-well coverage (`baghewala_well_coverage.json`) is explicit:
2 CSS records, 1 well-specific production record, 0 telemetry streams.
This is documented as fact, not failure.

## 4. Public reference datasets

Mendeley SRP failure data (DOI 10.17632/42jnkpp5tv.1) for failure-method design;
Equinor Volve (Open Data Licence) for production time-series pipeline patterns;
dynamometer literature (Mossoro/Brazil, China, methods repo) for Phase-3 design.
Raw third-party files are **never committed** — metadata only.

## 5. Synthetic data strategy

Seeded generator (`synthetic_baghewala/1.0`, seed 42): 3 wells × 3 CSS cycles ×
3 phases + deliberately broken records. Source-constrained bands (API context,
thermal baseline, CSS structure, SRP bands) vs documented engineering assumptions
(noise, failure rates). Regenerate any time: `project.data.synthetic.generate()`.

## 6. Provenance architecture

Five classes: `BAGHEWALA_FIELD`, `PUBLIC_REFERENCE`, `SYNTHETIC_BAGHEWALA`,
`DERIVED`, `UNKNOWN`. Every synthetic record carries generator version + seed +
constraints note; every feature carries origin + method + `DERIVED_PROTOTYPE`.

## 7. Data schema

`project/data/schema.py` (v1.0): `WellRecord`, `TelemetryRecord` (all measurements
nullable), `CSSCycleRecord`, `QualityRecord`, `FeatureRecord`, `DataSourceRecord`.
Unknown stays null — never faked.

## 8. Unit conventions

Canonical: °C, bar, BOPD, tonnes, hours, inches, SPM, VFD %, kWh, cP, water-cut
fraction. Conversions explicit; ambiguous units pass through **unchanged with a
warning flag** (`units.py`).

## 9. Data quality rules

Statuses VALID/WARNING/INVALID/MISSING/DUPLICATE; flags incl. missing_value,
outlier, ambiguous_unit, timestamp_problem, impossible_value, duplicate_record,
synthetic, derived. Hard physics (non-negativity, finiteness) rejects; soft
Baghewala-plausible windows warn. Worst-status-wins merge; raw never mutated.

## 10. Feature engineering

`project/data/features.py` reuses `twin_physics` (heating intensity, viscosity,
mobility, SOR, pump capacity) plus guarded divisions and pairwise deltas
(temperature/pressure/production/SPM/stroke/VFD). Each feature records origin,
method, status.

## 11. Storage architecture

`DataRepository` interface → `InMemoryRepository` (API runtime) and
`JsonlFileRepository` (JSONL per entity, traversal-safe paths). PostgreSQL/
TimescaleDB later = new implementation of the same interface. CSV ingest via
pandas parsing only; validation downstream.

## 12. Ingestion workflow

`pipeline.ingest_telemetry_batch`: RAW → parse → schema → units → quality →
clean → dedupe → features → store, returning a deterministic `IngestReport`
(accepted/rejected/duplicates/warnings/quality mix/provenance).

## 13. Future database migration

Implement `DataRepository` against PostgreSQL/TimescaleDB; JSONL files already
use one-record-per-line canonical JSON, importable as-is. No API change needed.

## 14. Limitations

Aggregates only for Baghewala; synthetic ≠ field; reference ≠ Baghewala; no
historical time series; soft windows are judgement, not calibration.

## 15. Licensing/data rights

Only metadata/citations stored for third-party sources. Mendeley/Volve/raw
papers: download separately under their terms; place licensed raw files under
`project/data/raw/` (git-ignored except `.gitkeep`). Nothing redistributed
without rights.

## 16. Reproducibility

Python per `requirements.txt`; `DATA_SCHEMA_VERSION=1.0`;
`SYNTHETIC_GENERATOR_VERSION=synthetic_baghewala/1.0`; default seed 42;
catalog files versioned (`"version": "1.0"`). Offline test suite (no internet).
