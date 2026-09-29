"""Anomaly detection model.

Implements statistical and ML-based anomaly detection.
Distinguishes NORMAL, WARNING, ANOMALY, INSUFFICIENT_CONTEXT.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .config import AnomalyStatus, get_config
from .registry import ModelRegistry
from .schemas import AnomalyResult


class AnomalyDetector:
    """Anomaly detection with statistical baselines and ML methods."""
    
    def __init__(self, registry: ModelRegistry):
        self.config = get_config()
        self.registry = registry
        self.ml_model: Optional[Any] = None
        self.rolling_stats: Dict[str, Dict[str, float]] = {}
    
    def detect(
        self,
        variable: str,
        value: float,
        well_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        historical_data: Optional[pd.DataFrame] = None,
        model_id: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> AnomalyResult:
        """Detect anomalies in a single observation.
        
        Uses multiple methods: rolling z-score, IQR, and optional Isolation Forest.
        """
        
        if historical_data is None or len(historical_data) < self.config.min_observations_for_trend:
            return AnomalyResult(
                variable=variable,
                observed_value=value,
                expected_value=None,
                reference_value=None,
                anomaly_score=0.0,
                status=AnomalyStatus.INSUFFICIENT_CONTEXT,
                method="insufficient_data",
                threshold=0.0,
                timestamp=timestamp or self._get_timestamp(),
                well_id=well_id,
                provenance="insufficient_historical_data",
                explanation="Insufficient historical data for anomaly detection",
                data_quality="INSUFFICIENT_DATA",
                model_id=model_id or "statistical",
                model_version=model_version or "1.0",
                limitations=[
                    f"Need at least {self.config.min_observations_for_trend} historical observations",
                ],
                insufficient_data=True,
                insufficient_reason="Insufficient historical context",
            )
        
        # Get historical values for the variable
        if variable not in historical_data.columns:
            return AnomalyResult(
                variable=variable,
                observed_value=value,
                expected_value=None,
                reference_value=None,
                anomaly_score=0.0,
                status=AnomalyStatus.INSUFFICIENT_CONTEXT,
                method="variable_not_found",
                threshold=0.0,
                timestamp=timestamp or self._get_timestamp(),
                well_id=well_id,
                provenance="variable_not_in_data",
                explanation=f"Variable {variable} not found in historical data",
                data_quality="INVALID",
                model_id=model_id or "statistical",
                model_version=model_version or "1.0",
                limitations=["Variable not available in historical data"],
                insufficient_data=True,
                insufficient_reason="Variable not found",
            )
        
        historical_values = historical_data[variable].dropna()
        
        if len(historical_values) < self.config.min_observations_for_trend:
            return AnomalyResult(
                variable=variable,
                observed_value=value,
                expected_value=None,
                reference_value=None,
                anomaly_score=0.0,
                status=AnomalyStatus.INSUFFICIENT_CONTEXT,
                method="insufficient_data",
                threshold=0.0,
                timestamp=timestamp or self._get_timestamp(),
                well_id=well_id,
                provenance="insufficient_variable_data",
                explanation=f"Insufficient historical data for variable {variable}",
                data_quality="INSUFFICIENT_DATA",
                model_id=model_id or "statistical",
                model_version=model_version or "1.0",
                limitations=[
                    f"Need at least {self.config.min_observations_for_trend} observations for {variable}",
                ],
                insufficient_data=True,
                insufficient_reason="Insufficient variable data",
            )
        
        # Method 1: Rolling z-score
        z_score, z_status, z_explanation = self._rolling_z_score(
            historical_values, value
        )
        
        # Method 2: IQR-based detection
        iqr_score, iqr_status, iqr_explanation = self._iqr_detection(
            historical_values, value
        )
        
        # Combine results (use more conservative status)
        if z_status == AnomalyStatus.ANOMALY or iqr_status == AnomalyStatus.ANOMALY:
            final_status = AnomalyStatus.ANOMALY
            final_score = max(z_score, iqr_score)
            final_method = "combined_z_iqr"
            final_explanation = f"{z_explanation}; {iqr_explanation}"
        elif z_status == AnomalyStatus.WARNING or iqr_status == AnomalyStatus.WARNING:
            final_status = AnomalyStatus.WARNING
            final_score = max(z_score, iqr_score)
            final_method = "combined_z_iqr"
            final_explanation = f"{z_explanation}; {iqr_explanation}"
        else:
            final_status = AnomalyStatus.NORMAL
            final_score = max(z_score, iqr_score)
            final_method = "combined_z_iqr"
            final_explanation = f"{z_explanation}; {iqr_explanation}"
        
        # Expected/reference values
        expected_value = float(historical_values.mean())
        reference_value = float(historical_values.median())
        
        return AnomalyResult(
            variable=variable,
            observed_value=value,
            expected_value=expected_value,
            reference_value=reference_value,
            anomaly_score=final_score,
            status=final_status,
            method=final_method,
            threshold=self.config.anomaly_zscore_threshold,
            timestamp=timestamp or self._get_timestamp(),
            well_id=well_id,
            provenance="statistical_detection",
            explanation=final_explanation,
            data_quality="VALID",
            model_id=model_id or "statistical",
            model_version=model_version or "1.0",
            limitations=[
                "Statistical methods only - no causal inference",
                "Anomaly does not imply failure",
            ],
        )
    
    def _rolling_z_score(
        self, historical_values: pd.Series, current_value: float
    ) -> tuple:
        """Rolling z-score anomaly detection."""
        
        mean = historical_values.mean()
        std = historical_values.std()
        
        if std == 0:
            return 0.0, AnomalyStatus.NORMAL, "No variance in historical data"
        
        z_score = abs((current_value - mean) / std)
        
        if z_score > self.config.anomaly_zscore_threshold:
            status = AnomalyStatus.ANOMALY
            explanation = (
                f"Z-score {z_score:.2f} exceeds threshold {self.config.anomaly_zscore_threshold}. "
                f"Value {current_value:.2f} deviates significantly from mean {mean:.2f}."
            )
        elif z_score > self.config.anomaly_zscore_threshold * 0.7:
            status = AnomalyStatus.WARNING
            explanation = (
                f"Z-score {z_score:.2f} approaching threshold. "
                f"Value {current_value:.2f} shows moderate deviation from mean {mean:.2f}."
            )
        else:
            status = AnomalyStatus.NORMAL
            explanation = (
                f"Z-score {z_score:.2f} within normal range. "
                f"Value {current_value:.2f} consistent with historical mean {mean:.2f}."
            )
        
        return z_score, status, explanation
    
    def _iqr_detection(
        self, historical_values: pd.Series, current_value: float
    ) -> tuple:
        """IQR-based anomaly detection."""
        
        q1 = historical_values.quantile(0.25)
        q3 = historical_values.quantile(0.75)
        iqr = q3 - q1
        
        if iqr == 0:
            return 0.0, AnomalyStatus.NORMAL, "No IQR spread in historical data"
        
        lower_bound = q1 - self.config.anomaly_iqr_multiplier * iqr
        upper_bound = q3 + self.config.anomaly_iqr_multiplier * iqr
        
        if current_value < lower_bound:
            score = (lower_bound - current_value) / iqr
            status = AnomalyStatus.ANOMALY
            explanation = (
                f"Value {current_value:.2f} below IQR lower bound {lower_bound:.2f}. "
                f"Significant downward deviation detected."
            )
        elif current_value > upper_bound:
            score = (current_value - upper_bound) / iqr
            status = AnomalyStatus.ANOMALY
            explanation = (
                f"Value {current_value:.2f} above IQR upper bound {upper_bound:.2f}. "
                f"Significant upward deviation detected."
            )
        else:
            score = 0.0
            status = AnomalyStatus.NORMAL
            explanation = (
                f"Value {current_value:.2f} within IQR range [{lower_bound:.2f}, {upper_bound:.2f}]. "
                f"No significant deviation detected."
            )
        
        return score, status, explanation
    
    def train_isolation_forest(
        self, data: pd.DataFrame, feature_columns: List[str]
    ) -> Dict[str, Any]:
        """Train Isolation Forest for multivariate anomaly detection."""
        
        if len(data) < self.config.min_observations_for_training:
            return {
                "success": False,
                "reason": f"Insufficient data: {len(data)} < {self.config.min_observations_for_training}",
            }
        
        X = data[feature_columns].values
        
        self.ml_model = IsolationForest(
            n_estimators=100,
            contamination=0.1,
            random_state=self.config.random_seed,
        )
        
        self.ml_model.fit(X)
        
        return {
            "success": True,
            "reason": "Isolation Forest trained successfully",
            "feature_columns": feature_columns,
        }
    
    def detect_isolation_forest(
        self, features: np.ndarray
    ) -> tuple:
        """Detect anomalies using trained Isolation Forest."""
        
        if self.ml_model is None:
            return 0.0, AnomalyStatus.INSUFFICIENT_CONTEXT, "Isolation Forest not trained"
        
        anomaly_score = self.ml_model.decision_function(features.reshape(1, -1))[0]
        is_anomaly = self.ml_model.predict(features.reshape(1, -1))[0] == -1
        
        if is_anomaly:
            status = AnomalyStatus.ANOMALY
            explanation = f"Isolation Forest detected anomaly (score: {anomaly_score:.2f})"
        else:
            status = AnomalyStatus.NORMAL
            explanation = f"Isolation Forest detected normal (score: {anomaly_score:.2f})"
        
        return abs(anomaly_score), status, explanation
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
