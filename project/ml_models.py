"""Legacy compatibility shim (deprecated).

The canonical runtime implementation lives in :mod:`ml.synthetic_hazard`.
This module re-exports the canonical names so existing imports keep working,
but all runtime paths (ingest, alerts, SSE, /predict) use the canonical
package directly. New code must import from ``ml`` instead.

Every prediction carries ``mode="SYNTHETIC"``: demonstration output trained
on synthetic hazard labels, never field-validated Baghewala intelligence.
"""

from ml.synthetic_hazard import (  # noqa: F401
    FEATURES,
    HORIZON_DAYS,
    HOLDOUT_FRAC,
    ITERATIONS,
    L2,
    LR,
    MODE,
    PROB_HIGH,
    PROB_MODERATE,
    PRODUCTION_SAFE,
    PROVENANCE,
    SEED,
    TRAINING_DATA,
    TRAINING_SAMPLES,
    LogisticModel,
    feature_vector,
    features_for_state,
    model_info,
    models,
    predict,
)

__all__ = [
    "FEATURES", "HORIZON_DAYS", "HOLDOUT_FRAC", "ITERATIONS", "L2", "LR",
    "MODE", "PROB_HIGH", "PROB_MODERATE", "PRODUCTION_SAFE", "PROVENANCE",
    "SEED", "TRAINING_DATA", "TRAINING_SAMPLES", "LogisticModel",
    "feature_vector", "features_for_state", "model_info", "models", "predict",
]
