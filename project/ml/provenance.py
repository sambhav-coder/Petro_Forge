"""ML data provenance tracking.

Ensures every model output can be traced to input dataset, observation IDs,
feature generation, model version, and training dataset version.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import get_config


@dataclass
class FeatureProvenance:
    """Provenance information for a single feature."""
    
    feature_name: str
    source_columns: List[str]
    method: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    derived_from: Optional[str] = None  # Parent feature if this is derived


@dataclass
class ModelProvenance:
    """Provenance information for a model prediction."""
    
    model_id: str
    model_version: str
    training_dataset_id: str
    training_dataset_version: str
    training_dataset_hash: str
    feature_schema: Dict[str, str]
    training_timestamp: str
    code_version: Optional[str] = None
    hyperparameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictionProvenance:
    """Provenance information for a single prediction."""
    
    prediction_id: str
    model_provenance: ModelProvenance
    input_observation_ids: List[str]
    feature_provenance: Dict[str, FeatureProvenance]
    input_data_hash: str
    prediction_timestamp: str
    data_quality: str
    warnings: List[str] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=dict)


class ProvenanceTracker:
    """Tracks ML data provenance throughout the pipeline."""
    
    def __init__(self):
        self.config = get_config()
        self.feature_registry: Dict[str, FeatureProvenance] = {}
        self.model_registry: Dict[str, ModelProvenance] = {}
        self.prediction_history: List[PredictionProvenance] = []
    
    def register_feature(
        self,
        feature_name: str,
        source_columns: List[str],
        method: str,
        parameters: Optional[Dict[str, Any]] = None,
        derived_from: Optional[str] = None,
    ) -> FeatureProvenance:
        """Register a feature with its provenance."""
        
        provenance = FeatureProvenance(
            feature_name=feature_name,
            source_columns=source_columns,
            method=method,
            parameters=parameters or {},
            derived_from=derived_from,
        )
        
        self.feature_registry[feature_name] = provenance
        return provenance
    
    def get_feature_provenance(self, feature_name: str) -> Optional[FeatureProvenance]:
        """Get provenance for a feature."""
        return self.feature_registry.get(feature_name)
    
    def register_model(
        self,
        model_id: str,
        model_version: str,
        training_dataset_id: str,
        training_dataset_version: str,
        training_dataset_hash: str,
        feature_schema: Dict[str, str],
        training_timestamp: str,
        code_version: Optional[str] = None,
        hyperparameters: Optional[Dict[str, Any]] = None,
    ) -> ModelProvenance:
        """Register a model with its training provenance."""
        
        provenance = ModelProvenance(
            model_id=model_id,
            model_version=model_version,
            training_dataset_id=training_dataset_id,
            training_dataset_version=training_dataset_version,
            training_dataset_hash=training_dataset_hash,
            feature_schema=feature_schema,
            training_timestamp=training_timestamp,
            code_version=code_version,
            hyperparameters=hyperparameters or {},
        )
        
        self.model_registry[model_id] = provenance
        return provenance
    
    def get_model_provenance(self, model_id: str) -> Optional[ModelProvenance]:
        """Get provenance for a model."""
        return self.model_registry.get(model_id)
    
    def record_prediction(
        self,
        prediction_id: str,
        model_id: str,
        input_observation_ids: List[str],
        input_data: Dict[str, Any],
        data_quality: str,
        warnings: Optional[List[str]] = None,
        limitations: Optional[List[str]] = None,
    ) -> PredictionProvenance:
        """Record provenance for a prediction."""
        
        model_provenance = self.get_model_provenance(model_id)
        if not model_provenance:
            raise ValueError(f"Model {model_id} not found in provenance registry")
        
        # Hash input data
        input_data_hash = self._hash_data(input_data)
        
        # Get feature provenance for all features in input
        feature_provenance = {}
        for feature_name in input_data.keys():
            feat_prov = self.get_feature_provenance(feature_name)
            if feat_prov:
                feature_provenance[feature_name] = feat_prov
        
        provenance = PredictionProvenance(
            prediction_id=prediction_id,
            model_provenance=model_provenance,
            input_observation_ids=input_observation_ids,
            feature_provenance=feature_provenance,
            input_data_hash=input_data_hash,
            prediction_timestamp=datetime.now(timezone.utc).isoformat(),
            data_quality=data_quality,
            warnings=warnings or [],
            limitations=limitations or [],
        )
        
        self.prediction_history.append(provenance)
        return provenance
    
    def get_prediction_provenance(self, prediction_id: str) -> Optional[PredictionProvenance]:
        """Get provenance for a prediction."""
        for prov in self.prediction_history:
            if prov.prediction_id == prediction_id:
                return prov
        return None
    
    def trace_lineage(self, feature_name: str) -> List[FeatureProvenance]:
        """Trace the lineage of a feature back to source columns."""
        
        lineage = []
        current_feature = feature_name
        
        while current_feature:
            prov = self.get_feature_provenance(current_feature)
            if not prov:
                break
            
            lineage.append(prov)
            current_feature = prov.derived_from
        
        return lineage
    
    def _hash_data(self, data: Dict[str, Any]) -> str:
        """Create a hash of input data for provenance tracking."""
        
        # Sort keys for consistent hashing
        sorted_data = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(sorted_data.encode()).hexdigest()
    
    def get_provenance_summary(self) -> Dict[str, Any]:
        """Get summary of provenance tracking."""
        
        return {
            "total_features": len(self.feature_registry),
            "total_models": len(self.model_registry),
            "total_predictions": len(self.prediction_history),
            "feature_names": list(self.feature_registry.keys()),
            "model_ids": list(self.model_registry.keys()),
        }
    
    def clear_history(self) -> None:
        """Clear prediction history (for testing)."""
        self.prediction_history = []
    
    def export_provenance(self, prediction_id: str) -> Dict[str, Any]:
        """Export full provenance for a prediction."""
        
        prov = self.get_prediction_provenance(prediction_id)
        if not prov:
            return {"error": f"Prediction {prediction_id} not found"}
        
        return {
            "prediction_id": prov.prediction_id,
            "prediction_timestamp": prov.prediction_timestamp,
            "model": {
                "model_id": prov.model_provenance.model_id,
                "model_version": prov.model_provenance.model_version,
                "training_dataset_id": prov.model_provenance.training_dataset_id,
                "training_dataset_version": prov.model_provenance.training_dataset_version,
                "training_dataset_hash": prov.model_provenance.training_dataset_hash,
                "training_timestamp": prov.model_provenance.training_timestamp,
                "code_version": prov.model_provenance.code_version,
                "hyperparameters": prov.model_provenance.hyperparameters,
            },
            "input_data": {
                "observation_ids": prov.input_observation_ids,
                "data_hash": prov.input_data_hash,
                "data_quality": prov.data_quality,
            },
            "features": {
                feature_name: {
                    "source_columns": feat_prov.source_columns,
                    "method": feat_prov.method,
                    "parameters": feat_prov.parameters,
                    "derived_from": feat_prov.derived_from,
                }
                for feature_name, feat_prov in prov.feature_provenance.items()
            },
            "warnings": prov.warnings,
            "limitations": prov.limitations,
        }


# Global provenance tracker instance
provenance_tracker = ProvenanceTracker()


def get_provenance_tracker() -> ProvenanceTracker:
    """Get the global provenance tracker."""
    return provenance_tracker
