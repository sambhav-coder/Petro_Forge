"""Explainability for ML predictions.

Provides feature importance and prediction explanations.
Distinguishes MODEL ASSOCIATION from PHYSICAL CAUSATION.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .schemas import ExplainabilityResult, FeatureImportance


class ExplainabilityEngine:
    """Provides explainability for ML predictions."""
    
    def __init__(self):
        self.feature_importance_cache: Dict[str, List[FeatureImportance]] = {}
    
    def get_feature_importance(
        self,
        model: Any,
        feature_names: List[str],
        model_id: str,
    ) -> List[FeatureImportance]:
        """Get feature importance from a trained model."""
        
        # Check cache
        if model_id in self.feature_importance_cache:
            return self.feature_importance_cache[model_id]
        
        importance_list = []
        
        # Try to get feature importance from model
        if hasattr(model, "feature_importances_"):
            # Tree-based models (RandomForest, etc.)
            importances = model.feature_importances_
            
            for name, importance in zip(feature_names, importances):
                direction = "positive" if importance > 0 else "negative"
                importance_list.append(
                    FeatureImportance(
                        feature_name=name,
                        importance=float(importance),
                        source="model_feature_importance",
                        direction=direction,
                    )
                )
        
        elif hasattr(model, "coef_"):
            # Linear models
            coefs = model.coef_
            
            for name, coef in zip(feature_names, coefs):
                direction = "positive" if coef > 0 else "negative"
                importance_list.append(
                    FeatureImportance(
                        feature_name=name,
                        importance=float(abs(coef)),
                        source="model_coefficient",
                        direction=direction,
                    )
                )
        
        else:
            # Model doesn't support feature importance
            importance_list = [
                FeatureImportance(
                    feature_name=name,
                    importance=0.0,
                    source="unknown",
                    direction=None,
                )
                for name in feature_names
            ]
        
        # Sort by importance
        importance_list.sort(key=lambda x: x.importance, reverse=True)
        
        # Cache
        self.feature_importance_cache[model_id] = importance_list
        
        return importance_list
    
    def explain_prediction(
        self,
        model: Any,
        features: Dict[str, float],
        feature_names: List[str],
        model_id: str,
        top_k: int = 5,
    ) -> ExplainabilityResult:
        """Explain a single prediction."""
        
        # Get feature importance
        feature_importance = self.get_feature_importance(model, feature_names, model_id)
        
        # Get top features
        top_features = feature_importance[:top_k]
        
        # Calculate feature contributions (simplified)
        feature_contributions = {}
        for feat_imp in top_features:
            feature_name = feat_imp.feature_name
            if feature_name in features:
                value = features[feature_name]
                contribution = feat_imp.importance * value
                feature_contributions[feature_name] = contribution
        
        # Determine model type
        model_type = self._get_model_type(model)
        
        return ExplainabilityResult(
            prediction_id=f"{model_id}_{np.datetime64('now')}",
            top_features=top_features,
            feature_contributions=feature_contributions,
            baseline_prediction=None,  # Would require SHAP or similar
            model_type=model_type,
            limitations=[
                "Feature importance indicates association, not causation",
                "Explanations are model-specific, not physical laws",
                "Correlation does not imply causation",
            ],
        )
    
    def _get_model_type(self, model: Any) -> str:
        """Determine model type for explanation."""
        
        if hasattr(model, "feature_importances_"):
            return "tree_based"
        elif hasattr(model, "coef_"):
            return "linear"
        elif hasattr(model, "predict_proba"):
            return "probabilistic"
        else:
            return "unknown"
    
    def generate_explanation_text(
        self,
        result: ExplainabilityResult,
        prediction_value: float,
    ) -> str:
        """Generate human-readable explanation text."""
        
        lines = []
        lines.append("Top contributing signals:")
        
        for feat in result.top_features:
            direction_symbol = "+" if feat.direction == "positive" else "-"
            lines.append(
                f"- {direction_symbol} {feat.feature_name} (importance: {feat.importance:.3f})"
            )
        
        lines.append("")
        lines.append("Note: These are model associations, not physical causation.")
        lines.append("The model identifies patterns but does not establish cause-effect relationships.")
        
        return "\n".join(lines)
    
    def clear_cache(self) -> None:
        """Clear feature importance cache."""
        self.feature_importance_cache = {}
