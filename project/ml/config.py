"""ML configuration and constants.

Deterministic configuration for reproducible ML operations.
No randomness without explicit seeds.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ModelTask(str, Enum):
    """ML task types."""
    PRODUCTION_FORECAST = "production_forecast"
    ANOMALY_DETECTION = "anomaly_detection"
    SRP_HEALTH = "srp_health"
    FAILURE_RISK = "failure_risk"


class MLEligibility(str, Enum):
    """ML eligibility classification."""
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    SYNTHETIC = "SYNTHETIC"
    DERIVED = "DERIVED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ModelStatus(str, Enum):
    """Model lifecycle status."""
    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    PRODUCTION = "PRODUCTION"
    RETIRED = "RETIRED"
    UNAVAILABLE = "UNAVAILABLE"


class AnomalyStatus(str, Enum):
    """Anomaly detection results."""
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    ANOMALY = "ANOMALY"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class HealthStatus(str, Enum):
    """SRP/pump health status."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    AT_RISK = "AT_RISK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class MLConfig:
    """ML configuration with deterministic defaults."""
    
    # Random seeds for reproducibility
    random_seed: int = 42
    numpy_seed: int = 42
    python_seed: int = 42
    
    # Data requirements
    min_observations_for_training: int = 100
    min_observations_for_trend: int = 2
    min_positive_failure_samples: int = 20
    min_negative_failure_samples: int = 100
    
    # Time-series requirements
    max_gap_days_for_continuous: int = 7
    min_temporal_precision_days: int = 1
    
    # Feature engineering
    default_rolling_window: int = 7
    max_lag_periods: int = 30
    
    # Model validation
    train_split_ratio: float = 0.7
    validation_split_ratio: float = 0.15
    test_split_ratio: float = 0.15
    
    # Quality gates
    min_baseline_improvement_pct: float = 5.0
    max_test_train_leakage: float = 0.0
    min_feature_importance_variance: float = 0.01
    
    # Anomaly detection
    anomaly_zscore_threshold: float = 3.0
    anomaly_iqr_multiplier: float = 1.5
    anomaly_rolling_window: int = 30
    
    # Health indicators
    health_degraded_threshold: float = 0.6
    health_at_risk_threshold: float = 0.8
    
    # Model registry
    artifact_dir: str = "project/ml/artifacts"
    max_model_versions: int = 10
    
    # Inference
    default_confidence_threshold: float = 0.7
    max_inference_batch_size: int = 1000
    
    # Data provenance
    require_provenance_tracking: bool = True
    require_feature_tracing: bool = True
    
    # Physics integration
    use_physics_features: bool = True
    physics_feature_source: str = "twin_physics"
    
    # Security
    max_request_size_mb: int = 10
    allow_model_artifact_upload: bool = False
    validate_artifact_paths: bool = True


# Global configuration instance
config = MLConfig()


def get_config() -> MLConfig:
    """Get the global ML configuration."""
    return config


def set_config(new_config: MLConfig) -> None:
    """Set a new global ML configuration."""
    global config
    config = new_config
