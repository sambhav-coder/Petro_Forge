"""PetroForge ML Intelligence Engine (Priority 3).

Trustworthy ML layer that complements physics and engineering knowledge.
ML must NEVER fabricate field knowledge that available data cannot support.

Key principles:
- Explicit data provenance tracking
- Insufficient data returns explicit unavailable state
- No fabrication of Baghewala field knowledge
- Clear distinction between measured, derived, synthetic, and ML outputs
- Leakage prevention (temporal, target, entity)
- Physics-aware features where appropriate
- Model registry with quality gates
- Comprehensive testing

Version: 1.0
Priority: 3
"""

from .config import MLConfig, ModelTask
from .schemas import (
    MLEligibility,
    DatasetValidationReport,
    ModelMetadata,
    PredictionRequest,
    PredictionResponse,
    ForecastResult,
    AnomalyResult,
    HealthResult,
    FailureRiskResult,
)
from .datasets import DatasetInventory, DatasetEligibility
from .validation import DatasetValidator
from .preprocessing import DataPreprocessor
from .features import FeatureEngineer
from .splits import DataSplitter
from .metrics import ModelMetrics
from .registry import ModelRegistry, ModelStatus
from .inference import InferenceEngine
from .forecasting import ForecastingModel
from .anomaly import AnomalyDetector
from .srp_health import SRPHealthModel
from .failure import FailurePredictionModel
from .explainability import ExplainabilityEngine
from .provenance import (
    ProvenanceTracker,
    FeatureProvenance,
    ModelProvenance,
    PredictionProvenance,
    get_provenance_tracker,
)

__all__ = [
    # Configuration
    "MLConfig",
    "ModelTask",
    # Schemas
    "MLEligibility",
    "DatasetValidationReport",
    "ModelMetadata",
    "PredictionRequest",
    "PredictionResponse",
    "ForecastResult",
    "AnomalyResult",
    "HealthResult",
    "FailureRiskResult",
    # Core modules
    "DatasetInventory",
    "DatasetEligibility",
    "DatasetValidator",
    "DataPreprocessor",
    "FeatureEngineer",
    "DataSplitter",
    "ModelMetrics",
    "ModelRegistry",
    "ModelStatus",
    "InferenceEngine",
    # Task-specific models
    "ForecastingModel",
    "AnomalyDetector",
    "SRPHealthModel",
    "FailurePredictionModel",
    # Explainability
    "ExplainabilityEngine",
    # Provenance
    "ProvenanceTracker",
    "FeatureProvenance",
    "ModelProvenance",
    "PredictionProvenance",
    "get_provenance_tracker",
]

ML_VERSION = "1.0"
ML_SCHEMA_VERSION = "1.0"
