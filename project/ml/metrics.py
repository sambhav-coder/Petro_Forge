"""Model evaluation metrics.

Implements appropriate metrics for different ML tasks.
"""

from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)


class ModelMetrics:
    """Computes and tracks model evaluation metrics."""
    
    def __init__(self):
        self.metrics_history: List[Dict[str, Any]] = []
    
    def regression_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        avoid_mape: bool = True,
    ) -> Dict[str, float]:
        """Compute regression metrics.
        
        Args:
            y_true: True values
            y_pred: Predicted values
            avoid_mape: If True, avoid MAPE when zeros/near-zeros present
        
        Returns:
            Dictionary of metric names and values
        """
        
        metrics = {}
        
        # Basic regression metrics
        metrics["mae"] = float(mean_absolute_error(y_true, y_pred))
        metrics["rmse"] = float(np.sqrt(mean_squared_error(y_true, y_pred)))
        
        # R² score (only meaningful if variance exists)
        if np.var(y_true) > 1e-10:
            metrics["r2"] = float(r2_score(y_true, y_pred))
        else:
            metrics["r2"] = 0.0
        
        # MAPE only if safe to compute
        if not avoid_mape:
            if np.all(y_true != 0):
                metrics["mape"] = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
                # SMAPE (symmetric MAPE)
                metrics["smape"] = float(
                    np.mean(2.0 * np.abs(y_true - y_pred) / (np.abs(y_true) + np.abs(y_pred))) * 100
                )
        
        return metrics
    
    def classification_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_proba: Optional[np.ndarray] = None,
        average: str = "binary",
    ) -> Dict[str, float]:
        """Compute classification metrics.
        
        Args:
            y_true: True labels
            y_pred: Predicted labels
            y_proba: Predicted probabilities (for AUC)
            average: Averaging method for multi-class
        
        Returns:
            Dictionary of metric names and values
        """
        
        metrics = {}
        
        # Basic classification metrics
        metrics["accuracy"] = float(accuracy_score(y_true, y_pred))
        metrics["precision"] = float(precision_score(y_true, y_pred, average=average, zero_division=0))
        metrics["recall"] = float(recall_score(y_true, y_pred, average=average, zero_division=0))
        metrics["f1"] = float(f1_score(y_true, y_pred, average=average, zero_division=0))
        
        # AUC if probabilities available
        if y_proba is not None:
            try:
                if len(y_proba.shape) == 1:
                    metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba))
                else:
                    metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba[:, 1], average=average))
            except Exception:
                # AUC may fail for single-class or other edge cases
                pass
        
        return metrics
    
    def baseline_comparison(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        baseline_pred: np.ndarray,
    ) -> Dict[str, float]:
        """Compare model performance against a baseline.
        
        Args:
            y_true: True values
            y_pred: Model predictions
            baseline_pred: Baseline predictions
        
        Returns:
            Dictionary of improvement metrics
        """
        
        model_mae = mean_absolute_error(y_true, y_pred)
        baseline_mae = mean_absolute_error(y_true, baseline_pred)
        
        improvement = {
            "model_mae": float(model_mae),
            "baseline_mae": float(baseline_mae),
            "mae_improvement": float(baseline_mae - model_mae),
            "mae_improvement_pct": float((baseline_mae - model_mae) / baseline_mae * 100) if baseline_mae > 0 else 0.0,
        }
        
        # R² comparison
        if np.var(y_true) > 1e-10:
            model_r2 = r2_score(y_true, y_pred)
            baseline_r2 = r2_score(y_true, baseline_pred)
            improvement["model_r2"] = float(model_r2)
            improvement["baseline_r2"] = float(baseline_r2)
            improvement["r2_improvement"] = float(model_r2 - baseline_r2)
        
        return improvement
    
    def naive_baseline(self, y_train: np.ndarray, y_test_len: int) -> np.ndarray:
        """Create naive baseline predictions (last value repeated).
        
        Args:
            y_train: Training data
            y_test_len: Length of test set
        
        Returns:
            Baseline predictions
        """
        
        last_value = y_train[-1]
        return np.full(y_test_len, last_value)
    
    def moving_average_baseline(
        self,
        y_train: np.ndarray,
        y_test_len: int,
        window: int = 7,
    ) -> np.ndarray:
        """Create moving average baseline predictions.
        
        Args:
            y_train: Training data
            y_test_len: Length of test set
            window: Window size for moving average
        
        Returns:
            Baseline predictions
        """
        
        if len(y_train) < window:
            return np.full(y_test_len, np.mean(y_train))
        
        ma_value = np.mean(y_train[-window:])
        return np.full(y_test_len, ma_value)
    
    def record_metrics(
        self,
        metrics: Dict[str, float],
        model_id: str,
        dataset_id: str,
        split: str = "test",
    ) -> None:
        """Record metrics for tracking."""
        
        record = {
            "model_id": model_id,
            "dataset_id": dataset_id,
            "split": split,
            "metrics": metrics,
            "timestamp": str(np.datetime64("now")),
        }
        
        self.metrics_history.append(record)
    
    def get_metrics_history(
        self,
        model_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get metrics history with optional filtering."""
        
        filtered = self.metrics_history
        
        if model_id:
            filtered = [r for r in filtered if r["model_id"] == model_id]
        
        if dataset_id:
            filtered = [r for r in filtered if r["dataset_id"] == dataset_id]
        
        return filtered
    
    def clear_history(self) -> None:
        """Clear metrics history."""
        self.metrics_history = []
