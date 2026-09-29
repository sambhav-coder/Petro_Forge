"""Data splitting for ML training.

Implements leakage prevention strategies: chronological and entity-aware splits.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import get_config


class DataSplitter:
    """Splits data for ML training with leakage prevention."""
    
    def __init__(self):
        self.config = get_config()
    
    def chronological_split(
        self,
        data: pd.DataFrame,
        timestamp_column: str = "timestamp",
        train_ratio: float = 0.7,
        validation_ratio: float = 0.15,
        test_ratio: float = 0.15,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Split data chronologically to prevent temporal leakage.
        
        Returns: (train, validation, test)
        """
        
        # Validate ratios
        if not np.isclose(train_ratio + validation_ratio + test_ratio, 1.0):
            raise ValueError("Split ratios must sum to 1.0")
        
        # Sort by timestamp
        sorted_data = data.sort_values(timestamp_column).copy()
        
        # Calculate split indices
        n = len(sorted_data)
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * validation_ratio)
        
        train = sorted_data.iloc[:train_end].copy()
        validation = sorted_data.iloc[train_end:val_end].copy()
        test = sorted_data.iloc[val_end:].copy()
        
        return train, validation, test
    
    def entity_aware_split(
        self,
        data: pd.DataFrame,
        entity_column: str = "well_id",
        train_ratio: float = 0.7,
        validation_ratio: float = 0.15,
        test_ratio: float = 0.15,
        random_seed: Optional[int] = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Split data by entities to prevent entity leakage.
        
        Entities are assigned to train/validation/test sets,
        then all data for each entity goes to its assigned set.
        
        Returns: (train, validation, test)
        """
        
        if random_seed is None:
            random_seed = self.config.random_seed
        
        # Validate ratios
        if not np.isclose(train_ratio + validation_ratio + test_ratio, 1.0):
            raise ValueError("Split ratios must sum to 1.0")
        
        # Get unique entities
        entities = data[entity_column].unique()
        entities = list(entities)  # Convert to list to avoid StringArray warning
        np.random.seed(random_seed)
        np.random.shuffle(entities)
        
        # Assign entities to splits
        n_entities = len(entities)
        train_end = int(n_entities * train_ratio)
        val_end = train_end + int(n_entities * validation_ratio)
        
        train_entities = entities[:train_end]
        val_entities = entities[train_end:val_end]
        test_entities = entities[val_end:]
        
        # Split data by entity assignment
        train = data[data[entity_column].isin(train_entities)].copy()
        validation = data[data[entity_column].isin(val_entities)].copy()
        test = data[data[entity_column].isin(test_entities)].copy()
        
        return train, validation, test
    
    def combined_split(
        self,
        data: pd.DataFrame,
        entity_column: str = "well_id",
        timestamp_column: str = "timestamp",
        train_ratio: float = 0.7,
        validation_ratio: float = 0.15,
        test_ratio: float = 0.15,
        random_seed: Optional[int] = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Combined entity-aware and chronological split.
        
        First splits entities, then applies chronological split within each entity's data.
        
        Returns: (train, validation, test)
        """
        
        if random_seed is None:
            random_seed = self.config.random_seed
        
        # Validate ratios
        if not np.isclose(train_ratio + validation_ratio + test_ratio, 1.0):
            raise ValueError("Split ratios must sum to 1.0")
        
        # Get unique entities
        entities = data[entity_column].unique()
        entities = list(entities)  # Convert to list to avoid StringArray warning
        np.random.seed(random_seed)
        np.random.shuffle(entities)
        
        # Assign entities to splits
        n_entities = len(entities)
        train_end = int(n_entities * train_ratio)
        val_end = train_end + int(n_entities * validation_ratio)
        
        train_entities = entities[:train_end]
        val_entities = entities[train_end:val_end]
        test_entities = entities[val_end:]
        
        # Split data by entity assignment
        train_data = data[data[entity_column].isin(train_entities)].copy()
        val_data = data[data[entity_column].isin(val_entities)].copy()
        test_data = data[data[entity_column].isin(test_entities)].copy()
        
        # Apply chronological split within each entity's data
        train = self._chronological_split_single(train_data, timestamp_column, 1.0, 0.0, 0.0)
        validation = self._chronological_split_single(val_data, timestamp_column, 0.0, 1.0, 0.0)
        test = self._chronological_split_single(test_data, timestamp_column, 0.0, 0.0, 1.0)
        
        return train, validation, test
    
    def _chronological_split_single(
        self,
        data: pd.DataFrame,
        timestamp_column: str,
        train_ratio: float,
        validation_ratio: float,
        test_ratio: float,
    ) -> pd.DataFrame:
        """Helper for chronological split of a single dataset."""
        
        sorted_data = data.sort_values(timestamp_column).copy()
        n = len(sorted_data)
        
        if train_ratio > 0:
            end_idx = int(n * train_ratio)
            return sorted_data.iloc[:end_idx].copy()
        elif validation_ratio > 0:
            start_idx = int(n * train_ratio)
            end_idx = start_idx + int(n * validation_ratio)
            return sorted_data.iloc[start_idx:end_idx].copy()
        else:  # test_ratio > 0
            start_idx = int(n * (train_ratio + validation_ratio))
            return sorted_data.iloc[start_idx:].copy()
    
    def random_split(
        self,
        data: pd.DataFrame,
        train_ratio: float = 0.7,
        validation_ratio: float = 0.15,
        test_ratio: float = 0.15,
        random_seed: Optional[int] = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Random split (USE WITH CAUTION - not recommended for time-series).
        
        Returns: (train, validation, test)
        """
        
        if random_seed is None:
            random_seed = self.config.random_seed
        
        # Validate ratios
        if not np.isclose(train_ratio + validation_ratio + test_ratio, 1.0):
            raise ValueError("Split ratios must sum to 1.0")
        
        # Shuffle data
        shuffled = data.sample(frac=1, random_state=random_seed).copy()
        
        # Calculate split indices
        n = len(shuffled)
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * validation_ratio)
        
        train = shuffled.iloc[:train_end].copy()
        validation = shuffled.iloc[train_end:val_end].copy()
        test = shuffled.iloc[val_end:].copy()
        
        return train, validation, test
    
    def get_split_info(
        self,
        train: pd.DataFrame,
        validation: pd.DataFrame,
        test: pd.DataFrame,
        entity_column: str = "well_id",
        timestamp_column: str = "timestamp",
    ) -> Dict[str, Any]:
        """Get information about the data split."""
        
        info = {
            "train_size": len(train),
            "validation_size": len(validation),
            "test_size": len(test),
            "total_size": len(train) + len(validation) + len(test),
        }
        
        # Entity overlap check
        if entity_column in train.columns:
            train_entities = set(train[entity_column].dropna().unique())
            val_entities = set(validation[entity_column].dropna().unique())
            test_entities = set(test[entity_column].dropna().unique())
            
            info["train_entities"] = len(train_entities)
            info["validation_entities"] = len(val_entities)
            info["test_entities"] = len(test_entities)
            info["entity_overlap_train_val"] = len(train_entities & val_entities)
            info["entity_overlap_train_test"] = len(train_entities & test_entities)
            info["entity_overlap_val_test"] = len(val_entities & test_entities)
        
        # Temporal overlap check
        if timestamp_column in train.columns:
            try:
                train_max = pd.to_datetime(train[timestamp_column]).max()
                val_min = pd.to_datetime(validation[timestamp_column]).min()
                test_min = pd.to_datetime(test[timestamp_column]).min()
                
                info["train_max_time"] = train_max.isoformat()
                info["validation_min_time"] = val_min.isoformat()
                info["test_min_time"] = test_min.isoformat()
                info["temporal_leakage_train_val"] = val_min < train_max
                info["temporal_leakage_train_test"] = test_min < train_max
            except Exception:
                pass
        
        return info
