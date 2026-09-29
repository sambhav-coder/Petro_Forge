# Priority 3: ML Intelligence Engine Documentation

## Overview

Priority 3 implements a trustworthy ML intelligence layer that complements physics and engineering knowledge in the PetroForge Digital Twin. The ML system explicitly distinguishes between real measured data, live telemetry, derived observations, synthetic data, and ML outputs.

**Key Principle:** ML must NEVER fabricate field knowledge that available data cannot support.

## Architecture

### Module Structure

```
project/ml/
├── __init__.py              # Main module exports
├── config.py                # ML configuration and constants
├── schemas.py               # Pydantic schemas for validation
├── datasets.py              # Dataset inventory and eligibility
├── validation.py            # Data validation framework
├── preprocessing.py         # Data cleaning and transformation
├── features.py              # Feature engineering pipeline
├── splits.py                # Data splitting with leakage prevention
├── metrics.py               # Model evaluation metrics
├── registry.py              # Model registry and lifecycle management
├── inference.py             # Unified inference engine
├── forecasting.py           # Production forecasting model
├── anomaly.py               # Anomaly detection model
├── srp_health.py            # SRP/pump health model
├── failure.py               # Failure prediction model
├── artifacts/               # Model artifacts storage
│   └── .gitkeep
└── tests/
    ├── __init__.py
    └── test_ml_intelligence.py
```

### Core Components

1. **Data Policy** (`ML_DATA_POLICY.md`)
   - Defines what data can/cannot be used for ML
   - Establishes ML_ELIGIBLE, ML_INELIGIBLE, SYNTHETIC, DERIVED, INSUFFICIENT_DATA classifications
   - Baghewala-specific policies

2. **Dataset Inventory** (`datasets.py`)
   - Discovers and evaluates datasets
   - Assesses ML eligibility for specific tasks
   - Maintains dataset metadata

3. **Data Validation** (`validation.py`)
   - Schema validation
   - Impossible value detection
   - Temporal ordering checks
   - Leakage risk assessment

4. **Feature Engineering** (`features.py`)
   - Lag features
   - Rolling window features
   - Delta features
   - Physics-aware features (using twin_physics)
   - Interaction features

5. **Data Splitting** (`splits.py`)
   - Chronological split (prevents temporal leakage)
   - Entity-aware split (prevents entity leakage)
   - Combined split
   - Leakage detection

6. **Model Registry** (`registry.py`)
   - Model lifecycle management
   - Quality gates for promotion
   - Artifact tracking
   - Metadata storage

7. **Inference Engine** (`inference.py`)
   - Unified prediction interface
   - Task routing
   - Insufficient-data handling

8. **Task-Specific Models**
   - `forecasting.py`: Production forecasting
   - `anomaly.py`: Anomaly detection
   - `srp_health.py`: SRP/pump health
   - `failure.py`: Failure prediction

## ML Data Policy

### ML_ELIGIBLE Data

- Sufficiently populated legitimate public datasets
- Properly timestamped historical telemetry
- Properly labeled failure/maintenance datasets
- Clearly isolated synthetic datasets
- Engineered features from eligible sources

### ML_INELIGIBLE Data

- Single sparse Baghewala observations
- Field-level values attached to individual wells
- Publication dates masquerading as measurements
- Derived midpoints treated as raw measurements
- Fabricated interpolation
- Synthetic data mixed with real data without labeling
- Test data leaked into training
- Future observations used to predict the past

### Baghewala-Specific Policies

**Production Forecasting: INSUFFICIENT TRAINING DATA**
- Public Baghewala dataset contains sparse observations
- No continuous time-series telemetry
- Field-level aggregates only
- Policy: Do NOT train forecasting on sparse Baghewala records

**SRP Health: INSUFFICIENT LABELED DATA**
- No continuous SRP operational telemetry
- No failure labels or maintenance records
- Policy: Do NOT train SRP health without labeled data

**Failure Prediction: INSUFFICIENT LABELED DATA**
- No explicit failure labels
- No maintenance work orders
- Policy: Do NOT train failure prediction without labels

## API Endpoints

### ML Status and Models

```
GET /api/v1/ml/status
```
Returns ML system status and available models.

```
GET /api/v1/ml/models?task=production_forecast&status=PRODUCTION
```
Lists registered ML models with optional filtering.

### Unified Prediction

```
POST /api/v1/ml/predict
```
Unified prediction endpoint that routes to task-specific models.

**Request:**
```json
{
  "task": "production_forecast",
  "well_id": "BGW-01",
  "features": {},
  "model_id": null,
  "model_version": null
}
```

**Response:**
```json
{
  "task": "production_forecast",
  "prediction": null,
  "confidence": null,
  "model_id": "unavailable",
  "model_version": "0.0",
  "timestamp": "2026-09-29T00:00:00Z",
  "feature_provenance": {},
  "data_quality": "INSUFFICIENT_DATA",
  "warnings": [],
  "limitations": [],
  "insufficient_data": true,
  "insufficient_reason": "MODEL_UNAVAILABLE_INSUFFICIENT_DATA"
}
```

### Task-Specific Endpoints

```
POST /api/v1/ml/forecast
```
Production forecasting endpoint.

```
POST /api/v1/ml/anomaly
```
Anomaly detection endpoint.

```
POST /api/v1/ml/srp-health
```
SRP/pump health assessment endpoint.

```
POST /api/v1/ml/failure-risk
```
Failure prediction endpoint.

### Dataset Management

```
GET /api/v1/ml/datasets
```
List ML datasets and their eligibility.

```
GET /api/v1/ml/datasets/{dataset_name}/eligibility?task=production_forecast
```
Get ML eligibility assessment for a dataset.

## Data Leakage Prevention

### Temporal Leakage Prevention

- **Chronological Split:** Ensures training data is strictly before validation/test data
- **No Future Information:** Features are computed only from past observations
- **Timestamp Validation:** Checks for temporal ordering violations

### Entity Leakage Prevention

- **Entity-Aware Split:** Ensures wells/entities do not appear in multiple splits
- **Entity Overlap Detection:** Identifies and prevents entity leakage
- **Combined Split:** Entity-aware + chronological for maximum safety

### Target Leakage Prevention

- **Label Leakage Detection:** Identifies features that may contain target information
- **Future Indicator Detection:** Flags features with future information
- **Failure Label Validation:** Ensures labels are not derived from features

## Model Quality Gates

A model cannot be promoted if:
- Insufficient data for training
- Severe class imbalance without handling
- Data leakage detected
- Baseline not established
- Test metrics unavailable
- Required metadata missing
- Reproducibility fails
- Feature schema mismatch
- Validation fails

## Insufficient Data Handling

When data is insufficient for a task:
- Return explicit `INSUFFICIENT_DATA` state
- Provide clear reason for insufficiency
- Never fabricate predictions
- Keep infrastructure in place for future data
- Document what data would be needed

**Example Response:**
```json
{
  "insufficient_data": true,
  "insufficient_reason": "MODEL_UNAVAILABLE_INSUFFICIENT_DATA",
  "limitations": [
    "Baghewala public data insufficient for continuous production forecasting",
    "Insufficient training data with continuous time-series"
  ]
}
```

## Physics-Aware Features

ML can consume physics-derived features from `twin_physics`:

- **Temperature-Viscosity:** `viscosity_cp()`
- **Mobility:** `mobility_factor()`
- **Heating Intensity:** `heating_intensity()`
- **Pump Capacity:** `theoretical_pump_capacity_bopd()`

**Important:** These are prototype relationships, not field-calibrated equations. ML uses them only when input data exists and units are valid.

## Model Training Pipeline

### Deterministic Training

Each training run records:
- Dataset identifier and version/hash
- Feature list and schema
- Target variable
- Split strategy (chronological/entity-aware)
- Random seed (fixed for reproducibility)
- Preprocessing parameters
- Model type and hyperparameters
- Training timestamp
- Metrics (train/validation/test)
- Provenance information
- Code/version identifier

### Baseline Comparison

Every model is compared against appropriate baselines:
- **Forecasting:** Naive last-value, moving average
- **Anomaly Detection:** Rolling z-score, IQR
- **Classification:** Majority class, random

A model is only promoted if it meaningfully improves over baseline.

## Testing

### Test Coverage

Priority 3 tests cover:
- Data validation (schema, impossible values, temporal ordering)
- Dataset eligibility (Baghewala forecasting ineligibility)
- Feature engineering (lag, rolling, physics features)
- Data leakage prevention (chronological, entity, temporal)
- Model metrics (regression, classification, baseline comparison)
- Model registry (registration, promotion, quality gates)
- Inference engine (insufficient data handling)
- Forecasting model (Baghewala ineligibility)
- Anomaly detection (statistical methods)
- SRP health (rule-based assessment)
- Failure prediction (label requirements)
- Integration with existing systems (Priority 1/2 contracts)

### Running Tests

```bash
cd project
python -m pytest ml/tests/test_ml_intelligence.py -v
```

## Security

### Security Measures

- No credentials in model artifacts
- Path traversal prevention in artifact loading
- Request size limits
- Validation of model IDs and versions
- No arbitrary pickle/joblib loading from user paths
- Explicit artifact path validation

### Artifact Safety

- Model artifacts stored in controlled directory
- Never load arbitrary user-provided files
- Validate model metadata before loading
- Document trust boundaries for joblib/pickle

## Performance

### Performance Considerations

- Local deterministic training (no distributed training)
- No GPU infrastructure required
- No cloud training platforms
- No Kubernetes or complex orchestration
- Millisecond-scale inference for individual predictions
- Batch processing for bulk operations

### Scalability

- In-memory processing for typical datasets
- JSONL file backing for persistence
- Migration path to PostgreSQL/TimescaleDB
- Async API endpoints for concurrent requests

## Limitations

### Current Limitations

1. **Baghewala Forecasting:** Public data insufficient for continuous forecasting
2. **SRP Health:** No labeled SRP health data available
3. **Failure Prediction:** No labeled failure data available
4. **Training Data:** Requires legitimate external datasets or live telemetry
5. **Deep Learning:** Not implemented (not needed for current data scale)

### Known Limitations

- Physics features are prototype relationships, not field-calibrated
- Rule-based health assessment until ML model trained
- Statistical anomaly detection until ML model trained
- No automatic model retraining (manual process)
- No distributed training (single-machine only)

## Integration with Existing Systems

### Priority 1 Contracts Preserved

- BGW-08 range preserved (not treated as single measurement)
- Publication dates not treated as event dates
- Field data not attached to wells
- Derived midpoints marked as DERIVED
- Provenance classes preserved

### Priority 2 Contracts Preserved

- Historical engine unchanged
- Temporal precision preserved
- Coverage analysis unchanged
- Trend analysis unchanged
- Aggregation rules unchanged

### Physics Module Integration

- ML can use physics-derived features
- Physics functions remain unchanged
- No modification to twin_physics
- No modification to twin_optimize

## Frontend Integration

### ML Intelligence Display

ML intelligence should be integrated into existing Twin/Inspector UI without redesign:

**Display Elements:**
- Production forecast (or "Insufficient training data")
- Anomaly status (NORMAL/WARNING/ANOMALY/INSUFFICIENT_CONTEXT)
- SRP/pump health (HEALTHY/DEGRADED/AT_RISK/INSUFFICIENT_DATA)
- Failure risk (probability or "Insufficient labeled data")

**Required Metadata:**
- Model ID and version
- Data source
- Confidence/score
- Data quality
- Limitations

**Prohibited Display:**
- Fake accuracy/confidence
- Fake failure probability
- Fake forecasts
- "0% risk" when model unavailable
- "Normal" when insufficient data

## Future Enhancements

### Potential Future Work (Priority 4+)

- Hybrid physics+ML Digital Twin
- Advanced SRP dissection UI
- Advanced CSS intelligence
- Advanced optimization
- Pareto optimization
- Full control room redesign
- Production deployment
- Automatic model retraining
- Distributed training
- GPU acceleration

### Data Requirements

To enable additional ML models:
- **Continuous time-series telemetry** for forecasting
- **Labeled failure/maintenance data** for failure prediction
- **SRP operational telemetry** for health models
- **Labeled CSS cycle data** for cycle optimization

## Troubleshooting

### Common Issues

**Model Returns INSUFFICIENT_DATA**
- Check if model is trained and promoted to PRODUCTION
- Verify dataset eligibility for the task
- Ensure required features are available

**Leakage Detection Fails**
- Verify chronological ordering of timestamps
- Check for entity overlap between splits
- Review feature engineering for future information

**Training Fails**
- Check dataset size meets minimum requirements
- Verify class balance for classification
- Ensure no impossible values in data
- Validate feature schema

### Debug Mode

Enable debug logging by setting environment variable:
```bash
export ML_DEBUG=true
```

## References

- ML Data Policy: `project/ml/ML_DATA_POLICY.md`
- Priority 1 Data Foundation: `project/data_catalog/README.md`
- Priority 2 Historical Engine: `project/PRIORITY2_HISTORICAL_ENGINE.md`
- Physics Module: `project/twin_physics.py`
- Optimization Module: `project/twin_optimize.py`

## Version History

- **1.0** (2026-09-29): Initial Priority 3 implementation
  - ML data policy
  - Dataset inventory and validation
  - Feature engineering pipeline
  - Data leakage prevention
  - Model registry and quality gates
  - Inference engine
  - Task-specific models (forecasting, anomaly, health, failure)
  - ML API endpoints
  - Comprehensive testing

## Support

For issues or questions:
1. Check this documentation
2. Review ML Data Policy
3. Run tests to verify installation
4. Check API responses for detailed error messages
5. Review model registry for model status

---

**Version:** 1.0  
**Priority:** 3 - ML Intelligence Engine  
**Status:** ACTIVE  
**Last Updated:** 2026-09-29
