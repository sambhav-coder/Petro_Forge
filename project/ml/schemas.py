"""ML schemas using Pydantic for validation and serialization.

Consistent with existing data schema patterns in project/data/schema.py
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .config import (
    AnomalyStatus,
    HealthStatus,
    MLEligibility,
    ModelStatus,
    ModelTask,
)


class DatasetValidationReport(BaseModel):
    """Validation report for a dataset."""
    
    dataset_name: str = Field(..., min_length=1)
    dataset_version: str = "1.0"
    rows: int = Field(..., ge=0)
    features: int = Field(..., ge=0)
    target: Optional[str] = None
    missing_value_count: int = Field(..., ge=0)
    duplicate_count: int = Field(..., ge=0)
    entity_count: int = Field(..., ge=0)
    time_span_start: Optional[str] = None
    time_span_end: Optional[str] = None
    class_balance: Optional[Dict[str, int]] = None
    units: Dict[str, str] = Field(default_factory=dict)
    ml_eligible: MLEligibility
    eligibility_reason: str = Field(..., min_length=1)
    suitable_for: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    validation_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ModelMetadata(BaseModel):
    """Metadata for a trained model."""
    
    model_id: str = Field(..., min_length=1)
    task: ModelTask
    version: str = Field(..., min_length=1)
    status: ModelStatus
    dataset_id: str = Field(..., min_length=1)
    dataset_version: str
    feature_schema: Dict[str, str] = Field(default_factory=dict)
    hyperparameters: Dict[str, Any] = Field(default_factory=dict)
    training_timestamp: str
    metrics: Dict[str, float] = Field(default_factory=dict)
    validation_metrics: Dict[str, float] = Field(default_factory=dict)
    test_metrics: Dict[str, float] = Field(default_factory=dict)
    artifact_path: Optional[str] = None
    eligibility: MLEligibility
    limitations: List[str] = Field(default_factory=list)
    provenance: Dict[str, str] = Field(default_factory=dict)
    code_version: Optional[str] = None


class PredictionRequest(BaseModel):
    """Generic prediction request."""
    
    task: ModelTask
    well_id: Optional[str] = None
    features: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    return_explanations: bool = False


class PredictionResponse(BaseModel):
    """Generic prediction response."""
    
    task: ModelTask
    prediction: Any
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    model_id: str
    model_version: str
    timestamp: str
    feature_provenance: Dict[str, str] = Field(default_factory=dict)
    data_quality: str = "UNKNOWN"
    warnings: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    insufficient_data: bool = False
    insufficient_reason: Optional[str] = None


class ForecastResult(BaseModel):
    """Production forecasting result."""
    
    well_id: str
    forecast_horizon_days: int
    forecasted_values: List[float]
    forecast_timestamps: List[str]
    baseline_values: Optional[List[float]] = None
    metrics: Dict[str, float] = Field(default_factory=dict)
    confidence_intervals: Optional[List[Dict[str, float]]] = None
    trend_direction: Optional[str] = None
    data_quality: str
    model_id: str
    model_version: str
    limitations: List[str] = Field(default_factory=list)
    insufficient_data: bool = False
    insufficient_reason: Optional[str] = None


class AnomalyResult(BaseModel):
    """Anomaly detection result."""
    
    variable: str
    observed_value: float
    expected_value: Optional[float] = None
    reference_value: Optional[float] = None
    anomaly_score: float = Field(..., ge=0.0)
    status: AnomalyStatus
    method: str
    threshold: float
    timestamp: str
    well_id: Optional[str] = None
    provenance: str
    explanation: str
    data_quality: str
    model_id: str
    model_version: str
    limitations: List[str] = Field(default_factory=list)
    insufficient_data: bool = False
    insufficient_reason: Optional[str] = None


class HealthResult(BaseModel):
    """SRP/pump health result."""
    
    well_id: str
    health_status: HealthStatus
    health_score: float = Field(..., ge=0.0, le=1.0)
    contributing_factors: List[Dict[str, Any]] = Field(default_factory=list)
    spm_status: Optional[str] = None
    stroke_status: Optional[str] = None
    load_status: Optional[str] = None
    fillage_status: Optional[str] = None
    data_quality: str
    model_id: str
    model_version: str
    limitations: List[str] = Field(default_factory=list)
    insufficient_data: bool = False
    insufficient_reason: Optional[str] = None


class FailureRiskResult(BaseModel):
    """Failure prediction result."""
    
    well_id: str
    failure_probability: Optional[float] = Field(None, ge=0.0, le=1.0)
    risk_level: Optional[str] = None
    failure_class: Optional[str] = None
    time_to_failure_days: Optional[int] = None
    contributing_factors: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    data_quality: str
    model_id: str
    model_version: str
    limitations: List[str] = Field(default_factory=list)
    insufficient_data: bool = False
    insufficient_reason: Optional[str] = None


class FeatureImportance(BaseModel):
    """Feature importance for explainability."""
    
    feature_name: str
    importance: float
    source: str
    direction: Optional[str] = None  # "positive" or "negative"


class ExplainabilityResult(BaseModel):
    """Explainability result for a prediction."""
    
    prediction_id: str
    top_features: List[FeatureImportance]
    feature_contributions: Dict[str, float] = Field(default_factory=dict)
    baseline_prediction: Optional[float] = None
    model_type: str
    limitations: List[str] = Field(default_factory=list)
