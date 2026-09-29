"""Unified inference engine for ML predictions.

Provides a single interface for all ML tasks.
Returns explicit insufficient-data states when models are unavailable.
"""

from typing import Any, Dict, Optional

from .config import ModelTask, get_config
from .forecasting import ForecastingModel
from .anomaly import AnomalyDetector
from .srp_health import SRPHealthModel
from .failure import FailurePredictionModel
from .registry import ModelRegistry
from .schemas import (
    PredictionRequest,
    PredictionResponse,
    ForecastResult,
    AnomalyResult,
    HealthResult,
    FailureRiskResult,
)


class InferenceEngine:
    """Unified inference engine for all ML tasks."""
    
    def __init__(self):
        self.config = get_config()
        self.registry = ModelRegistry()
        
        # Initialize task-specific models
        self.forecasting_model = ForecastingModel(self.registry)
        self.anomaly_detector = AnomalyDetector(self.registry)
        self.srp_health_model = SRPHealthModel(self.registry)
        self.failure_model = FailurePredictionModel(self.registry)
    
    def predict(self, request: PredictionRequest) -> PredictionResponse:
        """Unified prediction interface.
        
        Routes to appropriate task-specific model based on request task.
        """
        
        try:
            if request.task == ModelTask.PRODUCTION_FORECAST:
                return self._forecast(request)
            elif request.task == ModelTask.ANOMALY_DETECTION:
                return self._detect_anomaly(request)
            elif request.task == ModelTask.SRP_HEALTH:
                return self._assess_health(request)
            elif request.task == ModelTask.FAILURE_RISK:
                return self._predict_failure(request)
            else:
                return PredictionResponse(
                    task=request.task,
                    prediction=None,
                    model_id="unavailable",
                    model_version="0.0",
                    timestamp=self._get_timestamp(),
                    data_quality="UNKNOWN",
                    warnings=[f"Unknown task: {request.task}"],
                    limitations=["Task not supported"],
                    insufficient_data=True,
                    insufficient_reason="Task not supported",
                )
        except Exception as e:
            return PredictionResponse(
                task=request.task,
                prediction=None,
                model_id="error",
                model_version="0.0",
                timestamp=self._get_timestamp(),
                data_quality="ERROR",
                warnings=[f"Inference error: {str(e)}"],
                limitations=["Error during inference"],
                insufficient_data=True,
                insufficient_reason=f"Error: {str(e)}",
            )
    
    def _forecast(self, request: PredictionRequest) -> PredictionResponse:
        """Route to forecasting model."""
        
        result = self.forecasting_model.forecast(
            well_id=request.well_id,
            features=request.features,
            model_id=request.model_id,
            model_version=request.model_version,
        )
        
        return PredictionResponse(
            task=ModelTask.PRODUCTION_FORECAST,
            prediction=result.forecasted_values if not result.insufficient_data else None,
            confidence=None,  # Forecasting may not have confidence
            model_id=result.model_id,
            model_version=result.model_version,
            timestamp=self._get_timestamp(),
            feature_provenance={},  # Would be populated by model
            data_quality=result.data_quality,
            warnings=result.limitations,
            limitations=result.limitations,
            insufficient_data=result.insufficient_data,
            insufficient_reason=result.insufficient_reason,
        )
    
    def _detect_anomaly(self, request: PredictionRequest) -> PredictionResponse:
        """Route to anomaly detector."""
        
        result = self.anomaly_detector.detect(
            variable=request.features.get("variable", "unknown"),
            value=request.features.get("value", 0.0),
            well_id=request.well_id,
            model_id=request.model_id,
            model_version=request.model_version,
        )
        
        return PredictionResponse(
            task=ModelTask.ANOMALY_DETECTION,
            prediction=result.status.value if not result.insufficient_data else None,
            confidence=result.anomaly_score if not result.insufficient_data else None,
            model_id=result.model_id,
            model_version=result.model_version,
            timestamp=self._get_timestamp(),
            feature_provenance={},
            data_quality=result.data_quality,
            warnings=result.limitations,
            limitations=result.limitations,
            insufficient_data=result.insufficient_data,
            insufficient_reason=result.insufficient_reason,
        )
    
    def _assess_health(self, request: PredictionRequest) -> PredictionResponse:
        """Route to SRP health model."""
        
        result = self.srp_health_model.assess(
            well_id=request.well_id,
            features=request.features,
            model_id=request.model_id,
            model_version=request.model_version,
        )
        
        return PredictionResponse(
            task=ModelTask.SRP_HEALTH,
            prediction=result.health_status.value if not result.insufficient_data else None,
            confidence=result.health_score if not result.insufficient_data else None,
            model_id=result.model_id,
            model_version=result.model_version,
            timestamp=self._get_timestamp(),
            feature_provenance={},
            data_quality=result.data_quality,
            warnings=result.limitations,
            limitations=result.limitations,
            insufficient_data=result.insufficient_data,
            insufficient_reason=result.insufficient_reason,
        )
    
    def _predict_failure(self, request: PredictionRequest) -> PredictionResponse:
        """Route to failure prediction model."""
        
        result = self.failure_model.predict(
            well_id=request.well_id,
            features=request.features,
            model_id=request.model_id,
            model_version=request.model_version,
        )
        
        return PredictionResponse(
            task=ModelTask.FAILURE_RISK,
            prediction=result.failure_probability if not result.insufficient_data else None,
            confidence=result.confidence if not result.insufficient_data else None,
            model_id=result.model_id,
            model_version=result.model_version,
            timestamp=self._get_timestamp(),
            feature_provenance={},
            data_quality=result.data_quality,
            warnings=result.limitations,
            limitations=result.limitations,
            insufficient_data=result.insufficient_data,
            insufficient_reason=result.insufficient_reason,
        )
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
    
    def get_available_models(self) -> Dict[str, Any]:
        """Get information about available models."""
        
        return {
            "production_forecast": self._get_model_info(ModelTask.PRODUCTION_FORECAST),
            "anomaly_detection": self._get_model_info(ModelTask.ANOMALY_DETECTION),
            "srp_health": self._get_model_info(ModelTask.SRP_HEALTH),
            "failure_risk": self._get_model_info(ModelTask.FAILURE_RISK),
        }
    
    def _get_model_info(self, task: ModelTask) -> Dict[str, Any]:
        """Get model information for a task."""
        
        production_model = self.registry.get_production_model(task.value)
        
        if production_model:
            return {
                "available": True,
                "model_id": production_model.model_id,
                "model_version": production_model.version,
                "status": production_model.status.value,
                "eligibility": production_model.eligibility.value,
                "limitations": production_model.limitations,
            }
        else:
            return {
                "available": False,
                "model_id": None,
                "model_version": None,
                "status": "UNAVAILABLE",
                "eligibility": "INSUFFICIENT_DATA",
                "limitations": ["No trained model available for this task"],
            }
