"""Production forecasting model.

Implements forecasting framework with strong baselines.
Returns INSUFFICIENT_DATA when Baghewala public data cannot support forecasting.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor

from .config import MLEligibility, get_config
from .registry import ModelRegistry
from .schemas import ForecastResult


class ForecastingModel:
    """Production forecasting model with baseline comparison."""
    
    def __init__(self, registry: ModelRegistry):
        self.config = get_config()
        self.registry = registry
        self.model: Optional[Any] = None
        self.baseline_model: Optional[Any] = None
        self.feature_columns: Optional[List[str]] = None
        self.model_name: Optional[str] = None
    
    def train(
        self,
        data: pd.DataFrame,
        target_column: str = "oil_rate_bopd",
        feature_columns: Optional[List[str]] = None,
        model_type: str = "random_forest",
        dataset_id: Optional[str] = None,
        dataset_provenance: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Train forecasting model.
        
        Returns training report with metrics and eligibility determination.
        """
        
        # Check if this is Baghewala public data using explicit provenance
        # Baghewala public data is insufficient for continuous forecasting
        # This is a policy decision from ML_DATA_POLICY.md
        # Check this BEFORE minimum observations to give clear Baghewala rejection
        if self._is_baghewala_public_data(dataset_provenance, dataset_id):
            return {
                "success": False,
                "eligibility": MLEligibility.INSUFFICIENT_DATA,
                "reason": (
                    "Baghewala public data contains sparse observations with no continuous time-series. "
                    "Insufficient for production forecasting per ML_DATA_POLICY.md."
                ),
                "metrics": {},
            }
        
        # Check data eligibility
        if len(data) < self.config.min_observations_for_training:
            return {
                "success": False,
                "eligibility": MLEligibility.INSUFFICIENT_DATA,
                "reason": f"Insufficient observations: {len(data)} < {self.config.min_observations_for_training}",
                "metrics": {},
            }
        
        # Prepare features
        if feature_columns is None:
            # Automatically select numeric columns only, exclude timestamp and target
            feature_columns = [
                col for col in data.columns 
                if col != target_column 
                and col != "timestamp" 
                and pd.api.types.is_numeric_dtype(data[col])
            ]
        
        # Ensure we have at least one feature
        if len(feature_columns) == 0:
            return {
                "success": False,
                "eligibility": MLEligibility.INSUFFICIENT_DATA,
                "reason": "No numeric feature columns available for training",
                "metrics": {},
            }
        
        X = data[feature_columns].values
        y = data[target_column].values
        
        # Store feature columns for inference
        self.feature_columns = feature_columns
        
        # Split data chronologically
        n = len(data)
        train_size = int(n * self.config.train_split_ratio)
        val_size = int(n * self.config.validation_split_ratio)
        
        X_train, y_train = X[:train_size], y[:train_size]
        X_val, y_val = X[train_size:train_size + val_size], y[train_size:train_size + val_size]
        X_test, y_test = X[train_size + val_size:], y[train_size + val_size:]
        
        # Train baseline model (naive last value)
        baseline_pred = self._naive_baseline(y_train, len(y_test))
        baseline_mae = np.mean(np.abs(y_test - baseline_pred))
        
        # Train candidate models on training set only
        candidates = []
        
        # Candidate 1: Random Forest
        rf_model = RandomForestRegressor(
            n_estimators=100,
            random_state=self.config.random_seed,
            max_depth=10,
        )
        rf_model.fit(X_train, y_train)
        
        # Evaluate on validation set
        rf_val_pred = rf_model.predict(X_val)
        rf_val_mae = np.mean(np.abs(y_val - rf_val_pred))
        candidates.append({
            "model": rf_model,
            "name": "random_forest",
            "val_mae": rf_val_mae,
        })
        
        # Candidate 2: HistGradientBoosting
        hgb_model = HistGradientBoostingRegressor(
            max_iter=100,
            random_state=self.config.random_seed,
            max_depth=10,
        )
        hgb_model.fit(X_train, y_train)
        
        # Evaluate on validation set
        hgb_val_pred = hgb_model.predict(X_val)
        hgb_val_mae = np.mean(np.abs(y_val - hgb_val_pred))
        candidates.append({
            "model": hgb_model,
            "name": "hist_gradient_boosting",
            "val_mae": hgb_val_mae,
        })
        
        # Select best model based on validation performance
        best_candidate = min(candidates, key=lambda x: x["val_mae"])
        self.model = best_candidate["model"]
        self.model_name = best_candidate["name"]
        
        # Final evaluation on test set (must not be used for selection)
        y_pred = self.model.predict(X_test)
        mae = np.mean(np.abs(y_test - y_pred))
        rmse = np.sqrt(np.mean((y_test - y_pred) ** 2))
        
        # R² if variance exists
        if np.var(y_test) > 1e-10:
            from sklearn.metrics import r2_score
            r2 = r2_score(y_test, y_pred)
        else:
            r2 = 0.0
        
        # Validation metrics
        val_mae = best_candidate["val_mae"]
        
        # Baseline comparison
        improvement_pct = ((baseline_mae - mae) / baseline_mae * 100) if baseline_mae > 0 else 0.0
        
        metrics = {
            "train_mae": float(np.mean(np.abs(y_train - self.model.predict(X_train)))),
            "val_mae": float(val_mae),
            "test_mae": float(mae),
            "test_rmse": float(rmse),
            "test_r2": float(r2),
            "baseline_mae": float(baseline_mae),
            "mae_improvement_pct": float(improvement_pct),
            "selected_model": best_candidate["name"],
        }
        
        # Check if model beats baseline significantly
        if improvement_pct < self.config.min_baseline_improvement_pct:
            return {
                "success": False,
                "eligibility": MLEligibility.ELIGIBLE,
                "reason": f"Model does not significantly improve over baseline ({improvement_pct:.1f}% < {self.config.min_baseline_improvement_pct}%)",
                "metrics": metrics,
            }
        
        return {
            "success": True,
            "eligibility": MLEligibility.ELIGIBLE,
            "reason": "Model trained successfully and improves over baseline",
            "metrics": metrics,
        }
    
    def forecast(
        self,
        well_id: Optional[str],
        features: Dict[str, Any],
        model_id: Optional[str] = None,
        model_version: Optional[str] = None,
        horizon_days: int = 30,
    ) -> ForecastResult:
        """Generate production forecast.
        
        Returns explicit insufficient_data state when model unavailable.
        """
        
        # Check if model is available
        if self.model is None:
            production_model = self.registry.get_production_model("production_forecast")
            if not production_model:
                return ForecastResult(
                    well_id=well_id or "unknown",
                    forecast_horizon_days=horizon_days,
                    forecasted_values=[],
                    forecast_timestamps=[],
                    data_quality="INSUFFICIENT_DATA",
                    model_id="unavailable",
                    model_version="0.0",
                    limitations=["No trained forecasting model available"],
                    insufficient_data=True,
                    insufficient_reason="MODEL_UNAVAILABLE_INSUFFICIENT_DATA",
                )
        
        # Try to use the trained model for inference
        try:
            # Get feature names from model if available
            if hasattr(self.model, 'feature_names_in_'):
                feature_names = self.model.feature_names_in_
            elif self.feature_columns:
                feature_names = self.feature_columns
            else:
                # Use registry metadata for feature schema
                production_model = self.registry.get_production_model("production_forecast")
                if production_model and production_model.feature_schema:
                    feature_names = list(production_model.feature_schema.keys())
                else:
                    return ForecastResult(
                        well_id=well_id or "unknown",
                        forecast_horizon_days=horizon_days,
                        forecasted_values=[],
                        forecast_timestamps=[],
                        data_quality="INSUFFICIENT_DATA",
                        model_id=model_id or "unknown",
                        model_version=model_version or "0.0",
                        limitations=["Cannot determine feature schema from model"],
                        insufficient_data=True,
                        insufficient_reason="FEATURE_SCHEMA_UNAVAILABLE",
                    )
            
            # Check if required features are provided
            missing_features = [f for f in feature_names if f not in features]
            if missing_features:
                return ForecastResult(
                    well_id=well_id or "unknown",
                    forecast_horizon_days=horizon_days,
                    forecasted_values=[],
                    forecast_timestamps=[],
                    data_quality="INSUFFICIENT_DATA",
                    model_id=model_id or "unknown",
                    model_version=model_version or "0.0",
                    limitations=[f"Missing required features: {missing_features}"],
                    insufficient_data=True,
                    insufficient_reason="MISSING_FEATURES",
                )
            
            # Prepare feature vector in correct order
            feature_vector = [features[f] for f in feature_names]
            
            # Generate forecast (simple multi-step: repeat same prediction)
            # In production, this would use proper time-series forecasting
            forecast_value = self.model.predict([feature_vector])[0]
            forecasted_values = [forecast_value] * horizon_days
            
            # Generate timestamps
            base_time = datetime.now(timezone.utc)
            forecast_timestamps = [(base_time + timedelta(days=i)).isoformat() for i in range(1, horizon_days + 1)]
            
            return ForecastResult(
                well_id=well_id or "unknown",
                forecast_horizon_days=horizon_days,
                forecasted_values=forecasted_values,
                forecast_timestamps=forecast_timestamps,
                data_quality="VALID",
                model_id=model_id or "trained_model",
                model_version=model_version or "1.0",
                limitations=[
                    "Simple multi-step forecast (repeats single prediction)",
                    "Not field-calibrated for Baghewala",
                    "Requires legitimate training data for production use",
                ],
                insufficient_data=False,
                insufficient_reason=None,
            )
            
        except Exception as e:
            return ForecastResult(
                well_id=well_id or "unknown",
                forecast_horizon_days=horizon_days,
                forecasted_values=[],
                forecast_timestamps=[],
                data_quality="ERROR",
                model_id=model_id or "unknown",
                model_version=model_version or "0.0",
                limitations=[f"Inference error: {str(e)}"],
                insufficient_data=True,
                insufficient_reason="INFERENCE_ERROR",
            )
    
    def _naive_baseline(self, y_train: np.ndarray, test_len: int) -> np.ndarray:
        """Naive baseline: last value repeated."""
        last_value = y_train[-1]
        return np.full(test_len, last_value)
    
    def _is_baghewala_public_data(self, dataset_provenance: Optional[str], dataset_id: Optional[str]) -> bool:
        """Check if data is Baghewala public or synthetic data using explicit provenance.

        Uses dataset_id and provenance metadata for reliable identification.
        No row-count heuristics — explicit provenance only.

        Covers:
          - BAGHEWALA_FIELD  : measured/reported public field data
          - PUBLIC_BAGHEWALA : alternate tag for the same corpus
          - SYNTHETIC_BAGHEWALA : synthetic data derived from Baghewala parameters
                                   (kept separate from production but still rejected
                                    because it is not legitimate external reference data)
        """
        # Check explicit provenance string
        if dataset_provenance:
            baghewala_provenances = [
                "BAGHEWALA_FIELD",
                "PUBLIC_BAGHEWALA",
                "SYNTHETIC_BAGHEWALA",
            ]
            if any(prov in dataset_provenance.upper() for prov in baghewala_provenances):
                return True

        # Check explicit dataset_id
        if dataset_id:
            baghewala_dataset_ids = [
                "baghewala_public",
                "baghewala_field",
                "public_baghewala",
                "synthetic_baghewala",
            ]
            if any(bag_id in dataset_id.lower() for bag_id in baghewala_dataset_ids):
                return True

        # Default: not Baghewala data
        return False
