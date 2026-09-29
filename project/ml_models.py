"""SIH26120 Digital Twin — predictive failure models (Block 4, AI layer).

=====================================================================
DOCUMENTATION — read before quoting any number from this module
=====================================================================
WHAT: two logistic-regression classifiers predicting the probability of
  (a) ROD FAILURE and (b) PUMP UNSETTING within the next 30 operating
  days, from physics-informed features (hybrid physics + ML).

TRAINING DATA (honest statement): no Baghewala failure history is public.
  The models are trained on TRAINING_SAMPLES operating states sampled
  across the documented engineering bands, pushed through the twin
  (twin_physics + srp_dynacard) to get features, with labels drawn from
  a documented SYNTHETIC HAZARD MODEL (_rod_hazard / _unset_hazard)
  encoding standard SRP failure drivers: rod stress (Goodman loading),
  fluid pound (low fillage), lost rod-fall margin (rod floating), pump/
  inflow mismatch, stroke rate. The labels are therefore synthetic. The
  deliverable is the pipeline — features -> training -> holdout metrics
  -> per-prediction explanation — which retrains unchanged on real
  failure logs (fit(X, y)) when Oil India data is available.

MODEL: standardized features, L2-regularised logistic regression fitted
  by full-batch gradient descent (deterministic, numpy only). 80/20
  split with fixed seed; holdout AUC, accuracy, Brier score reported,
  plus ORACLE AUC: the AUC of the true hazard probabilities on the same
  noisy labels, i.e. the ceiling any model could reach on this data.
  Training states sample the pump/inflow ratio log-normally around 1.1
  (realistic sizing with spread), so failure-prone states are the tails.

EXPLANATION: contribution_i = coef_i * standardized_feature_i (log-odds
  units). Top contributors are returned with every prediction.
=====================================================================
"""

import math
from types import SimpleNamespace
from typing import Dict, List, Optional

import numpy as np

import srp_dynacard as dc
import twin_physics as tp

SEED = 26120
TRAINING_SAMPLES = 3000
HOLDOUT_FRAC = 0.2
L2 = 1e-3
LR = 0.5
ITERATIONS = 1500
HORIZON_DAYS = 30
PROB_MODERATE = 0.15
PROB_HIGH = 0.35

FEATURES = [
    ("log_tubing_viscosity", "Tubing fluid viscosity (log cP)"),
    ("pump_fillage", "Estimated pump fillage"),
    ("spm", "Strokes per minute"),
    ("stroke_100in", "Stroke length (x100 in)"),
    ("goodman_loading", "Rod Goodman loading (fraction)"),
    ("rod_fall_margin", "Rod-fall margin (MPRL / buoyant rod weight)"),
    ("pump_inflow_mismatch", "Pump capacity vs inflow (log ratio)"),
    ("water_cut", "Water cut (fraction)"),
    ("wellhead_reservoir_ratio", "Wellhead / reservoir pressure"),
]


def feature_vector(snapshot: Dict, card: Dict) -> np.ndarray:
    inflow = max(snapshot["estimated_reservoir_inflow_bopd"], 1e-3)
    pump = max(snapshot["pump_capacity_bopd"], 1e-3)
    return np.array([
        math.log(max(card["tubing_viscosity_cp"], 0.1)),
        snapshot["estimated_pump_fillage"],
        snapshot["spm"],
        snapshot["stroke_in"] / 100.0,
        card["goodman_loading_percent"] / 100.0,
        card["mprl_lb"] / max(card["buoyant_rod_weight_lb"], 1.0),
        math.log(pump / inflow),
        snapshot["water_cut_percent"] / 100.0,
        snapshot["wellhead_pressure_bar"] / max(snapshot["reservoir_pressure_bar"], 1e-3),
    ], dtype=float)


# ---- Synthetic hazard model (ground truth for training labels; documented above) ----
def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def _rod_hazard(f: np.ndarray) -> float:
    goodman, fill, margin, spm = f[4], f[1], f[5], f[2]
    z = (-4.6 + 5.0 * max(goodman - 0.5, 0.0) + 3.0 * (1.0 - fill)
         + 3.0 * max(0.35 - margin, 0.0) / 0.35 + 0.15 * spm)
    return float(_sigmoid(z))


def _unset_hazard(f: np.ndarray) -> float:
    fill, mismatch, whp, spm = f[1], f[6], f[8], f[2]
    z = -5.6 + 3.2 * (1.0 - fill) + 1.2 * max(mismatch, 0.0) + 1.5 * whp + 0.12 * spm
    return float(_sigmoid(z))


def _sample_states(n: int, rng: np.random.RandomState) -> List[SimpleNamespace]:
    """Operating states resembling real practice: SRP sized near inflow, with spread.

    Pump-capacity/inflow ratio is log-normal around 1.1 (sigma 0.6), so badly
    over- or under-pumped wells exist but are the tails, not the norm.
    """
    states = []
    for _ in range(n):
        res_p = rng.uniform(15.0, 45.0)
        cold = rng.random_sample() < 0.2
        s = SimpleNamespace(
            well_id="TRAIN", timestamp="", css_phase="PRODUCTION",
            reservoir_temperature_c=rng.uniform(46.0, 48.0),
            reservoir_pressure_bar=res_p,
            wellhead_pressure_bar=max(res_p - rng.uniform(3.0, 22.0), 0.0),
            api_gravity=rng.uniform(17.0, 19.0),
            steam_volume_t=0.0 if cold else rng.uniform(300.0, 1200.0),
            steam_injection_pressure_bar=0.0 if cold else rng.uniform(40.0, 80.0),
            soak_time_h=rng.uniform(12.0, 120.0),
            days_in_phase=rng.uniform(0.0, 45.0),  # CSS wells are cut off within ~2-6 weeks
            spm=1.0,
            stroke_in=rng.uniform(54.0, 144.0),
            water_cut_percent=rng.uniform(10.0, 60.0),
        )
        inflow = tp.twin_snapshot(s)["estimated_reservoir_inflow_bopd"]
        per_spm = tp.actual_pump_capacity_bopd(tp.theoretical_pump_capacity_bopd(1.0, s.stroke_in))
        ratio = math.exp(rng.normal(math.log(1.1), 0.6))
        s.spm = float(np.clip(ratio * inflow / max(per_spm, 1e-6), 1.0, 12.0))
        states.append(s)
    return states


def features_for_state(state) -> Dict:
    snap = tp.twin_snapshot(state)
    card = dc.dynacard(snap, state.api_gravity)
    return {"snapshot": snap, "card": card, "x": feature_vector(snap, card)}


def _auc(y: np.ndarray, p: np.ndarray) -> Optional[float]:
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


class LogisticModel:
    def __init__(self, name: str, label: str):
        self.name, self.label = name, label
        self.mean = self.std = self.coef = None
        self.bias = 0.0
        self.metrics: Dict = {}

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LogisticModel":
        self.mean = X.mean(axis=0)
        self.std = X.std(axis=0) + 1e-9
        Z = (X - self.mean) / self.std
        w = np.zeros(Z.shape[1])
        b = 0.0
        n = len(y)
        for _ in range(ITERATIONS):
            p = _sigmoid(Z @ w + b)
            g = p - y
            w -= LR * (Z.T @ g / n + L2 * w)
            b -= LR * g.mean()
        self.coef, self.bias = w, b
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return _sigmoid(((X - self.mean) / self.std) @ self.coef + self.bias)

    def evaluate(self, X: np.ndarray, y: np.ndarray, oracle_p: Optional[np.ndarray] = None) -> Dict:
        """Holdout metrics. oracle_p (true hazard probabilities) gives the best AUC any
        model could reach on these noisy labels, so the model's AUC has a ceiling to compare to."""
        p = self.predict_proba(X)
        auc = _auc(y, p)
        oracle = _auc(y, oracle_p) if oracle_p is not None else None
        self.metrics = {
            "holdout_samples": int(len(y)),
            "holdout_positive_rate": round(float(y.mean()), 4),
            "auc": round(auc, 4) if auc is not None else None,
            "oracle_auc": round(oracle, 4) if oracle is not None else None,
            "accuracy_at_0_5": round(float(((p >= 0.5) == (y == 1)).mean()), 4),
            "brier_score": round(float(((p - y) ** 2).mean()), 4),
        }
        return self.metrics

    def explain(self, x: np.ndarray, top: int = 4) -> List[Dict]:
        contrib = self.coef * (x - self.mean) / self.std
        order = np.argsort(-np.abs(contrib))[:top]
        return [{
            "feature": FEATURES[i][0], "label": FEATURES[i][1],
            "value": round(float(x[i]), 4),
            "contribution_log_odds": round(float(contrib[i]), 4),
            "direction": "raises risk" if contrib[i] > 0 else "lowers risk",
        } for i in order]

    def card(self) -> Dict:
        return {
            "name": self.name, "label": self.label, "type": "logistic_regression (L2, numpy)",
            "horizon_days": HORIZON_DAYS,
            "coefficients": {FEATURES[i][0]: round(float(c), 4) for i, c in enumerate(self.coef)},
            "metrics": self.metrics,
        }


_MODELS: Dict[str, LogisticModel] = {}
_TRAINING_INFO: Dict = {}


def _train() -> None:
    rng = np.random.RandomState(SEED)
    states = _sample_states(TRAINING_SAMPLES, rng)
    X = np.array([features_for_state(s)["x"] for s in states])
    h_rod = np.array([_rod_hazard(x) for x in X])
    h_unset = np.array([_unset_hazard(x) for x in X])
    y_rod = (rng.random_sample(len(X)) < h_rod).astype(float)
    y_unset = (rng.random_sample(len(X)) < h_unset).astype(float)
    idx = rng.permutation(len(X))
    cut = int(len(X) * (1 - HOLDOUT_FRAC))
    tr, te = idx[:cut], idx[cut:]
    for name, label, y, h in (("rod_failure", "Rod failure", y_rod, h_rod),
                              ("pump_unsetting", "Pump unsetting", y_unset, h_unset)):
        m = LogisticModel(name, label).fit(X[tr], y[tr])
        m.evaluate(X[te], y[te], oracle_p=h[te])
        _MODELS[name] = m
    _TRAINING_INFO.update({
        "training_samples": int(len(tr)),
        "holdout_samples": int(len(te)),
        "seed": SEED,
        "label_source": "SYNTHETIC_HAZARD_MODEL",
        "data_statement": ("Labels come from a documented synthetic hazard model over the prototype "
                           "twin; no Baghewala failure logs are included. Retrain with fit(X, y) on "
                           "field failure history before operational use."),
    })


def models() -> Dict[str, LogisticModel]:
    if not _MODELS:
        _train()
    return _MODELS


def _band(p: float) -> str:
    if p >= PROB_HIGH:
        return "HIGH"
    if p >= PROB_MODERATE:
        return "MODERATE"
    return "LOW"


def predict(state) -> Dict:
    """Failure probabilities + explanations for one well state."""
    feats = features_for_state(state)
    x = feats["x"]
    out = {}
    for name, m in models().items():
        p = float(m.predict_proba(x[None, :])[0])
        out[name] = {
            "probability": round(p, 4),
            "risk_band": _band(p),
            "horizon_days": HORIZON_DAYS,
            "top_drivers": m.explain(x),
        }
    return {
        "well_id": state.well_id,
        "predictions": out,
        "features": {FEATURES[i][0]: round(float(v), 4) for i, v in enumerate(x)},
        "dynacard_diagnosis": feats["card"]["primary_diagnosis"],
        "model_info": model_info(),
    }


def model_info() -> Dict:
    ms = models()
    return {**_TRAINING_INFO, "models": [m.card() for m in ms.values()],
            "features": [{"name": n, "label": l} for n, l in FEATURES]}
