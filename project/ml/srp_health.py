"""SRP/pump health assessment model.

Implements health intelligence for sucker rod pumps.
Returns INSUFFICIENT_DATA when SRP operational data is unavailable.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import HealthStatus, get_config
from .registry import ModelRegistry
from .schemas import HealthResult


class SRPHealthModel:
    """SRP/pump health assessment model."""
    
    def __init__(self, registry: ModelRegistry):
        self.config = get_config()
        self.registry = registry
        self.model: Optional[Any] = None
    
    def assess(
        self,
        well_id: Optional[str],
        features: Dict[str, Any],
        model_id: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> HealthResult:
        """Assess SRP/pump health based on operational parameters.
        
        Returns explicit insufficient_data state when SRP data unavailable.
        """
        
        # Check for required SRP features
        required_features = ["spm", "stroke"]
        missing_features = [f for f in required_features if f not in features or features[f] is None]
        
        if missing_features:
            return HealthResult(
                well_id=well_id or "unknown",
                health_status=HealthStatus.INSUFFICIENT_DATA,
                health_score=0.0,
                contributing_factors=[],
                data_quality="INSUFFICIENT_DATA",
                model_id=model_id or "unavailable",
                model_version=model_version or "0.0",
                limitations=[
                    f"Missing required SRP features: {missing_features}",
                    "SRP operational data not available",
                ],
                insufficient_data=True,
                insufficient_reason="Missing SRP operational parameters",
            )
        
        # Extract SRP parameters
        spm = features.get("spm", 0.0)
        stroke = features.get("stroke", 0.0)
        rod_load = features.get("rod_load")
        pump_fillage = features.get("pump_fillage")
        
        # Simple rule-based health assessment
        # In production, this would use a trained ML model
        health_score, status, factors = self._rule_based_health_assessment(
            spm, stroke, rod_load, pump_fillage
        )
        
        return HealthResult(
            well_id=well_id or "unknown",
            health_status=status,
            health_score=health_score,
            contributing_factors=factors,
            spm_status=self._assess_spm(spm),
            stroke_status=self._assess_stroke(stroke),
            load_status=self._assess_load(rod_load),
            fillage_status=self._assess_fillage(pump_fillage),
            data_quality="VALID" if all(f is not None for f in [spm, stroke]) else "PARTIAL",
            model_id=model_id or "rule_based",
            model_version=model_version or "1.0",
            limitations=[
                "Rule-based assessment, not ML model",
                "Requires trained ML model with labeled SRP health data",
                "Baghewala public data lacks continuous SRP telemetry",
            ],
            insufficient_data=False,
            insufficient_reason=None,
        )
    
    def _rule_based_health_assessment(
        self,
        spm: float,
        stroke: float,
        rod_load: Optional[float],
        pump_fillage: Optional[float],
    ) -> tuple:
        """Simple rule-based health assessment.
        
        Returns: (health_score, status, contributing_factors)
        """
        
        factors = []
        score = 0.0
        num_factors = 0
        
        # SPM assessment
        if 3 <= spm <= 8:
            factors.append({
                "factor": "spm",
                "value": spm,
                "status": "normal",
                "contribution": -0.1,
            })
            score += 0.9
        elif spm > 12:
            factors.append({
                "factor": "spm",
                "value": spm,
                "status": "high",
                "contribution": 0.3,
            })
            score += 0.5
        else:
            factors.append({
                "factor": "spm",
                "value": spm,
                "status": "normal",
                "contribution": 0.0,
            })
            score += 0.8
        num_factors += 1
        
        # Stroke assessment
        if 72 <= stroke <= 120:
            factors.append({
                "factor": "stroke",
                "value": stroke,
                "status": "normal",
                "contribution": -0.1,
            })
            score += 0.9
        elif stroke > 200:
            factors.append({
                "factor": "stroke",
                "value": stroke,
                "status": "high",
                "contribution": 0.2,
            })
            score += 0.6
        else:
            factors.append({
                "factor": "stroke",
                "value": stroke,
                "status": "normal",
                "contribution": 0.0,
            })
            score += 0.8
        num_factors += 1
        
        # Rod load assessment (if available)
        if rod_load is not None:
            if rod_load > 10000:  # Example threshold
                factors.append({
                    "factor": "rod_load",
                    "value": rod_load,
                    "status": "high",
                    "contribution": 0.4,
                })
                score += 0.4
            else:
                factors.append({
                    "factor": "rod_load",
                    "value": rod_load,
                    "status": "normal",
                    "contribution": -0.1,
                })
                score += 0.9
            num_factors += 1
        
        # Pump fillage assessment (if available)
        if pump_fillage is not None:
            if pump_fillage < 0.5:
                factors.append({
                    "factor": "pump_fillage",
                    "value": pump_fillage,
                    "status": "low",
                    "contribution": 0.5,
                })
                score += 0.3
            elif pump_fillage > 0.9:
                factors.append({
                    "factor": "pump_fillage",
                    "value": pump_fillage,
                    "status": "normal",
                    "contribution": -0.1,
                })
                score += 0.9
            else:
                factors.append({
                    "factor": "pump_fillage",
                    "value": pump_fillage,
                    "status": "normal",
                    "contribution": 0.0,
                })
                score += 0.8
            num_factors += 1
        
        # Normalize score
        if num_factors > 0:
            health_score = score / num_factors
        else:
            health_score = 0.5
        
        # Determine status
        if health_score < self.config.health_degraded_threshold:
            status = HealthStatus.HEALTHY
        elif health_score < self.config.health_at_risk_threshold:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.AT_RISK
        
        return health_score, status, factors
    
    def _assess_spm(self, spm: float) -> str:
        """Assess SPM status."""
        if spm < 3:
            return "low"
        elif spm > 12:
            return "high"
        else:
            return "normal"
    
    def _assess_stroke(self, stroke: float) -> str:
        """Assess stroke status."""
        if stroke < 72:
            return "low"
        elif stroke > 200:
            return "high"
        else:
            return "normal"
    
    def _assess_load(self, rod_load: Optional[float]) -> Optional[str]:
        """Assess rod load status."""
        if rod_load is None:
            return None
        if rod_load > 10000:
            return "high"
        elif rod_load < 1000:
            return "low"
        else:
            return "normal"
    
    def _assess_fillage(self, pump_fillage: Optional[float]) -> Optional[str]:
        """Assess pump fillage status."""
        if pump_fillage is None:
            return None
        if pump_fillage < 0.5:
            return "low"
        elif pump_fillage > 0.95:
            return "high"
        else:
            return "normal"
    
    def train(
        self,
        data: pd.DataFrame,
        target_column: str = "health_status",
        feature_columns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Train SRP health model.
        
        Returns training report with eligibility determination.
        """
        
        # Check for SRP-specific features
        srp_features = ["spm", "stroke", "rod_load", "pump_fillage"]
        has_srp_features = any(feat in data.columns for feat in srp_features)
        
        if not has_srp_features:
            return {
                "success": False,
                "eligibility": "INSUFFICIENT_DATA",
                "reason": "Missing SRP-specific features (SPM, stroke, rod load, pump fillage)",
            }
        
        # Check for labeled health data
        if target_column not in data.columns:
            return {
                "success": False,
                "eligibility": "INSUFFICIENT_DATA",
                "reason": "Missing health status labels for training",
            }
        
        # Check data size
        if len(data) < self.config.min_observations_for_training:
            return {
                "success": False,
                "eligibility": "INSUFFICIENT_DATA",
                "reason": f"Insufficient observations: {len(data)} < {self.config.min_observations_for_training}",
            }
        
        # In a real implementation, this would train an ML model
        # For now, return insufficient data as per policy
        return {
            "success": False,
            "eligibility": "INSUFFICIENT_DATA",
            "reason": "Baghewala public data lacks labeled SRP health data for training",
        }
