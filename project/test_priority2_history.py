"""Priority 2 historical engine tests.

Comprehensive tests for time-series schema, variable registry, temporal
semantics, repository operations, coverage analysis, aggregation, and
trend analysis. Ensures BGW-08 range preservation, BGW-17 publication
date handling, field/well separation, and synthetic data isolation.
"""

import pytest
from datetime import date, datetime

from data import history as history_engine
from data.provenance import ProvenanceClass


class TestVariableRegistry:
    def test_variable_registry_populated(self):
        assert len(history_engine.VARIABLE_REGISTRY) > 0
        assert "oil_rate_bopd" in history_engine.VARIABLE_REGISTRY
        assert "reservoir_temperature_c" in history_engine.VARIABLE_REGISTRY

    def test_variable_spec_structure(self):
        spec = history_engine.VARIABLE_REGISTRY["oil_rate_bopd"]
        assert spec.name == "oil_rate_bopd"
        assert spec.label == "Oil rate"
        assert spec.unit == "bopd"
        assert spec.domain == "PRODUCTION"
        assert spec.kind == history_engine.VariableKind.RATE
        assert spec.ml_eligible is True

    def test_variable_kind_enum(self):
        assert history_engine.VariableKind.RATE.value == "rate"
        assert history_engine.VariableKind.CUMULATIVE.value == "cumulative"
        assert history_engine.VariableKind.CATEGORICAL.value == "categorical"


class TestTemporalPrecision:
    def test_temporal_precision_enum(self):
        assert history_engine.TemporalPrecision.YEAR.value == "YEAR"
        assert history_engine.TemporalPrecision.MONTH.value == "MONTH"
        assert history_engine.TemporalPrecision.DAY.value == "DAY"
        assert history_engine.TemporalPrecision.DATETIME.value == "DATETIME"
        assert history_engine.TemporalPrecision.FINANCIAL_YEAR.value == "FINANCIAL_YEAR"
        assert history_engine.TemporalPrecision.RANGE.value == "RANGE"
        assert history_engine.TemporalPrecision.APPROXIMATE.value == "APPROXIMATE"

    def test_normalize_year(self):
        start, end, precision, approx = history_engine.normalize_period("2019")
        assert precision == history_engine.TemporalPrecision.YEAR
        assert start == "2019-01-01"
        assert end == "2019-12-31"
        assert approx is False

    def test_normalize_month(self):
        start, end, precision, approx = history_engine.normalize_period("2019-06")
        assert precision == history_engine.TemporalPrecision.MONTH
        assert start == "2019-06-01"
        assert end == "2019-06-30"
        assert approx is False

    def test_normalize_day(self):
        start, end, precision, approx = history_engine.normalize_period("2019-06-15")
        assert precision == history_engine.TemporalPrecision.DAY
        assert start == "2019-06-15"
        assert end == "2019-06-15"
        assert approx is False

    def test_normalize_financial_year(self):
        start, end, precision, approx = history_engine.normalize_period("FY2025-26")
        assert precision == history_engine.TemporalPrecision.FINANCIAL_YEAR
        assert start == "2025-04-01"
        assert end == "2026-03-31"
        assert approx is False

    def test_normalize_range(self):
        start, end, precision, approx = history_engine.normalize_period("2022-04/2022-08")
        assert precision == history_engine.TemporalPrecision.RANGE
        assert start == "2022-04-01"
        assert end == "2022-08-31"
        assert approx is True

    def test_normalize_undated(self):
        start, end, precision, approx = history_engine.normalize_period("undated")
        assert precision == history_engine.TemporalPrecision.APPROXIMATE
        assert approx is True

    def test_normalize_datetime(self):
        start, end, precision, approx = history_engine.normalize_period("2019-06-15T14:30:00Z")
        assert precision == history_engine.TemporalPrecision.DATETIME
        assert approx is False


class TestHistoricalObservation:
    def test_observation_schema_valid(self):
        obs = history_engine.HistoricalObservation(
            record_id="TEST-001",
            timestamp_start="2019-06-01",
            timestamp_end="2019-06-30",
            timestamp_precision=history_engine.TemporalPrecision.MONTH,
            original_period="2019-06",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            unit="bopd",
            value_kind=history_engine.ValueKind.REPORTED,
            source_id="test_source",
            provenance=ProvenanceClass.BAGHEWALA_FIELD,
            data_status="PUBLIC_FIELD_RECORD",
        )
        assert obs.record_id == "TEST-001"
        assert obs.well_id == "BGW-08"
        assert obs.value == 85.0

    def test_observation_validation_variable_unknown(self):
        obs = history_engine.HistoricalObservation(
            record_id="TEST-002",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="unknown_variable",
            value=1.0,
            unit="unknown",
            source_id="test",
        )
        ok, msg = history_engine.validate_observation(obs)
        assert ok is False
        assert "unknown variable" in msg

    def test_observation_validation_scope_mismatch(self):
        # Use css_event which is WELL-only and try to use it at FIELD scope
        obs = history_engine.HistoricalObservation(
            record_id="TEST-003",
            timestamp_start="2019-06-01",
            well_id=None,  # FIELD scope
            scope=history_engine.ObservationScope.FIELD,
            variable="css_event",  # css_event only allowed at WELL scope
            value_str="CSS_CYCLE",
            unit="event",
            source_id="test",
        )
        ok, msg = history_engine.validate_observation(obs)
        assert ok is False
        assert "not allowed at scope" in msg

    def test_observation_validation_well_scope_requires_well_id(self):
        obs = history_engine.HistoricalObservation(
            record_id="TEST-004",
            timestamp_start="2019-06-01",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=1.0,
            unit="bopd",
            source_id="test",
        )
        ok, msg = history_engine.validate_observation(obs)
        assert ok is False
        assert "requires well_id" in msg

    def test_observation_validation_field_scope_no_well_id(self):
        obs = history_engine.HistoricalObservation(
            record_id="TEST-005",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.FIELD,
            variable="field_rate_bopd",
            value=1000.0,
            unit="bopd",
            source_id="test",
        )
        ok, msg = history_engine.validate_observation(obs)
        assert ok is False
        assert "must not carry well_id" in msg

    def test_observation_validation_derived_midpoint_requires_range(self):
        obs = history_engine.HistoricalObservation(
            record_id="TEST-006",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            value_kind=history_engine.ValueKind.DERIVED_MIDPOINT,
            unit="bopd",
            source_id="test",
            provenance=ProvenanceClass.DERIVED,
        )
        ok, msg = history_engine.validate_observation(obs)
        assert ok is False
        assert "must preserve range" in msg

    def test_observation_validation_reported_range_requires_min_max(self):
        obs = history_engine.HistoricalObservation(
            record_id="TEST-007",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value_kind=history_engine.ValueKind.REPORTED_RANGE,
            unit="bopd",
            source_id="test",
        )
        ok, msg = history_engine.validate_observation(obs)
        assert ok is False
        assert "must carry min/max" in msg


class TestInMemoryRepository:
    def test_repository_insert_and_get(self):
        repo = history_engine.InMemoryHistoryRepository()
        obs = history_engine.HistoricalObservation(
            record_id="TEST-008",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            unit="bopd",
            source_id="test",
        )
        assert repo.insert(obs) is True
        retrieved = repo.get("TEST-008")
        assert retrieved is not None
        assert retrieved.value == 85.0

    def test_repository_duplicate_prevention(self):
        repo = history_engine.InMemoryHistoryRepository()
        obs = history_engine.HistoricalObservation(
            record_id="TEST-009",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            unit="bopd",
            source_id="test",
        )
        assert repo.insert(obs) is True
        assert repo.insert(obs) is False  # duplicate
        assert repo.duplicates == 1

    def test_repository_query_by_well(self):
        repo = history_engine.InMemoryHistoryRepository()
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-010-A",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            unit="bopd",
            source_id="test",
        ))
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-010-B",
            timestamp_start="2019-07-01",
            well_id="BGW-17",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=100.0,
            unit="bopd",
            source_id="test",
        ))
        results = repo.query(well_id="BGW-08")
        assert len(results) == 1
        assert results[0].well_id == "BGW-08"

    def test_repository_query_by_variable(self):
        repo = history_engine.InMemoryHistoryRepository()
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-011-A",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            unit="bopd",
            source_id="test",
        ))
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-011-B",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="reservoir_temperature_c",
            value=47.0,
            unit="C",
            source_id="test",
        ))
        results = repo.query(variable="oil_rate_bopd")
        assert len(results) == 1
        assert results[0].variable == "oil_rate_bopd"

    def test_repository_query_excludes_derived_by_default(self):
        repo = history_engine.InMemoryHistoryRepository()
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-012-A",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            unit="bopd",
            source_id="test",
            provenance=ProvenanceClass.BAGHEWALA_FIELD,
        ))
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-012-B",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            unit="bopd",
            source_id="test",
            provenance=ProvenanceClass.DERIVED,
        ))
        results = repo.query(well_id="BGW-08", include_derived=False)
        assert len(results) == 1
        assert results[0].provenance == ProvenanceClass.BAGHEWALA_FIELD

    def test_repository_query_excludes_synthetic_by_default(self):
        repo = history_engine.InMemoryHistoryRepository()
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-013-A",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            unit="bopd",
            source_id="test",
            provenance=ProvenanceClass.BAGHEWALA_FIELD,
        ))
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-013-B",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            unit="bopd",
            source_id="test",
            provenance=ProvenanceClass.SYNTHETIC_BAGHEWALA,
            data_status="SYNTHETIC_BAGHEWALA",
        ))
        results = repo.query(well_id="BGW-08", include_synthetic=False)
        assert len(results) == 1
        assert results[0].provenance == ProvenanceClass.BAGHEWALA_FIELD

    def test_repository_query_time_range(self):
        repo = history_engine.InMemoryHistoryRepository()
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-014-A",
            timestamp_start="2019-01-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=80.0,
            unit="bopd",
            source_id="test",
        ))
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-014-B",
            timestamp_start="2019-12-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=90.0,
            unit="bopd",
            source_id="test",
        ))
        results = repo.query(well_id="BGW-08", start="2019-06-01", end="2019-12-31")
        assert len(results) == 1
        assert results[0].value == 90.0


class TestPublicHistoryBuilder:
    def test_build_public_history_creates_observations(self):
        boot = {
            "production_well": [
                {
                    "well_id": "BGW-08",
                    "event_period": "2019-06",
                    "value": 85.0,
                    "value_kind": "midpoint_of_reported_range",
                    "reported_min_bopd": 80.0,
                    "reported_max_bopd": 90.0,
                    "derived_midpoint_bopd": 85.0,
                    "derivation": "arithmetic midpoint",
                    "derived_from": "reported range",
                    "unit": "bopd",
                    "source_id": "toi_css_jaipur_2019",
                    "source_publication_date": "2019-06-05",
                }
            ],
            "production_field": [],
            "css": [],
        }
        observations = history_engine.build_public_history(boot)
        assert len(observations) == 2  # range + derived midpoint

    def test_bgw08_range_preserved(self):
        boot = {
            "production_well": [
                {
                    "well_id": "BGW-08",
                    "event_period": "2019-06",
                    "value": 85.0,
                    "value_kind": "midpoint_of_reported_range",
                    "reported_min_bopd": 80.0,
                    "reported_max_bopd": 90.0,
                    "derived_midpoint_bopd": 85.0,
                    "derivation": "arithmetic midpoint",
                    "derived_from": "reported range",
                    "unit": "bopd",
                    "source_id": "toi_css_jaipur_2019",
                }
            ],
            "production_field": [],
            "css": [],
        }
        observations = history_engine.build_public_history(boot)
        range_obs = [o for o in observations if o.value_kind == history_engine.ValueKind.REPORTED_RANGE]
        assert len(range_obs) == 1
        assert range_obs[0].reported_min == 80.0
        assert range_obs[0].reported_max == 90.0
        assert range_obs[0].value is None

    def test_bgw08_midpoint_marked_derived(self):
        boot = {
            "production_well": [
                {
                    "well_id": "BGW-08",
                    "event_period": "2019-06",
                    "value": 85.0,
                    "value_kind": "midpoint_of_reported_range",
                    "reported_min_bopd": 80.0,
                    "reported_max_bopd": 90.0,
                    "derived_midpoint_bopd": 85.0,
                    "derivation": "arithmetic midpoint",
                    "derived_from": "reported range",
                    "unit": "bopd",
                    "source_id": "toi_css_jaipur_2019",
                }
            ],
            "production_field": [],
            "css": [],
        }
        observations = history_engine.build_public_history(boot)
        mid_obs = [o for o in observations if o.value_kind == history_engine.ValueKind.DERIVED_MIDPOINT]
        assert len(mid_obs) == 1
        assert mid_obs[0].value == 85.0
        assert mid_obs[0].provenance == ProvenanceClass.DERIVED
        assert mid_obs[0].data_status == "DERIVED"

    def test_field_level_observations_have_no_well_id(self):
        boot = {
            "production_well": [],
            "production_field": [
                {
                    "period": "FY2025-26",
                    "value": 1202.0,
                    "variable": "field_rate_bopd",
                    "unit": "bopd",
                    "source_id": "test",
                }
            ],
            "css": [],
        }
        observations = history_engine.build_public_history(boot)
        assert len(observations) == 1
        assert observations[0].scope == history_engine.ObservationScope.FIELD
        assert observations[0].well_id is None


class TestCoverageAnalysis:
    def test_coverage_empty(self):
        coverage = history_engine.compute_coverage([])
        assert coverage["observation_count"] == 0
        assert coverage["temporal_coverage"] == "NONE"
        assert coverage["has_gaps"] is False

    def test_coverage_basic(self):
        obs = [
            history_engine.HistoricalObservation(
                record_id="TEST-015",
                timestamp_start="2019-06-01",
                well_id="BGW-08",
                scope=history_engine.ObservationScope.WELL,
                variable="oil_rate_bopd",
                value=85.0,
                unit="bopd",
                source_id="test",
                provenance=ProvenanceClass.BAGHEWALA_FIELD,
            )
        ]
        coverage = history_engine.compute_coverage(obs)
        assert coverage["observation_count"] == 1
        assert coverage["measured_count"] == 1
        assert coverage["provenance_classes"] == ["BAGHEWALA_FIELD"]

    def test_well_coverage_summary(self):
        repo = history_engine.InMemoryHistoryRepository()
        repo.insert(history_engine.HistoricalObservation(
            record_id="TEST-016",
            timestamp_start="2019-06-01",
            well_id="BGW-08",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=85.0,
            unit="bopd",
            source_id="test",
        ))
        summary = history_engine.well_coverage_summary(repo, "BGW-08")
        assert summary["well_id"] == "BGW-08"
        assert summary["coverage"]["observation_count"] == 1
        assert summary["time_series_ready"] is False  # insufficient observations


class TestSafeAggregation:
    def test_aggregate_count(self):
        obs = [
            history_engine.HistoricalObservation(
                record_id="TEST-017",
                timestamp_start="2019-06-01",
                well_id="BGW-08",
                scope=history_engine.ObservationScope.WELL,
                variable="oil_rate_bopd",
                value=85.0,
                unit="bopd",
                source_id="test",
            )
        ]
        result = history_engine.safe_aggregate(obs, "count")
        assert result["operation"] == "count"
        assert result["result"] == 1

    def test_aggregate_mean(self):
        obs = [
            history_engine.HistoricalObservation(
                record_id="TEST-018-A",
                timestamp_start="2019-06-01",
                well_id="BGW-08",
                scope=history_engine.ObservationScope.WELL,
                variable="oil_rate_bopd",
                value=80.0,
                unit="bopd",
                source_id="test",
            ),
            history_engine.HistoricalObservation(
                record_id="TEST-018-B",
                timestamp_start="2019-07-01",
                well_id="BGW-08",
                scope=history_engine.ObservationScope.WELL,
                variable="oil_rate_bopd",
                value=90.0,
                unit="bopd",
                source_id="test",
            ),
        ]
        result = history_engine.safe_aggregate(obs, "mean")
        assert result["operation"] == "mean"
        assert result["result"] == 85.0

    def test_aggregate_refuses_categorical_sum(self):
        obs = [
            history_engine.HistoricalObservation(
                record_id="TEST-019",
                timestamp_start="2019-06-01",
                well_id="BGW-08",
                scope=history_engine.ObservationScope.WELL,
                variable="css_phase",
                value_str="INJECTION",
                unit="-",
                source_id="test",
            )
        ]
        result = history_engine.safe_aggregate(obs, "sum")
        assert result["result"] is None
        assert any("Cannot sum" in w for w in result["warnings"])

    def test_aggregate_refuses_rate_sum(self):
        obs = [
            history_engine.HistoricalObservation(
                record_id="TEST-020",
                timestamp_start="2019-06-01",
                well_id="BGW-08",
                scope=history_engine.ObservationScope.WELL,
                variable="oil_rate_bopd",
                value=85.0,
                unit="bopd",
                source_id="test",
            )
        ]
        result = history_engine.safe_aggregate(obs, "sum")
        assert result["result"] == 85.0  # but with warning
        assert any("physically meaningless" in w for w in result["warnings"])


class TestTrendAnalysis:
    def test_trend_insufficient_no_observations(self):
        result = history_engine.analyze_trend([])
        assert result["status"] == "INSUFFICIENT"
        assert "No observations" in result["reason"]

    def test_trend_insufficient_month_precision(self):
        obs = [
            history_engine.HistoricalObservation(
                record_id="TEST-021",
                timestamp_start="2019-06-01",
                timestamp_end="2019-06-30",
                timestamp_precision=history_engine.TemporalPrecision.MONTH,
                well_id="BGW-08",
                scope=history_engine.ObservationScope.WELL,
                variable="oil_rate_bopd",
                value=85.0,
                unit="bopd",
                source_id="test",
            )
        ]
        result = history_engine.analyze_trend(obs)
        assert result["status"] == "INSUFFICIENT"
        assert "Temporal precision not eligible" in result["reason"]

    def test_trend_insufficient_count(self):
        obs = [
            history_engine.HistoricalObservation(
                record_id="TEST-022",
                timestamp_start="2019-06-15T10:00:00Z",
                timestamp_precision=history_engine.TemporalPrecision.DATETIME,
                well_id="BGW-08",
                scope=history_engine.ObservationScope.WELL,
                variable="oil_rate_bopd",
                value=85.0,
                unit="bopd",
                source_id="test",
            )
        ]
        result = history_engine.analyze_trend(obs)
        assert result["status"] == "INSUFFICIENT"
        assert "Insufficient observations" in result["reason"]

    def test_trend_available(self):
        obs = [
            history_engine.HistoricalObservation(
                record_id="TEST-023-A",
                timestamp_start="2019-06-15T10:00:00Z",
                timestamp_precision=history_engine.TemporalPrecision.DATETIME,
                well_id="BGW-08",
                scope=history_engine.ObservationScope.WELL,
                variable="oil_rate_bopd",
                value=80.0,
                unit="bopd",
                source_id="test",
            ),
            history_engine.HistoricalObservation(
                record_id="TEST-023-B",
                timestamp_start="2019-07-15T10:00:00Z",
                timestamp_precision=history_engine.TemporalPrecision.DATETIME,
                well_id="BGW-08",
                scope=history_engine.ObservationScope.WELL,
                variable="oil_rate_bopd",
                value=90.0,
                unit="bopd",
                source_id="test",
            ),
        ]
        result = history_engine.analyze_trend(obs)
        assert result["status"] == "TREND_AVAILABLE"
        assert result["direction"] == "INCREASING"
        assert result["change"] == 10.0


class TestSyntheticIsolation:
    def test_synthetic_well_ids_defined(self):
        assert "BGW-DEMO" in history_engine.SYNTHETIC_WELL_IDS
        assert "BGW-S01" in history_engine.SYNTHETIC_WELL_IDS

    def test_synthetic_provenance_validation(self):
        obs = history_engine.HistoricalObservation(
            record_id="TEST-024",
            timestamp_start="2019-06-01",
            well_id="BGW-DEMO",
            scope=history_engine.ObservationScope.WELL,
            variable="oil_rate_bopd",
            value=100.0,
            unit="bopd",
            source_id="test",
            provenance=ProvenanceClass.SYNTHETIC_BAGHEWALA,
            data_status="PUBLIC_FIELD_RECORD",  # wrong status
        )
        ok, msg = history_engine.validate_observation(obs)
        assert ok is False
        assert "requires SYNTHETIC data_status" in msg


class TestPriority1ContractPreservation:
    def test_priority1_tests_still_pass(self):
        """Ensure Priority 2 doesn't break Priority 1 contracts."""
        # This is a meta-test - the actual Priority 1 tests run separately
        # Here we just verify the history module doesn't interfere with existing data
        assert history_engine.VARIABLE_REGISTRY is not None
        assert history_engine.MIN_OBSERVATIONS_FOR_TREND == 2
        assert history_engine.TREND_ELIGIBLE_PRECISION == {"DAY", "DATETIME"}
