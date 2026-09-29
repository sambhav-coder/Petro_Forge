# PetroForge ML Data Policy (Priority 3)

## Purpose

This policy establishes clear rules for what data may and may not be used for machine learning training in the PetroForge system. The goal is to ensure ML models are trained only on data that genuinely supports the task, preventing fabrications and maintaining trustworthiness.

## Core Principle

**ML must NEVER fabricate field knowledge that the available data cannot support.**

Every model output must explicitly distinguish between:
1. Real measured/public historical data
2. Live telemetry
3. Derived observations
4. Synthetic/demo data
5. External legitimate public datasets
6. Training data
7. Validation/test data
8. Inference outputs

No model output may be presented as a measured Baghewala fact.

---

## WHAT CAN BE USED FOR ML

### ML_ELIGIBLE Data Sources

The following data sources are considered eligible for ML training when they meet the criteria below:

#### 1. Sufficiently Populated Legitimate Public Datasets
- **Requirements:**
  - Clear provenance documentation (source, license, collection method)
  - Sufficient sample size for the intended ML task
  - Well-documented variable definitions and units
  - Temporal information where applicable
  - Explicit licensing that permits ML use
- **Examples:**
  - Public datasets with documented licensing (e.g., Equinor Volve under Open Data Licence)
  - Academic datasets with clear terms of use
  - Industry benchmark datasets with proper attribution

#### 2. Properly Timestamped Historical Telemetry
- **Requirements:**
  - Continuous or sufficiently dense time-series data
  - Timestamp precision at least DAY-level (DATETIME preferred)
  - Consistent sampling intervals
  - No temporal gaps that would invalidate the ML task
  - Clear provenance (measured vs reported vs derived)
- **Examples:**
  - Live SCADA telemetry with proper timestamps
  - Historical time-series with adequate frequency
  - Monitoring data with temporal integrity

#### 3. Properly Labeled Failure/Maintenance Datasets
- **Requirements:**
  - Explicit failure labels (not inferred from anomalies)
  - Clear failure definition and classification
  - Sufficient positive examples (failure cases)
  - Sufficient negative examples (normal operation)
  - Temporal separation between training and test periods
  - No label leakage from future information
- **Examples:**
  - Equipment failure logs with confirmed root cause
  - Maintenance records with clear work order outcomes
  - Public failure datasets with documented labeling methodology

#### 4. Clearly Isolated Synthetic Datasets
- **Requirements:**
  - Explicitly labeled as SYNTHETIC_BAGHEWALA
  - Generator version and seed documented
  - Constraints and assumptions documented
  - Never mixed with real data without labeling
  - Used only for demonstration/testing, not as Baghewala facts
- **Examples:**
  - Synthetic telemetry generated under Baghewala constraints
  - Demo datasets for testing ML pipelines
  - Stress test data for validation

#### 5. Engineered Features Derived from Eligible Source Observations
- **Requirements:**
  - Source observations must be ML-eligible
  - Feature derivation logic documented
  - No future-value leakage in feature computation
  - Provenance traced to source observations
  - Mathematical/physical basis explained
- **Examples:**
  - Rolling statistics from eligible time-series
  - Physics-derived features from twin_physics (with prototype disclaimer)
  - Rate-of-change features from continuous measurements
  - Lag features from historical data

---

## WHAT MUST NOT BE USED AS ORDINARY TRAINING DATA

### ML_INELIGIBLE Data Sources

The following data sources are explicitly ineligible for ML training as ordinary training data:

#### 1. Single Sparse Baghewala Observations
- **Reason:** Single point observations cannot establish patterns or trends
- **Examples:**
  - Individual well production rates from public reports
  - Single CSS cycle records
  - One-time measurement snapshots
- **Allowed Use:** Feature context, engineering constraints, metadata only

#### 2. Field-Level Values Attached to Individual Wells
- **Reason:** Field aggregates do not represent well-specific behavior
- **Examples:**
  - Field-wide production rates assigned to specific wells
  - Average field temperature applied to individual wells
  - Aggregate CSS parameters per well
- **Allowed Use:** Field-level context only, never as well training data

#### 3. Publication Dates Masquerading as Measurements
- **Reason:** Publication dates are when data was reported, not when measurements occurred
- **Examples:**
  - Report publication dates used as production timestamps
  - Fiscal year bounds treated as actual measurement periods
  - Document release dates as event timestamps
- **Allowed Use:** Provenance tracking only, never as measurement time

#### 4. Derived Midpoint Values Treated as Raw Measurements
- **Reason:** Midpoints are computed from ranges, not actual measurements
- **Examples:**
  - BGW-08 derived midpoint 85 BOPD from 80-90 range treated as measured
  - Average of reported min/max treated as actual reading
  - Interpolated values between sparse points
- **Allowed Use:** Only with explicit DERIVED provenance, never as raw measurement

#### 5. Fabricated Interpolation
- **Reason:** Interpolation between sparse points invents data that does not exist
- **Examples:**
  - Daily values interpolated from monthly reports
  - Continuous telemetry fabricated from sparse points
  - Gap filling without measurement basis
- **Allowed Use:** Never - gaps must remain as gaps

#### 6. Fabricated Baghewala Telemetry
- **Reason:** Synthetic data cannot become field data through relabeling
- **Examples:**
  - Synthetic telemetry with provenance changed to BAGHEWALA_FIELD
  - Demo data presented as real measurements
  - Generated values treated as actual field readings
- **Allowed Use:** Only with explicit SYNTHETIC_BAGHEWALA provenance

#### 7. Synthetic Data Mixed with Real Data Without Labeling
- **Reason:** Mixing synthetic and real without labeling destroys provenance
- **Examples:**
  - Synthetic records added to training data without provenance flags
  - Demo and real data in same dataset without separation
  - Generated and measured values merged without distinction
- **Allowed Use:** Only with explicit provenance tracking for each record

#### 8. Test Data Leaked into Training
- **Reason:** Testing on training data invalidates model evaluation
- **Examples:**
  - Same observations in both train and test splits
  - Future observations used to predict the past
  - Random splits for temporal data (violates causality)
- **Allowed Use:** Never - strict train/validation/test separation required

#### 9. Future Observations Used to Predict the Past
- **Reason:** Temporal leakage violates causality
- **Examples:**
  - Using future production to predict past SPM
  - Test data from later periods in training
  - Information from future timesteps in features
- **Allowed Use:** Never - chronological ordering must be preserved

---

## DATA ELIGIBILITY CLASSIFICATIONS

### ML_ELIGIBLE
Data that meets all criteria for ML training:
- Sufficient sample size
- Proper labeling (if supervised)
- Temporal integrity (if time-series)
- Clear provenance
- Documented licensing
- No leakage risks

### ML_INELIGIBLE
Data that cannot be used for ML training:
- Sparse single observations
- Field aggregates at well level
- Publication dates as measurements
- Derived midpoints as raw data
- Fabricated interpolation
- Unlabeled synthetic mixes
- Leaked test data
- Future information in past

### SYNTHETIC
Generated data for demonstration/testing:
- Explicitly labeled SYNTHETIC_BAGHEWALA
- Generator version and seed documented
- Constraints documented
- Never presented as field data
- Used only for testing/validation

### DERIVED
Computed features from eligible sources:
- Source observations documented
- Derivation logic explained
- Provenance traced to source
- Mathematical/physical basis
- No future-value leakage

### INSUFFICIENT_DATA
Data that does not meet minimum requirements:
- Too few observations for task
- Inadequate temporal coverage
- Missing required labels
- Incomplete variable set
- Insufficient diversity

---

## BAGHEWALA-SPECIFIC POLICIES

### Baghewala Production Forecasting
**Status: INSUFFICIENT TRAINING DATA**

The public Baghewala dataset contains:
- 5 verified well records with sparse historical data
- No continuous time-series telemetry
- Field-level aggregates only
- Single-point production observations
- No daily/monthly continuous production history

**Policy:** Do NOT train a production forecasting model on sparse public Baghewala well records.

**Allowed Uses:**
- Feature context (well metadata, reservoir properties)
- Engineering constraints (pressure, temperature ranges)
- Physics-informed features (using twin_physics relationships)
- Inference context when live telemetry exists
- Dashboard context (historical records as reference)

**Prohibited Uses:**
- Creating artificial daily/monthly Baghewala production history
- Training forecasting models on sparse points
- Presenting model outputs as Baghewala measurements
- Interpolating between sparse public records

### Baghewala SRP Health
**Status: INSUFFICIENT LABELED DATA**

The public Baghewala dataset contains:
- SRP equipment information (lift method, pump type)
- No continuous SRP operational telemetry
- No failure labels or maintenance records
- No dynamometer card data
- No rod load or pump fillage measurements

**Policy:** Do NOT train an SRP health model without labeled failure data.

**Allowed Uses:**
- Equipment metadata (pump type, stroke range)
- Physics-based indicators (from twin_physics)
- Anomaly detection on live telemetry (if available)
- Engineering constraints (SPM ranges, stroke limits)

**Prohibited Uses:**
- Training failure prediction without labels
- Inferring mechanical failure from sparse records
- Presenting anomaly scores as failure probabilities

### Baghewala Failure Prediction
**Status: INSUFFICIENT LABELED DATA**

The public Baghewala dataset contains:
- No explicit failure labels
- No maintenance work orders
- No equipment failure records
- No downtime classifications
- No root cause documentation

**Policy:** Do NOT train a failure prediction model without labeled failure data.

**Allowed Uses:**
- Reference datasets for methodology design (e.g., Mendeley SRP failure data)
- Feature engineering patterns from public sources
- Anomaly detection framework design
- Risk indicator development (engineering-based, not ML)

**Prohibited Uses:**
- Training failure models on unlabeled Baghewala data
- Inferring failure from sparse observations
- Presenting risk indicators as failure probabilities

---

## DATA PROVENANCE REQUIREMENTS

Every ML model must document:
1. **Input Dataset:** Name, version, source, license
2. **Observation IDs:** Where feasible, trace predictions to source observations
3. **Feature Generation:** Which features, from which source variables, using which methods
4. **Model Version:** Identifier, training timestamp, code version
5. **Training Dataset Version:** Hash or version of training data
6. **Provenance Class:** BAGHEWALA_FIELD, PUBLIC_REFERENCE, SYNTHETIC_BAGHEWALA, DERIVED, UNKNOWN

---

## VALIDATION REQUIREMENTS

Before any ML training:
1. **Schema Validation:** Required columns present, correct types
2. **Missing Value Analysis:** Document missingness patterns
3. **Duplicate Detection:** Identify and handle duplicates
4. **Impossible Value Check:** Physical plausibility (negative pressure, etc.)
5. **Label Validity:** Labels exist, are correct, not leaked
6. **Temporal Ordering:** Chronological sequence preserved
7. **Entity Identifiers:** Well/entity IDs consistent
8. **Provenance Verification:** Provenance classes correct
9. **Leakage Risk Assessment:** No future information, no target leakage
10. **ML Eligibility:** Dataset meets minimum requirements

If any validation fails, training must refuse to proceed.

---

## MODEL OUTPUT REQUIREMENTS

Every ML prediction must include:
1. **Task:** What the model predicts (forecast, anomaly, health, failure)
2. **Prediction:** The model output value or class
3. **Confidence/Score:** Model confidence where applicable
4. **Model ID:** Which model produced the prediction
5. **Model Version:** Version identifier
6. **Timestamp:** When the prediction was made
7. **Feature Provenance:** Which features were used, from which sources
8. **Data Quality:** Assessment of input data quality
9. **Warnings:** Any data quality or model limitation warnings
10. **Limitations:** Known model limitations and assumptions
11. **Insufficient Data State:** Explicit "INSUFFICIENT_DATA" when applicable

Never return a prediction without knowing which model produced it and what data it was trained on.

---

## POLICY ENFORCEMENT

### Quality Gates
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

### Model Registry
Every model must be registered with:
- Model ID
- Task type
- Version
- Status (CANDIDATE, VALIDATED, PRODUCTION, RETIRED, UNAVAILABLE)
- Dataset used
- Feature schema
- Metrics
- Artifact path
- Training timestamp
- Eligibility determination
- Limitations documentation

### Unavailable Models
If data does not support a model:
- Return "MODEL_UNAVAILABLE_INSUFFICIENT_DATA"
- Document why data is insufficient
- Keep infrastructure in place for future data
- Do not fabricate performance metrics

---

## REVIEW AND UPDATES

This policy must be reviewed:
- When new data sources are added
- When ML tasks are expanded
- When data quality issues are discovered
- When model performance issues arise
- At least annually for currency

Policy changes require:
- Documentation of rationale
- Impact assessment on existing models
- Retraining requirements evaluation
- Stakeholder approval

---

## REFERENCES

- Priority 1: Data Foundation and Provenance
- Priority 2: Historical Time-Series Engine
- PetroForge Data Catalog (project/data_catalog/)
- Baghewala Well Coverage (project/data/public/baghewala_well_coverage.json)
- twin_physics.py (prototype engineering relationships)
- twin_optimize.py (deterministic optimization)

---

**Policy Version:** 1.0  
**Effective Date:** 2026-09-29  
**Priority:** 3 - ML Intelligence Engine  
**Status:** ACTIVE
