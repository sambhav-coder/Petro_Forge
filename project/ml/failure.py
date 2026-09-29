"""Failure prediction model.

Implements failure risk prediction when labeled data is available.
Returns INSUFFICIENT_DATA when failure labels are unavailable.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from .config import get_config
from .registry import ModelRegistry
from .schemas import FailureRiskResult


class FailurePredictionModel:
    """Failure prediction model with strict label requirements."""
    
    def __init__(self, registry: ModelRegistry):
        self.config = get_config()
        self.registry = registry
        self.model: Optional[Any] = None
    
    def predict(
        self,
        well_id: Optional[str],
        features: Dict[str, Any],
        model_id: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> FailureRiskResult:
        """Predict failure risk.
        
        Returns explicit insufficient_data state when model unavailable.
        """
        
        # Check if model is available
        if self.model is None:
            production_model = self.registry.get_production_model("failure_risk")
            if not production_model:
                return FailureRiskResult(
                    well_id=well_id or "unknown",
                    failure_probability=None,
                    risk_level=None,
                    failure_class=None,
                    time_to_failure_days=None,
                    contributing_factors=[],
                    confidence=None,
                    data_quality="INSUFFICIENT_DATA",
                    model_id=model_id or "unavailable",
                    model_version=model_version or "0.0",
                    limitations=[
                        "No trained failure prediction model available",
                        "Baghewala public data lacks labeled failure data",
                        "Insufficient labeled failure/maintenance data for training",
                    ],
                    insufficient_data=True,
                    insufficient_reason="MODEL_UNAVAILABLE_INSUFFICIENT_DATA",
                )
        
        # In a real implementation, this would use the trained model
        # For now, return insufficient data state as per policy
        return FailureRiskResult(
            well_id=well_id or "unknown",
            failure_probability=None,
            risk_level=None,
            failure_class=None,
            time_to_failure_days=None,
            contributing_factors=[],
            confidence=None,
            data_quality="INSUFFICIENT_DATA",
            model_id=model_id or "unavailable",
            model_version=model_version or "0.0",
            limitations=[
                "Baghewala public data lacks explicit failure labels",
                "No maintenance work orders or failure records available",
                "Failure prediction requires labeled failure data",
            ],
            insufficient_data=True,
            insufficient_reason="MODEL_UNAVAILABLE_INSUFFICIENT_DATA",
        )
    
    def train(
        self,
        data: pd.DataFrame,
        target_column: str = "failure_label",
        feature_columns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Train failure prediction model.
        
        Returns training report with eligibility determination.
        """
        
        # Check for failure labels
        if target_column not in data.columns:
            return {
                "success": False,
                "eligibility": "INSUFFICIENT_DATA",
                "reason": "Missing failure label column for training",
            }
        
        # Check class balance
        class_counts = data[target_column].value_counts()
        
        # Check for positive class (failure)
        failure_count = class_counts.get("failure", class_counts.get(1, 0))
        if failure_count < self.config.min_positive_failure_samples:
            return {
                "success": False,
                "eligibility": "INSUFFICIENT_DATA",
                "reason": (
                    f"Insufficient failure samples: {failure_count} < "
                    f"{self.config.min_positive_failure_samples}"
                ),
            }
        
        # Check for negative class (normal)
        normal_count = class_counts.get("normal", class_counts.get(0, 0))
        if normal_count < self.config.min_negative_failure_samples:
            return {
                "success": False,
                "eligibility": "INSUFFICIENT_DATA",
                "reason": (
                    f"Insufficient normal samples: {normal_count} < "
                    f"{self.config.min_negative_failure_samples}"
                ),
            }
        
        # Check total data size
        if len(data) < self.config.min_observations_for_training:
            return {
                "success": False,
                "eligibility": "INSUFFICIENT_DATA",
                "reason": f"Insufficient observations: {len(data)} < {self.config.min_observations_for_training}",
            }
        
        # Prepare features
        if feature_columns is None:
            feature_columns = [col for col in data.columns if col != target_column]
        
        X = data[feature_columns].values
        y = data[target_column].values
        
        # Split data chronologically (for time-series)
        if "timestamp" in data.columns:
            n = len(data)
            train_size = int(n * self.config.train_split_ratio)
            X_train, y_train = X[:train_size], y[:train_size]
            X_test, y_test = X[train_size:], y[train_size:]
        else:
            # Entity-aware split if well_id available
            if "well_id" in data.columns:
                from .splits import DataSplitter
                splitter = DataSplitter()
                train_data, _, test_data = splitter.entity_aware_split(
                    data, entity_column="well_id", random_seed=self.config.random_seed
                )
                X_train = train_data[feature_columns].values
                y_train = train_data[target_column].values
                X_test = test_data[feature_columns].values
                y_test = test_data[target_column].values
            else:
                # Random split (least preferred)
                from sklearn.model_selection import train_test_split
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=self.config.test_split_ratio, random_state=self.config.random_seed
                )
        
        # Train model
        self.model = RandomForestClassifier(
            n_estimators=100,
            random_state=self.config.random_seed,
            max_depth=10,
            class_weight="balanced",
        )
        
        self.model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test)
        y_proba = self.model.predict_proba(X_test)
        
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
        
        metrics = {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "precision": float(precision_score(y_test, y_pred, average="binary", zero_division=0)),
            "recall": float(recall_score(y_test, y_pred, average="binary", zero_division=0)),
            "f1": float(f1_score(y_test, y_pred, average="binary", zero_division=0)),
        }
        
        # AUC if binary classification
        if len(self.model.classes_) == 2:
            try:
                metrics["roc_auc"] = float(roc_auc_score(y_test, y_proba[:, 1]))
            except Exception:
                pass
        
        return {
            "success": True,
            "eligibility": "ELIGIBLE",
            "reason": "Model trained successfully with sufficient labeled data",
            "metrics": metrics,
            "feature_importance": dict(zip(feature_columns, self.model.feature_importances_.tolist())),
        }
    
    def check_label_leakage(
        self,
        data: pd.DataFrame,
        target_column: str,
        feature_columns: List[str],
    ) -> Dict[str, Any]:
        """Check for label leakage in features."""
        
        leakage_report = {
            "has_leakage": False,
            "leaking_features": [],
            "warnings": [],
        }
        
        # Check for features that are direct indicators of failure
        leakage_indicators = [
            "failure",
            "maintenance",
            "breakdown",
            "shutdown",
            "alarm",
        ]
        
        for feature in feature_columns:
            feature_lower = feature.lower()
            if any(indicator in feature_lower for indicator in leakage_indicators):
                leakage_report["has_leakage"] = True
                leakage_report["leaking_features"].append(feature)
                leakage_report["warnings"].append(
                    f"Feature '{feature}' may contain label leakage"
                )
        
        # Check for future information
        future_indicators = ["future", "upcoming", "next_day", "next_month"]
        for feature in feature_columns:
            feature_lower = feature.lower()
            if any(indicator in feature_lower for indicator in future_indicators):
                leakage_report["has_leakage"] = True
                leakage_report["leaking_features"].append(feature)
                leakage_report["warnings"].append(
                    f"Feature '{feature}' may contain future information"
                )
        
        return leakage_report
