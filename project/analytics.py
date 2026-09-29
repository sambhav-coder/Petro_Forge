"""SIH26120 Digital Twin — predictive analytics over well history (Block 4).

=====================================================================
DOCUMENTATION
=====================================================================
Operates on the per-well history recorded at every telemetry ingest
(measured values + the twin's prediction at that moment).

1. TWIN AUTO-CALIBRATION (hybrid physics x data)
   The prototype physics is uncalibrated. With >= CALIB_MIN_POINTS
   PRODUCTION-phase readings, a least-squares scale factor
       k = sum(measured * predicted) / sum(predicted^2)
   maps twin oil rate onto measured oil rate (clamped to [0.05, 5]).
   One robust refit drops readings diverging > DIVERGENCE_FRAC from the
   first fit, so fault periods do not bias the calibration.
   Reported with R^2 and MAPE so the fit quality is visible. The
   calibrated twin is k * physics, i.e. physics shape, field magnitude.

2. ANOMALY DETECTION (robust statistics, no training needed)
   Rolling modified z-score (Iglewicz & Hoaglin):
       z = 0.6745 * (x - median) / MAD over the trailing ANOMALY_WINDOW
   |z| > ANOMALY_Z AND a deviation beyond the metric's engineering
   deadband (ANOMALY_MIN_DEV) flags a reading. Also flags TWIN_DIVERGENCE when a
   measured oil rate departs from the calibrated twin by more than
   DIVERGENCE_FRAC (sensor fault, pump wear or a real change).

3. DECLINE FORECAST (Arps exponential [STD])
   Fits q(t) = qi * exp(-D t) by log-linear least squares to the current
   production period and forecasts FORECAST_DAYS ahead with R^2.
=====================================================================
"""

import math
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

CALIB_MIN_POINTS = 3
CALIB_K_RANGE = (0.05, 5.0)
ANOMALY_WINDOW = 24
ANOMALY_MIN_POINTS = 8
ANOMALY_Z = 3.5
DIVERGENCE_FRAC = 0.5
FORECAST_DAYS = 30
# Oil rate is NOT z-scored: it declines by design within a CSS cycle, so the
# calibrated-twin divergence check (which models that decline) covers it.
ANOMALY_METRICS = ("wellhead_pressure_bar", "reservoir_pressure_bar", "spm")
# Alarm deadbands: a statistically unusual reading must also deviate by an
# engineering-meaningful amount (standard alarm-management practice).
ANOMALY_MIN_DEV = {"wellhead_pressure_bar": 1.5, "reservoir_pressure_bar": 2.0, "spm": 0.5}


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def calibrate(history: List[Dict]) -> Dict:
    """Least-squares twin->field scale factor over PRODUCTION-phase points."""
    pts = [(h["twin_oil_bopd"], h["oil_rate_bopd"]) for h in history
           if h.get("css_phase") == "PRODUCTION" and h.get("twin_oil_bopd", 0) > 0]
    if len(pts) < CALIB_MIN_POINTS:
        return {"status": "INSUFFICIENT_DATA", "points": len(pts), "k": 1.0,
                "r2": None, "mape_percent": None,
                "explanation": f"Need {CALIB_MIN_POINTS}+ production readings to calibrate (have {len(pts)})."}
    p = np.array([a for a, _ in pts], dtype=float)
    m = np.array([b for _, b in pts], dtype=float)

    def _fit(mask):
        return float(np.clip((m[mask] * p[mask]).sum() / max((p[mask] ** 2).sum(), 1e-9), *CALIB_K_RANGE))

    k = _fit(np.ones(len(p), dtype=bool))
    # One robust pass: readings already diverging (faults, pump wear) must not bias k.
    inliers = np.abs(m - k * p) <= DIVERGENCE_FRAC * k * p
    excluded = 0
    if CALIB_MIN_POINTS <= inliers.sum() < len(p):
        k = _fit(inliers)
        excluded = int(len(p) - inliers.sum())
        m, p = m[inliers], p[inliers]
    fit = k * p
    ss_res = float(((m - fit) ** 2).sum())
    ss_tot = float(((m - m.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else None
    nz = m > 1e-6
    mape = float(np.mean(np.abs((m[nz] - fit[nz]) / m[nz])) * 100.0) if nz.any() else None
    raw_mape = float(np.mean(np.abs((m[nz] - p[nz]) / m[nz])) * 100.0) if nz.any() else None
    return {
        "status": "CALIBRATED",
        "points": len(pts),
        "outliers_excluded": excluded,
        "k": round(k, 4),
        "r2": round(r2, 4) if r2 is not None else None,
        "mape_percent": round(mape, 2) if mape is not None else None,
        "uncalibrated_mape_percent": round(raw_mape, 2) if raw_mape is not None else None,
        "explanation": (
            f"Field oil rate averages {k:.2f}x the uncalibrated physics over {len(pts)} production "
            f"readings"
            + (f" ({excluded} diverging readings excluded as outliers)" if excluded else "")
            + f". Calibrated twin error {mape:.1f}% MAPE vs {raw_mape:.1f}% uncalibrated"
            + (f", R^2 {r2:.2f}." if r2 is not None else ".")
        ),
    }


def _modified_z(window: np.ndarray, x: float) -> Optional[float]:
    med = float(np.median(window))
    mad = float(np.median(np.abs(window - med)))
    if mad < 1e-9:
        return None
    return 0.6745 * (x - med) / mad


def detect_anomalies(history: List[Dict], k: Optional[float] = 1.0) -> List[Dict]:
    """Robust z-score outliers per metric + twin-divergence flags, newest last.

    k=None skips twin-divergence checks (twin not calibrated yet: comparing
    against uncalibrated physics would flag every reading).
    """
    out = []
    for i, h in enumerate(history):
        # Robust z is only meaningful within one CSS phase (shut-in vs producing differ by design).
        same_phase = [x for x in history[max(0, i - ANOMALY_WINDOW):i]
                      if x.get("css_phase") == h.get("css_phase")]
        if len(same_phase) >= ANOMALY_MIN_POINTS:
            for metric in ANOMALY_METRICS:
                vals = np.array([x[metric] for x in same_phase], dtype=float)
                z = _modified_z(vals, float(h[metric]))
                dev = abs(float(h[metric]) - float(np.median(vals)))
                if z is not None and abs(z) > ANOMALY_Z and dev >= ANOMALY_MIN_DEV[metric]:
                    out.append({
                        "timestamp": h["timestamp"], "metric": metric, "type": "STATISTICAL_OUTLIER",
                        "value": h[metric], "baseline_median": round(float(np.median(vals)), 3),
                        "z_score": round(z, 2),
                        "detail": (f"{metric} = {h[metric]} vs recent median "
                                   f"{float(np.median(vals)):.2f} (robust z {z:+.1f})."),
                    })
        if k is not None and h.get("css_phase") == "PRODUCTION" and h.get("twin_oil_bopd", 0) > 0:
            expected = k * h["twin_oil_bopd"]
            if expected > 1.0 and abs(h["oil_rate_bopd"] - expected) / expected > DIVERGENCE_FRAC:
                out.append({
                    "timestamp": h["timestamp"], "metric": "oil_rate_bopd", "type": "TWIN_DIVERGENCE",
                    "value": h["oil_rate_bopd"], "baseline_median": round(expected, 3),
                    "z_score": None,
                    "detail": (f"Measured {h['oil_rate_bopd']:.1f} bopd vs calibrated twin "
                               f"{expected:.1f} bopd ({(h['oil_rate_bopd'] / expected - 1) * 100:+.0f}%)."),
                })
    return out


def decline_forecast(history: List[Dict], days: int = FORECAST_DAYS) -> Dict:
    """Arps exponential fit to the latest uninterrupted PRODUCTION run."""
    run: List[Dict] = []
    for h in reversed(history):
        if h.get("css_phase") != "PRODUCTION":
            if run:
                break
            continue
        run.append(h)
    run.reverse()
    pts = []
    t0 = _parse_ts(run[0]["timestamp"]) if run else None
    for h in run:
        t = _parse_ts(h["timestamp"])
        if t is None or t0 is None or h["oil_rate_bopd"] <= 0:
            continue
        pts.append(((t - t0).total_seconds() / 86400.0, h["oil_rate_bopd"]))
    if len(pts) < 4 or pts[-1][0] - pts[0][0] < 1.0:
        return {"status": "INSUFFICIENT_DATA", "points": len(pts), "forecast": [],
                "explanation": "Need 4+ production readings spanning at least a day to fit a decline."}
    t = np.array([a for a, _ in pts])
    y = np.log(np.array([b for _, b in pts]))
    slope, intercept = np.polyfit(t, y, 1)
    fit = slope * t + intercept
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(((y - fit) ** 2).sum()) / ss_tot if ss_tot > 1e-12 else None
    D = -float(slope)
    qi = math.exp(intercept)
    t_last = float(t[-1])
    forecast = [{"day_ahead": d, "oil_rate_bopd": round(qi * math.exp(-D * (t_last + d)), 3)}
                for d in range(0, days + 1)]
    cum = sum(f["oil_rate_bopd"] for f in forecast[1:])
    return {
        "status": "FITTED",
        "points": len(pts),
        "decline_rate_per_day": round(D, 5),
        "decline_percent_per_month": round((1 - math.exp(-D * 30)) * 100, 2),
        "initial_rate_bopd": round(qi, 3),
        "r2": round(r2, 4) if r2 is not None else None,
        "forecast": forecast,
        "forecast_cum_oil_bbl": round(cum, 1),
        "explanation": (
            f"Exponential decline {D * 100:.2f}%/day ({(1 - math.exp(-D * 30)) * 100:.0f}%/month) fitted "
            f"to {len(pts)} production readings"
            + (f" (R^2 {r2:.2f})" if r2 is not None else "")
            + f"; {cum:.0f} bbl forecast over the next {days} days."
        ),
    }


def trend_summary(history: List[Dict]) -> Dict:
    if not history:
        return {}
    prod = [h for h in history if h.get("css_phase") == "PRODUCTION"]
    return {
        "readings": len(history),
        "production_readings": len(prod),
        "first_timestamp": history[0]["timestamp"],
        "last_timestamp": history[-1]["timestamp"],
        "mean_oil_rate_bopd": round(float(np.mean([h["oil_rate_bopd"] for h in prod])), 3) if prod else None,
        "max_oil_rate_bopd": round(max(h["oil_rate_bopd"] for h in prod), 3) if prod else None,
    }


def analyze(history: List[Dict]) -> Dict:
    calib = calibrate(history)
    return {
        "summary": trend_summary(history),
        "calibration": calib,
        "anomalies": detect_anomalies(
            history, calib["k"] if calib["status"] == "CALIBRATED" else None)[-50:],
        "decline": decline_forecast(history),
    }
