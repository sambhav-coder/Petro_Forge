"""Data preprocessing for ML training.

Handles data cleaning, transformation, and preparation for ML.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import get_config


class DataPreprocessor:
    """Preprocesses data for ML training."""
    
    def __init__(self):
        self.config = get_config()
        self.fitted_scalers: Dict[str, Any] = {}
        self.fitted_imputers: Dict[str, Any] = {}
    
    def clean(
        self,
        data: pd.DataFrame,
        remove_duplicates: bool = True,
        handle_missing: str = "keep",  # keep, drop, impute
        impute_strategy: str = "median",  # mean, median, mode, constant
    ) -> pd.DataFrame:
        """Clean the dataset."""
        
        cleaned = data.copy()
        
        # Remove duplicates
        if remove_duplicates:
            initial_len = len(cleaned)
            cleaned = cleaned.drop_duplicates()
            removed = initial_len - len(cleaned)
        
        # Handle missing values
        if handle_missing == "drop":
            cleaned = cleaned.dropna()
        elif handle_missing == "impute":
            cleaned = self._impute_missing(cleaned, impute_strategy)
        # keep: do nothing
        
        return cleaned
    
    def _impute_missing(self, data: pd.DataFrame, strategy: str) -> pd.DataFrame:
        """Impute missing values based on strategy."""
        
        imputed = data.copy()
        
        for col in imputed.columns:
            if imputed[col].isnull().any():
                if imputed[col].dtype in [np.float64, np.int64]:
                    if strategy == "mean":
                        value = imputed[col].mean()
                    elif strategy == "median":
                        value = imputed[col].median()
                    elif strategy == "constant":
                        value = 0
                    else:
                        value = imputed[col].median()
                    
                    imputed[col] = imputed[col].fillna(value)
                    self.fitted_imputers[col] = {"strategy": strategy, "value": value}
                else:
                    # For categorical, use mode
                    value = imputed[col].mode()[0] if not imputed[col].mode().empty else "unknown"
                    imputed[col] = imputed[col].fillna(value)
                    self.fitted_imputers[col] = {"strategy": "mode", "value": value}
        
        return imputed
    
    def scale_features(
        self,
        data: pd.DataFrame,
        numeric_columns: Optional[List[str]] = None,
        method: str = "standard",  # standard, minmax, robust
    ) -> pd.DataFrame:
        """Scale numeric features."""
        
        scaled = data.copy()
        
        if numeric_columns is None:
            numeric_columns = scaled.select_dtypes(include=[np.number]).columns.tolist()
        
        for col in numeric_columns:
            if col in scaled.columns:
                if method == "standard":
                    mean = scaled[col].mean()
                    std = scaled[col].std()
                    if std > 0:
                        scaled[col] = (scaled[col] - mean) / std
                        self.fitted_scalers[col] = {"method": "standard", "mean": mean, "std": std}
                elif method == "minmax":
                    min_val = scaled[col].min()
                    max_val = scaled[col].max()
                    if max_val > min_val:
                        scaled[col] = (scaled[col] - min_val) / (max_val - min_val)
                        self.fitted_scalers[col] = {
                            "method": "minmax",
                            "min": min_val,
                            "max": max_val,
                        }
                elif method == "robust":
                    median = scaled[col].median()
                    q1 = scaled[col].quantile(0.25)
                    q3 = scaled[col].quantile(0.75)
                    iqr = q3 - q1
                    if iqr > 0:
                        scaled[col] = (scaled[col] - median) / iqr
                        self.fitted_scalers[col] = {
                            "method": "robust",
                            "median": median,
                            "q1": q1,
                            "q3": q3,
                            "iqr": iqr,
                        }
        
        return scaled
    
    def encode_categorical(
        self,
        data: pd.DataFrame,
        categorical_columns: Optional[List[str]] = None,
        method: str = "onehot",  # onehot, label
    ) -> pd.DataFrame:
        """Encode categorical features."""
        
        encoded = data.copy()
        
        if categorical_columns is None:
            categorical_columns = encoded.select_dtypes(include=["object", "category"]).columns.tolist()
        
        for col in categorical_columns:
            if col in encoded.columns:
                if method == "onehot":
                    dummies = pd.get_dummies(encoded[col], prefix=col, drop_first=False)
                    encoded = pd.concat([encoded, dummies], axis=1)
                    encoded = encoded.drop(col, axis=1)
                elif method == "label":
                    encoded[col] = encoded[col].astype("category").cat.codes
        
        return encoded
    
    def transform_new_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform new data using fitted scalers and imputers."""
        
        transformed = data.copy()
        
        # Apply imputers
        for col, imputer in self.fitted_imputers.items():
            if col in transformed.columns:
                if transformed[col].isnull().any():
                    transformed[col].fillna(imputer["value"], inplace=True)
        
        # Apply scalers
        for col, scaler in self.fitted_scalers.items():
            if col in transformed.columns:
                if scaler["method"] == "standard":
                    transformed[col] = (transformed[col] - scaler["mean"]) / scaler["std"]
                elif scaler["method"] == "minmax":
                    transformed[col] = (transformed[col] - scaler["min"]) / (
                        scaler["max"] - scaler["min"]
                    )
                elif scaler["method"] == "robust":
                    transformed[col] = (transformed[col] - scaler["median"]) / scaler["iqr"]
        
        return transformed
    
    def get_fitted_params(self) -> Dict[str, Any]:
        """Get fitted preprocessing parameters."""
        return {
            "scalers": self.fitted_scalers,
            "imputers": self.fitted_imputers,
        }
    
    def reset(self) -> None:
        """Reset fitted parameters."""
        self.fitted_scalers = {}
        self.fitted_imputers = {}
