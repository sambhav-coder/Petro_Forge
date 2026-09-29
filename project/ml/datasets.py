"""Dataset inventory and eligibility assessment.

Discovers and evaluates datasets for ML training eligibility.
Follows ML_DATA_POLICY.md guidelines.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .config import MLEligibility, get_config
from .schemas import DatasetValidationReport


class DatasetSource(str, Enum):
    """Dataset source types."""
    PUBLIC_BAGHEWALA = "PUBLIC_BAGHEWALA"
    PUBLIC_REFERENCE = "PUBLIC_REFERENCE"
    SYNTHETIC_BAGHEWALA = "SYNTHETIC_BAGHEWALA"
    LIVE_TELEMETRY = "LIVE_TELEMETRY"
    DERIVED = "DERIVED"
    UNKNOWN = "UNKNOWN"


@dataclass
class DatasetInfo:
    """Information about a candidate dataset."""
    
    name: str
    source: DatasetSource
    domain: str
    target_variable: Optional[str]
    rows: int
    features: int
    time_information: bool
    well_entity_identifier: bool
    failure_labels: bool
    missingness: float
    duplicate_rate: float
    class_balance: Optional[Dict[str, int]]
    units: Dict[str, str]
    license: str = "unspecified"
    provenance: str = "unknown"
    file_path: Optional[str] = None


class DatasetInventory:
    """Manages dataset inventory and eligibility assessment."""
    
    def __init__(self, base_dir: str = "project/data"):
        self.base_dir = base_dir
        self.datasets: Dict[str, DatasetInfo] = {}
        self._load_catalog()
    
    def _load_catalog(self) -> None:
        """Load existing data catalog information."""
        catalog_path = os.path.join(self.base_dir, "..", "data_catalog", "data_catalog.json")
        if os.path.exists(catalog_path):
            try:
                with open(catalog_path, "r", encoding="utf-8") as f:
                    catalog = json.load(f)
                    for dataset in catalog.get("datasets", []):
                        self._register_from_catalog(dataset)
            except (json.JSONDecodeError, IOError):
                pass
    
    def _register_from_catalog(self, dataset: Dict[str, Any]) -> None:
        """Register a dataset from the data catalog."""
        name = dataset.get("name", "unknown")
        self.datasets[name] = DatasetInfo(
            name=name,
            source=DatasetSource(dataset.get("source", "UNKNOWN")),
            domain=dataset.get("domain", "unknown"),
            target_variable=dataset.get("target_variable"),
            rows=dataset.get("rows", 0),
            features=dataset.get("features", 0),
            time_information=dataset.get("time_information", False),
            well_entity_identifier=dataset.get("well_entity_identifier", False),
            failure_labels=dataset.get("failure_labels", False),
            missingness=dataset.get("missingness", 0.0),
            duplicate_rate=dataset.get("duplicate_rate", 0.0),
            class_balance=dataset.get("class_balance"),
            units=dataset.get("units", {}),
            license=dataset.get("license", "unspecified"),
            provenance=dataset.get("provenance", "unknown"),
            file_path=dataset.get("file_path"),
        )
    
    def add_dataset(self, info: DatasetInfo) -> None:
        """Add a dataset to the inventory."""
        self.datasets[info.name] = info
    
    def get_dataset(self, name: str) -> Optional[DatasetInfo]:
        """Get dataset information by name."""
        return self.datasets.get(name)
    
    def list_datasets(self) -> List[DatasetInfo]:
        """List all datasets in the inventory."""
        return list(self.datasets.values())
    
    def assess_eligibility(self, dataset_name: str, task: str) -> DatasetValidationReport:
        """Assess ML eligibility for a specific task."""
        dataset = self.get_dataset(dataset_name)
        if not dataset:
            return DatasetValidationReport(
                dataset_name=dataset_name,
                rows=0,
                features=0,
                missing_value_count=0,
                duplicate_count=0,
                entity_count=0,
                ml_eligible=MLEligibility.INELIGIBLE,
                eligibility_reason="Dataset not found in inventory",
                suitable_for=[],
            )
        
        config = get_config()
        
        # Determine eligibility based on task requirements
        if task == "production_forecast":
            return self._assess_forecasting_eligibility(dataset, config)
        elif task == "anomaly_detection":
            return self._assess_anomaly_eligibility(dataset, config)
        elif task == "srp_health":
            return self._assess_health_eligibility(dataset, config)
        elif task == "failure_risk":
            return self._assess_failure_eligibility(dataset, config)
        else:
            return DatasetValidationReport(
                dataset_name=dataset_name,
                rows=dataset.rows,
                features=dataset.features,
                target=dataset.target_variable,
                missing_value_count=int(dataset.rows * dataset.missingness),
                duplicate_count=int(dataset.rows * dataset.duplicate_rate),
                entity_count=dataset.rows if dataset.well_entity_identifier else 0,
                ml_eligible=MLEligibility.INELIGIBLE,
                eligibility_reason=f"Unknown task: {task}",
                suitable_for=[],
            )
    
    def _assess_forecasting_eligibility(
        self, dataset: DatasetInfo, config
    ) -> DatasetValidationReport:
        """Assess eligibility for production forecasting."""
        warnings = []
        suitable_for = []
        
        # Check time-series requirements
        if not dataset.time_information:
            warnings.append("No time information available")
        
        # Check minimum observations
        if dataset.rows < config.min_observations_for_training:
            warnings.append(
                f"Insufficient observations: {dataset.rows} < {config.min_observations_for_training}"
            )
        
        # Check for target variable
        if not dataset.target_variable:
            warnings.append("No target variable specified")
        
        # Determine eligibility
        if dataset.source == DatasetSource.PUBLIC_BAGHEWALA:
            # Baghewala public data is insufficient for forecasting
            return DatasetValidationReport(
                dataset_name=dataset.name,
                rows=dataset.rows,
                features=dataset.features,
                target=dataset.target_variable,
                missing_value_count=int(dataset.rows * dataset.missingness),
                duplicate_count=int(dataset.rows * dataset.duplicate_rate),
                entity_count=dataset.rows if dataset.well_entity_identifier else 0,
                units=dataset.units,
                ml_eligible=MLEligibility.INSUFFICIENT_DATA,
                eligibility_reason=(
                    "Baghewala public data contains sparse observations "
                    "with no continuous time-series. Insufficient for production forecasting."
                ),
                suitable_for=[],
                warnings=warnings,
            )
        
        if len(warnings) == 0 and dataset.rows >= config.min_observations_for_training:
            ml_eligible = MLEligibility.ELIGIBLE
            eligibility_reason = "Dataset meets forecasting requirements"
            suitable_for = ["production_forecast"]
        else:
            ml_eligible = MLEligibility.INSUFFICIENT_DATA
            eligibility_reason = "; ".join(warnings) if warnings else "Insufficient data quality"
        
        return DatasetValidationReport(
            dataset_name=dataset.name,
            rows=dataset.rows,
            features=dataset.features,
            target=dataset.target_variable,
            missing_value_count=int(dataset.rows * dataset.missingness),
            duplicate_count=int(dataset.rows * dataset.duplicate_rate),
            entity_count=dataset.rows if dataset.well_entity_identifier else 0,
            units=dataset.units,
            ml_eligible=ml_eligible,
            eligibility_reason=eligibility_reason,
            suitable_for=suitable_for,
            warnings=warnings,
        )
    
    def _assess_anomaly_eligibility(
        self, dataset: DatasetInfo, config
    ) -> DatasetValidationReport:
        """Assess eligibility for anomaly detection."""
        warnings = []
        suitable_for = []
        
        # Anomaly detection can work with less data than forecasting
        if dataset.rows < config.min_observations_for_trend:
            warnings.append(
                f"Insufficient observations: {dataset.rows} < {config.min_observations_for_trend}"
            )
        
        if len(warnings) == 0:
            ml_eligible = MLEligibility.ELIGIBLE
            eligibility_reason = "Dataset meets anomaly detection requirements"
            suitable_for = ["anomaly_detection"]
        else:
            ml_eligible = MLEligibility.INSUFFICIENT_DATA
            eligibility_reason = "; ".join(warnings) if warnings else "Insufficient data"
        
        return DatasetValidationReport(
            dataset_name=dataset.name,
            rows=dataset.rows,
            features=dataset.features,
            target=dataset.target_variable,
            missing_value_count=int(dataset.rows * dataset.missingness),
            duplicate_count=int(dataset.rows * dataset.duplicate_rate),
            entity_count=dataset.rows if dataset.well_entity_identifier else 0,
            units=dataset.units,
            ml_eligible=ml_eligible,
            eligibility_reason=eligibility_reason,
            suitable_for=suitable_for,
            warnings=warnings,
        )
    
    def _assess_health_eligibility(
        self, dataset: DatasetInfo, config
    ) -> DatasetValidationReport:
        """Assess eligibility for SRP health assessment."""
        warnings = []
        suitable_for = []
        
        # Need SRP-specific features
        srp_features = ["spm", "stroke", "rod_load", "pump_fillage"]
        has_srp_features = any(feat in dataset.units for feat in srp_features)
        
        if not has_srp_features:
            warnings.append("Missing SRP-specific features (SPM, stroke, rod load, pump fillage)")
        
        if dataset.rows < config.min_observations_for_training:
            warnings.append(
                f"Insufficient observations: {dataset.rows} < {config.min_observations_for_training}"
            )
        
        if len(warnings) == 0:
            ml_eligible = MLEligibility.ELIGIBLE
            eligibility_reason = "Dataset meets SRP health requirements"
            suitable_for = ["srp_health"]
        else:
            ml_eligible = MLEligibility.INSUFFICIENT_DATA
            eligibility_reason = "; ".join(warnings) if warnings else "Insufficient SRP data"
        
        return DatasetValidationReport(
            dataset_name=dataset.name,
            rows=dataset.rows,
            features=dataset.features,
            target=dataset.target_variable,
            missing_value_count=int(dataset.rows * dataset.missingness),
            duplicate_count=int(dataset.rows * dataset.duplicate_rate),
            entity_count=dataset.rows if dataset.well_entity_identifier else 0,
            units=dataset.units,
            ml_eligible=ml_eligible,
            eligibility_reason=eligibility_reason,
            suitable_for=suitable_for,
            warnings=warnings,
        )
    
    def _assess_failure_eligibility(
        self, dataset: DatasetInfo, config
    ) -> DatasetValidationReport:
        """Assess eligibility for failure prediction."""
        warnings = []
        suitable_for = []
        
        # Need failure labels
        if not dataset.failure_labels:
            warnings.append("No failure labels available")
        
        # Check class balance
        if dataset.class_balance:
            positive = dataset.class_balance.get("failure", 0)
            negative = dataset.class_balance.get("normal", 0)
            if positive < config.min_positive_failure_samples:
                warnings.append(
                    f"Insufficient failure samples: {positive} < {config.min_positive_failure_samples}"
                )
            if negative < config.min_negative_failure_samples:
                warnings.append(
                    f"Insufficient normal samples: {negative} < {config.min_negative_failure_samples}"
                )
        else:
            warnings.append("No class balance information available")
        
        if len(warnings) == 0:
            ml_eligible = MLEligibility.ELIGIBLE
            eligibility_reason = "Dataset meets failure prediction requirements"
            suitable_for = ["failure_risk"]
        else:
            ml_eligible = MLEligibility.INSUFFICIENT_DATA
            eligibility_reason = "; ".join(warnings) if warnings else "Insufficient labeled failure data"
        
        return DatasetValidationReport(
            dataset_name=dataset.name,
            rows=dataset.rows,
            features=dataset.features,
            target=dataset.target_variable,
            missing_value_count=int(dataset.rows * dataset.missingness),
            duplicate_count=int(dataset.rows * dataset.duplicate_rate),
            entity_count=dataset.rows if dataset.well_entity_identifier else 0,
            class_balance=dataset.class_balance,
            units=dataset.units,
            ml_eligible=ml_eligible,
            eligibility_reason=eligibility_reason,
            suitable_for=suitable_for,
            warnings=warnings,
        )


class DatasetEligibility:
    """Convenience class for eligibility checks."""
    
    def __init__(self):
        self.inventory = DatasetInventory()
    
    def is_eligible_for_forecasting(self, dataset_name: str) -> bool:
        """Check if dataset is eligible for production forecasting."""
        report = self.inventory.assess_eligibility(dataset_name, "production_forecast")
        return report.ml_eligible == MLEligibility.ELIGIBLE
    
    def is_eligible_for_anomaly_detection(self, dataset_name: str) -> bool:
        """Check if dataset is eligible for anomaly detection."""
        report = self.inventory.assess_eligibility(dataset_name, "anomaly_detection")
        return report.ml_eligible == MLEligibility.ELIGIBLE
    
    def is_eligible_for_health_assessment(self, dataset_name: str) -> bool:
        """Check if dataset is eligible for SRP health assessment."""
        report = self.inventory.assess_eligibility(dataset_name, "srp_health")
        return report.ml_eligible == MLEligibility.ELIGIBLE
    
    def is_eligible_for_failure_prediction(self, dataset_name: str) -> bool:
        """Check if dataset is eligible for failure prediction."""
        report = self.inventory.assess_eligibility(dataset_name, "failure_risk")
        return report.ml_eligible == MLEligibility.ELIGIBLE
