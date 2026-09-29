"""Feature engineering for ML.

Creates features from raw data while preventing leakage.
Physics-aware features using twin_physics where appropriate.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import get_config


class FeatureEngineer:
    """Engineers features for ML training and inference."""
    
    def __init__(self):
        self.config = get_config()
        self.feature_registry: Dict[str, Dict[str, Any]] = {}
    
    def add_lag_features(
        self,
        data: pd.DataFrame,
        value_column: str,
        lags: Optional[List[int]] = None,
        entity_column: str = "well_id",
    ) -> pd.DataFrame:
        """Add lag features for time-series data.
        
        LEAKAGE-SAFE: Uses shift() which only uses past values.
        Lag N feature at row T uses value from row T-N (strictly in the past).
        Current observation (row T) is never included in lag features.
        Entity grouping prevents cross-entity leakage.
        """
        
        if lags is None:
            lags = list(range(1, self.config.max_lag_periods + 1))
        
        featured = data.copy()
        
        # Sort by entity and timestamp if available
        # Chronological ordering is REQUIRED for temporal safety
        if entity_column in featured.columns:
            if "timestamp" in featured.columns:
                featured = featured.sort_values([entity_column, "timestamp"])
            else:
                featured = featured.sort_values(entity_column)
        
        for lag in lags:
            lag_col = f"{value_column}_lag_{lag}"
            # shift(lag) moves values down by lag rows
            # Row T gets value from row T-lag (strictly in the past)
            featured[lag_col] = featured.groupby(entity_column)[value_column].shift(lag)
            
            self.feature_registry[lag_col] = {
                "type": "lag",
                "source_column": value_column,
                "lag": lag,
                "description": f"{value_column} lagged by {lag} periods (strictly past values only)",
                "leakage_risk": "none",
                "temporal_safety": "shift(lag) uses only T-lag, never current or future",
            }
        
        return featured
    
    def add_rolling_features(
        self,
        data: pd.DataFrame,
        value_column: str,
        windows: Optional[List[int]] = None,
        functions: Optional[List[str]] = None,
        entity_column: str = "well_id",
    ) -> pd.DataFrame:
        """Add rolling window features.
        
        LEAKAGE-SAFE: Uses rolling() with min_periods=1 which includes current observation.
        Current observation IS included in rolling statistics by design.
        Entity grouping prevents cross-entity leakage.
        Chronological sorting required for temporal safety.
        """
        
        if windows is None:
            windows = [self.config.default_rolling_window]
        
        if functions is None:
            functions = ["mean", "std", "min", "max"]
        
        featured = data.copy()
        
        # Sort by entity and timestamp if available
        # Chronological ordering is REQUIRED for temporal safety
        if entity_column in featured.columns:
            if "timestamp" in featured.columns:
                featured = featured.sort_values([entity_column, "timestamp"])
            else:
                featured = featured.sort_values(entity_column)
        
        for window in windows:
            for func in functions:
                feature_name = f"{value_column}_rolling_{func}_{window}"
                
                if func == "mean":
                    featured[feature_name] = (
                        featured.groupby(entity_column)[value_column]
                        .transform(lambda x: x.rolling(window, min_periods=1).mean())
                    )
                elif func == "std":
                    featured[feature_name] = (
                        featured.groupby(entity_column)[value_column]
                        .transform(lambda x: x.rolling(window, min_periods=1).std())
                    )
                elif func == "min":
                    featured[feature_name] = (
                        featured.groupby(entity_column)[value_column]
                        .transform(lambda x: x.rolling(window, min_periods=1).min())
                    )
                elif func == "max":
                    featured[feature_name] = (
                        featured.groupby(entity_column)[value_column]
                        .transform(lambda x: x.rolling(window, min_periods=1).max())
                    )
                
                self.feature_registry[feature_name] = {
                    "type": "rolling",
                    "source_column": value_column,
                    "window": window,
                    "function": func,
                    "description": f"{func} of {value_column} over {window} periods (includes current obs)",
                    "leakage_risk": "none",
                    "temporal_safety": "rolling includes current observation, never future",
                }
        
        return featured
    
    def add_delta_features(
        self,
        data: pd.DataFrame,
        value_column: str,
        periods: Optional[List[int]] = None,
        entity_column: str = "well_id",
    ) -> pd.DataFrame:
        """Add delta (change) features.
        
        LEAKAGE-SAFE: Uses diff() and pct_change() which only use past values.
        Delta for period N at row T compares row T to row T-N (past only).
        Entity grouping prevents cross-entity leakage.
        Chronological sorting required for temporal safety.
        """
        
        if periods is None:
            periods = [1]
        
        featured = data.copy()
        
        # Sort by entity and timestamp if available
        # Chronological ordering is REQUIRED for temporal safety
        if entity_column in featured.columns:
            if "timestamp" in featured.columns:
                featured = featured.sort_values([entity_column, "timestamp"])
            else:
                featured = featured.sort_values(entity_column)
        
        for period in periods:
            delta_col = f"{value_column}_delta_{period}"
            pct_change_col = f"{value_column}_pct_change_{period}"
            
            # diff(periods) computes T - T-period (past only)
            featured[delta_col] = featured.groupby(entity_column)[value_column].diff(periods=period)
            # pct_change computes (T - T-period) / T-period (past only)
            featured[pct_change_col] = featured.groupby(entity_column)[value_column].pct_change(periods=period)
            
            self.feature_registry[delta_col] = {
                "type": "delta",
                "source_column": value_column,
                "period": period,
                "description": f"Change in {value_column} over {period} periods (T - T-period, past only)",
                "leakage_risk": "none",
                "temporal_safety": "diff(periods) uses only T-period, never future",
            }
            
            self.feature_registry[pct_change_col] = {
                "type": "pct_change",
                "source_column": value_column,
                "period": period,
                "description": f"Percentage change in {value_column} over {period} periods (past only)",
                "leakage_risk": "none",
                "temporal_safety": "pct_change uses only T-period, never future",
            }
        
        return featured
    
    def add_physics_features(
        self,
        data: pd.DataFrame,
        use_twin_physics: bool = True,
    ) -> pd.DataFrame:
        """Add physics-aware features using twin_physics relationships."""
        
        if not use_twin_physics:
            return data
        
        featured = data.copy()
        
        try:
            # Import twin_physics for physics-based features
            import twin_physics as tp
            
            # Temperature-viscosity relationship
            if "reservoir_temperature_c" in featured.columns and "api_gravity" in featured.columns:
                featured["estimated_viscosity_cp"] = featured.apply(
                    lambda row: tp.viscosity_cp(row["reservoir_temperature_c"], row["api_gravity"]),
                    axis=1,
                )
                
                self.feature_registry["estimated_viscosity_cp"] = {
                    "type": "physics_derived",
                    "source_columns": ["reservoir_temperature_c", "api_gravity"],
                    "method": "twin_physics.viscosity_cp",
                    "description": "Estimated viscosity from temperature and API gravity",
                    "leakage_risk": "none",
                    "provenance": "DERIVED_PROTOTYPE",
                }
            
            # Mobility factor
            if "estimated_viscosity_cp" in featured.columns:
                featured["mobility_factor"] = featured["estimated_viscosity_cp"].apply(
                    tp.mobility_factor
                )
                
                self.feature_registry["mobility_factor"] = {
                    "type": "physics_derived",
                    "source_columns": ["estimated_viscosity_cp"],
                    "method": "twin_physics.mobility_factor",
                    "description": "Mobility factor from viscosity",
                    "leakage_risk": "none",
                    "provenance": "DERIVED_PROTOTYPE",
                }
            
            # Heating intensity
            if "steam_volume_t" in featured.columns and "steam_injection_pressure_bar" in featured.columns:
                featured["heating_intensity"] = featured.apply(
                    lambda row: tp.heating_intensity(row["steam_volume_t"], row["steam_injection_pressure_bar"]),
                    axis=1,
                )
                
                self.feature_registry["heating_intensity"] = {
                    "type": "physics_derived",
                    "source_columns": ["steam_volume_t", "steam_injection_pressure_bar"],
                    "method": "twin_physics.heating_intensity",
                    "description": "Heating intensity from steam volume and pressure",
                    "leakage_risk": "none",
                    "provenance": "DERIVED_PROTOTYPE",
                }
            
            # Pump capacity
            if "spm" in featured.columns and "stroke_in" in featured.columns:
                featured["theoretical_pump_capacity_bopd"] = featured.apply(
                    lambda row: tp.theoretical_pump_capacity_bopd(row["spm"], row["stroke_in"]),
                    axis=1,
                )
                
                self.feature_registry["theoretical_pump_capacity_bopd"] = {
                    "type": "physics_derived",
                    "source_columns": ["spm", "stroke_in"],
                    "method": "twin_physics.theoretical_pump_capacity_bopd",
                    "description": "Theoretical pump capacity from SPM and stroke",
                    "leakage_risk": "none",
                    "provenance": "DERIVED_PROTOTYPE",
                }
        
        except ImportError:
            # twin_physics not available, skip physics features
            pass
        
        return featured
    
    def add_interaction_features(
        self,
        data: pd.DataFrame,
        feature_pairs: Optional[List[tuple]] = None,
    ) -> pd.DataFrame:
        """Add interaction features between variables."""
        
        featured = data.copy()
        
        if feature_pairs is None:
            # Default to common operational interactions
            feature_pairs = [
                ("spm", "stroke_in"),
                ("reservoir_temperature_c", "reservoir_pressure_bar"),
                ("steam_volume_t", "soak_time_h"),
            ]
        
        for feat1, feat2 in feature_pairs:
            if feat1 in featured.columns and feat2 in featured.columns:
                interaction_col = f"{feat1}_x_{feat2}"
                featured[interaction_col] = featured[feat1] * featured[feat2]
                
                self.feature_registry[interaction_col] = {
                    "type": "interaction",
                    "source_columns": [feat1, feat2],
                    "method": "multiplication",
                    "description": f"Interaction between {feat1} and {feat2}",
                    "leakage_risk": "none",
                }
        
        return featured
    
    def get_feature_info(self, feature_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a feature."""
        return self.feature_registry.get(feature_name)
    
    def get_all_features(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered features."""
        return self.feature_registry
    
    def reset(self) -> None:
        """Reset feature registry."""
        self.feature_registry = {}
