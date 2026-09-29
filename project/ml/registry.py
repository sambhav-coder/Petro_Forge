"""Model registry for tracking ML models.

Maintains metadata, status, and artifact locations for all models.
Implements quality gates for model promotion.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import MLEligibility, ModelStatus, get_config
from .schemas import ModelMetadata


class ModelRegistry:
    """Registry for tracking ML models throughout their lifecycle."""
    
    def __init__(self, artifact_dir: Optional[str] = None):
        self.config = get_config()
        self.artifact_dir = artifact_dir or self.config.artifact_dir
        self.models: Dict[str, ModelMetadata] = {}
        self._load_registry()
    
    def _load_registry(self) -> None:
        """Load model registry from disk if exists."""
        registry_path = os.path.join(self.artifact_dir, "registry.json")
        if os.path.exists(registry_path):
            try:
                with open(registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for model_id, model_data in data.items():
                        self.models[model_id] = ModelMetadata(**model_data)
            except (json.JSONDecodeError, IOError):
                pass
    
    def _save_registry(self) -> None:
        """Save model registry to disk."""
        os.makedirs(self.artifact_dir, exist_ok=True)
        registry_path = os.path.join(self.artifact_dir, "registry.json")
        
        data = {
            model_id: model.model_dump()
            for model_id, model in self.models.items()
        }
        
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    
    def register_model(
        self,
        model_id: str,
        task: str,
        version: str,
        dataset_id: str,
        dataset_version: str,
        feature_schema: Dict[str, str],
        hyperparameters: Dict[str, Any],
        metrics: Dict[str, float],
        validation_metrics: Dict[str, float],
        test_metrics: Dict[str, float],
        artifact_path: Optional[str] = None,
        eligibility: MLEligibility = MLEligibility.ELIGIBLE,
        limitations: Optional[List[str]] = None,
        provenance: Optional[Dict[str, str]] = None,
        code_version: Optional[str] = None,
    ) -> ModelMetadata:
        """Register a new model in the registry."""
        
        model = ModelMetadata(
            model_id=model_id,
            task=task,
            version=version,
            status=ModelStatus.CANDIDATE,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            feature_schema=feature_schema,
            hyperparameters=hyperparameters,
            training_timestamp=datetime.now(timezone.utc).isoformat(),
            metrics=metrics,
            validation_metrics=validation_metrics,
            test_metrics=test_metrics,
            artifact_path=artifact_path,
            eligibility=eligibility,
            limitations=limitations or [],
            provenance=provenance or {},
            code_version=code_version,
        )
        
        self.models[model_id] = model
        self._save_registry()
        
        return model
    
    def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        """Get model metadata by ID."""
        return self.models.get(model_id)
    
    def list_models(
        self,
        task: Optional[str] = None,
        status: Optional[ModelStatus] = None,
        eligibility: Optional[MLEligibility] = None,
    ) -> List[ModelMetadata]:
        """List models with optional filtering."""
        
        models = list(self.models.values())
        
        if task:
            models = [m for m in models if m.task == task]
        
        if status:
            models = [m for m in models if m.status == status]
        
        if eligibility:
            models = [m for m in models if m.eligibility == eligibility]
        
        return models
    
    def update_status(
        self,
        model_id: str,
        new_status: ModelStatus,
    ) -> bool:
        """Update model status."""
        
        if model_id not in self.models:
            return False
        
        self.models[model_id].status = new_status
        self._save_registry()
        
        return True
    
    def promote_to_production(
        self,
        model_id: str,
    ) -> bool:
        """Promote a model to production with quality gate checks."""
        
        model = self.get_model(model_id)
        if not model:
            return False
        
        # Quality gate checks
        if not self._check_quality_gates(model):
            return False
        
        # Update status
        self.update_status(model_id, ModelStatus.PRODUCTION)
        
        return True
    
    def _check_quality_gates(self, model: ModelMetadata) -> bool:
        """Check if model meets quality gates for promotion."""
        
        # Check eligibility
        if model.eligibility != MLEligibility.ELIGIBLE:
            return False
        
        # Check test metrics exist
        if not model.test_metrics:
            return False
        
        # Check baseline improvement (if applicable)
        # This would require baseline comparison data
        # For now, just check that metrics exist
        
        # Check feature schema
        if not model.feature_schema:
            return False
        
        # Check no severe limitations
        critical_limitations = [
            "insufficient data",
            "data leakage",
            "invalid provenance",
        ]
        for lim in model.limitations:
            if any(crit in lim.lower() for crit in critical_limitations):
                return False
        
        return True
    
    def retire_model(self, model_id: str) -> bool:
        """Retire a model from production."""
        
        return self.update_status(model_id, ModelStatus.RETIRED)
    
    def mark_unavailable(
        self,
        model_id: str,
        reason: str,
    ) -> bool:
        """Mark a model as unavailable with reason."""
        
        model = self.get_model(model_id)
        if not model:
            return False
        
        model.status = ModelStatus.UNAVAILABLE
        model.eligibility = MLEligibility.INSUFFICIENT_DATA
        model.limitations.append(reason)
        self._save_registry()
        
        return True
    
    def get_production_model(self, task: str) -> Optional[ModelMetadata]:
        """Get the current production model for a task."""
        
        production_models = self.list_models(task=task, status=ModelStatus.PRODUCTION)
        
        if not production_models:
            return None
        
        # Return the most recently trained production model
        return max(production_models, key=lambda m: m.training_timestamp)
    
    def delete_model(self, model_id: str) -> bool:
        """Delete a model from the registry."""
        
        if model_id not in self.models:
            return False
        
        del self.models[model_id]
        self._save_registry()
        
        return True
    
    def get_registry_summary(self) -> Dict[str, Any]:
        """Get summary of the model registry."""
        
        summary = {
            "total_models": len(self.models),
            "by_status": {},
            "by_task": {},
            "by_eligibility": {},
        }
        
        for model in self.models.values():
            # Count by status
            status = model.status.value
            summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
            
            # Count by task
            task = model.task
            summary["by_task"][task] = summary["by_task"].get(task, 0) + 1
            
            # Count by eligibility
            eligibility = model.eligibility.value
            summary["by_eligibility"][eligibility] = summary["by_eligibility"].get(eligibility, 0) + 1
        
        return summary
