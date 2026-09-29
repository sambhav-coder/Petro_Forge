"""Data validation for ML training.

Validates datasets before training to ensure data quality and ML eligibility.
Follows ML_DATA_POLICY.md requirements.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import MLEligibility, get_config
from .schemas import DatasetValidationReport


class DatasetValidator:
    """Validates datasets for ML training eligibility."""
    
    def __init__(self):
        self.config = get_config()
    
    def validate(
        self,
        data: pd.DataFrame,
        target_column: Optional[str] = None,
        required_columns: Optional[List[str]] = None,
        column_types: Optional[Dict[str, str]] = None,
        units: Optional[Dict[str, str]] = None,
        task: str = "general",
    ) -> DatasetValidationReport:
        """Perform comprehensive validation on a dataset."""
        
        if data.empty:
            return DatasetValidationReport(
                dataset_name="unknown",
                rows=0,
                features=0,
                target=target_column,
                missing_value_count=0,
                duplicate_count=0,
                entity_count=0,
                units=units or {},
                ml_eligible=MLEligibility.INSUFFICIENT_DATA,
                eligibility_reason="Dataset is empty",
                suitable_for=[],
            )
        
        rows, features = data.shape
        missing_count = data.isnull().sum().sum()
        duplicate_count = data.duplicated().sum()
        
        # Identify entity column (well_id)
        entity_count = 0
        if "well_id" in data.columns:
            entity_count = data["well_id"].nunique()
        
        # Time span information
        time_span_start = None
        time_span_end = None
        if "timestamp" in data.columns:
            try:
                data["timestamp"] = pd.to_datetime(data["timestamp"])
                time_span_start = data["timestamp"].min().isoformat()
                time_span_end = data["timestamp"].max().isoformat()
            except Exception:
                pass
        
        # Class balance for classification tasks
        class_balance = None
        if target_column and target_column in data.columns:
            class_balance = data[target_column].value_counts().to_dict()
        
        # Validation checks
        warnings = []
        
        # Check required columns
        if required_columns:
            missing_cols = set(required_columns) - set(data.columns)
            if missing_cols:
                warnings.append(f"Missing required columns: {missing_cols}")
        
        # Check column types
        if column_types:
            for col, expected_type in column_types.items():
                if col in data.columns:
                    actual_type = str(data[col].dtype)
                    if expected_type not in actual_type:
                        warnings.append(
                            f"Column {col} type mismatch: expected {expected_type}, got {actual_type}"
                        )
        
        # Check for impossible values
        warnings.extend(self._check_impossible_values(data, units))
        
        # Check for temporal ordering
        if "timestamp" in data.columns:
            warnings.extend(self._check_temporal_ordering(data))
        
        # Task-specific validation
        if task == "production_forecast":
            warnings.extend(self._validate_forecasting_requirements(data, target_column))
        elif task == "failure_risk":
            warnings.extend(self._validate_failure_requirements(data, target_column))
        
        # Determine eligibility
        ml_eligible, eligibility_reason, suitable_for = self._determine_eligibility(
            data, target_column, task, warnings
        )
        
        return DatasetValidationReport(
            dataset_name="validated_dataset",
            rows=rows,
            features=features,
            target=target_column,
            missing_value_count=missing_count,
            duplicate_count=duplicate_count,
            entity_count=entity_count,
            time_span_start=time_span_start,
            time_span_end=time_span_end,
            class_balance=class_balance,
            units=units or {},
            ml_eligible=ml_eligible,
            eligibility_reason=eligibility_reason,
            suitable_for=suitable_for,
            warnings=warnings,
        )
    
    def _check_impossible_values(self, data: pd.DataFrame, units: Dict[str, str]) -> List[str]:
        """Check for physically impossible values."""
        warnings = []
        
        # Non-negative checks
        non_negative_columns = {
            "oil_rate_bopd": "Oil production rate",
            "steam_volume_t": "Steam volume",
            "spm": "Strokes per minute",
            "stroke_in": "Stroke length",
            "reservoir_pressure_bar": "Reservoir pressure",
            "wellhead_pressure_bar": "Wellhead pressure",
            "reservoir_temperature_c": "Reservoir temperature",
        }
        
        for col, label in non_negative_columns.items():
            if col in data.columns:
                if (data[col] < 0).any():
                    count = (data[col] < 0).sum()
                    warnings.append(f"{label} ({col}) has {count} negative values")
        
        # Range checks
        if "spm" in data.columns:
            if (data["spm"] > 20).any():
                warnings.append("SPM exceeds maximum realistic value (20)")
        
        if "water_cut_fraction" in data.columns:
            if (data["water_cut_fraction"] > 1.0).any():
                warnings.append("Water cut fraction exceeds 1.0 (100%)")
        
        return warnings
    
    def _check_temporal_ordering(self, data: pd.DataFrame) -> List[str]:
        """Check for temporal ordering issues."""
        warnings = []
        
        if "timestamp" not in data.columns:
            return warnings
        
        try:
            data_sorted = data.sort_values("timestamp")
            if not data["timestamp"].equals(data_sorted["timestamp"]):
                warnings.append("Data is not chronologically ordered")
        except Exception:
            pass
        
        return warnings
    
    def _validate_forecasting_requirements(
        self, data: pd.DataFrame, target_column: Optional[str]
    ) -> List[str]:
        """Validate requirements for production forecasting."""
        warnings = []
        
        if not target_column or target_column not in data.columns:
            warnings.append("No target column specified for forecasting")
            return warnings
        
        if "timestamp" not in data.columns:
            warnings.append("No timestamp column for time-series forecasting")
        
        if len(data) < self.config.min_observations_for_training:
            warnings.append(
                f"Insufficient observations for forecasting: {len(data)} < {self.config.min_observations_for_training}"
            )
        
        return warnings
    
    def _validate_failure_requirements(
        self, data: pd.DataFrame, target_column: Optional[str]
    ) -> List[str]:
        """Validate requirements for failure prediction."""
        warnings = []
        
        if not target_column or target_column not in data.columns:
            warnings.append("No failure label column specified")
            return warnings
        
        class_counts = data[target_column].value_counts()
        
        # Check for positive class (failure)
        if "failure" not in class_counts.index and 1 not in class_counts.index:
            warnings.append("No failure cases found in dataset")
        else:
            failure_count = class_counts.get("failure", class_counts.get(1, 0))
            if failure_count < self.config.min_positive_failure_samples:
                warnings.append(
                    f"Insufficient failure samples: {failure_count} < {self.config.min_positive_failure_samples}"
                )
        
        # Check for negative class (normal)
        if "normal" not in class_counts.index and 0 not in class_counts.index:
            warnings.append("No normal cases found in dataset")
        else:
            normal_count = class_counts.get("normal", class_counts.get(0, 0))
            if normal_count < self.config.min_negative_failure_samples:
                warnings.append(
                    f"Insufficient normal samples: {normal_count} < {self.config.min_negative_failure_samples}"
                )
        
        return warnings
    
    def _determine_eligibility(
        self,
        data: pd.DataFrame,
        target_column: Optional[str],
        task: str,
        warnings: List[str],
    ) -> tuple:
        """Determine ML eligibility based on validation results."""
        
        # Critical failures that make data ineligible
        critical_warnings = [
            w for w in warnings
            if "empty" in w.lower() or "missing required" in w.lower()
        ]
        
        if critical_warnings:
            return (
                MLEligibility.INELIGIBLE,
                "; ".join(critical_warnings),
                [],
            )
        
        # Check for sufficient data
        if len(data) < self.config.min_observations_for_training:
            return (
                MLEligibility.INSUFFICIENT_DATA,
                f"Insufficient observations: {len(data)} < {self.config.min_observations_for_training}",
                [],
            )
        
        # Task-specific eligibility
        if task == "production_forecast":
            if "timestamp" not in data.columns or not target_column:
                return (
                    MLEligibility.INSUFFICIENT_DATA,
                    "Missing timestamp or target column for forecasting",
                    [],
                )
            return MLEligibility.ELIGIBLE, "Dataset meets forecasting requirements", ["production_forecast"]
        
        elif task == "failure_risk":
            if not target_column:
                return (
                    MLEligibility.INSUFFICIENT_DATA,
                    "Missing failure label column",
                    [],
                )
            return MLEligibility.ELIGIBLE, "Dataset meets failure prediction requirements", ["failure_risk"]
        
        # Default - eligible for general use
        return MLEligibility.ELIGIBLE, "Dataset meets general ML requirements", [task]
    
    def check_leakage(
        self,
        train_data: pd.DataFrame,
        test_data: pd.DataFrame,
        entity_column: str = "well_id",
    ) -> Dict[str, Any]:
        """Check for data leakage between train and test sets."""
        
        leakage_report = {
            "has_leakage": False,
            "entity_leakage": False,
            "temporal_leakage": False,
            "target_leakage": False,
            "overlapping_entities": [],
            "temporal_violations": [],
        }
        
        # Check entity leakage
        if entity_column in train_data.columns and entity_column in test_data.columns:
            train_entities = set(train_data[entity_column].dropna().unique())
            test_entities = set(test_data[entity_column].dropna().unique())
            overlap = train_entities & test_entities
            
            if overlap:
                leakage_report["has_leakage"] = True
                leakage_report["entity_leakage"] = True
                leakage_report["overlapping_entities"] = list(overlap)
        
        # Check temporal leakage
        if "timestamp" in train_data.columns and "timestamp" in test_data.columns:
            try:
                train_max = pd.to_datetime(train_data["timestamp"]).max()
                test_min = pd.to_datetime(test_data["timestamp"]).min()
                
                if test_min < train_max:
                    leakage_report["has_leakage"] = True
                    leakage_report["temporal_leakage"] = True
                    leakage_report["temporal_violations"].append(
                        f"Test data starts before training data ends: {test_min} < {train_max}"
                    )
            except Exception:
                pass
        
        return leakage_report
