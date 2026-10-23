"""Reference-population repayment-risk signal backed by the v2 Home Credit model.

The model was trained on the Home Credit Default Risk dataset. Its calibrated output
must be presented as a relative signal against that reference population, never as an
individual's probability of default.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "backend" / "ml" / "artifacts" / "risk_v2"
MODEL_FILENAME = "model_risk_v2.json"
CALIBRATION_FILENAME = "calibration_v2.json"
META_FILENAME = "risk_meta_v2.json"

# Assumption: a profile is considered sparse below 12 of the 24 model inputs.
MIN_PROVIDED_FEATURES_FOR_NORMAL_RELIABILITY = 12

# The three history-presence flags used by the Home Credit feature pipeline.
HISTORY_FLAGS: Tuple[str, ...] = (
    "has_installment_history",
    "has_bureau_history",
    "has_prev_application",
)

RELIABILITY_NORMAL = "NORMAL"
RELIABILITY_LIMITED = "LIMITED"

MAX_ERROR_LENGTH = 500
RELATIVE_SIZE_DECIMALS = 4
LOG_ODDS_DECIMALS = 6

FEATURE_LABELS: Dict[str, str] = {
    "credit_term_months": "loan term in months",
    "years_employed": "years of employment",
    "days_employed_anomaly": "employment-status anomaly",
    "days_since_phone_change": "days since phone number change",
    "years_since_id_published": "age of identity document",
    "years_registered": "years at registered address",
    "cnt_children": "number of children",
    "cnt_fam_members": "household size",
    "n_prev_loans": "number of previous loans",
    "n_installments": "historical installments recorded",
    "late_share": "share of late payments",
    "underpaid_share": "share of underpaid installments",
    "mean_days_late": "average days late",
    "max_days_late": "worst payment delay",
    "missing_payment_share": "share of missed payments",
    "recent_late_share": "recent late-payment share",
    "has_installment_history": "has installment history",
    "bureau_n_credits": "number of bureau credit lines",
    "bureau_n_active": "active bureau loans",
    "bureau_max_days_overdue": "worst bureau overdue days",
    "has_bureau_history": "has bureau history",
    "prev_n_apps": "number of prior applications",
    "prev_refused_share": "share of prior applications refused",
    "has_prev_application": "has prior applications",
}

_LOCK = threading.RLock()
_LOAD_ATTEMPTED = False
_ARTIFACTS: Optional[Dict[str, Any]] = None
_LOAD_ERROR: Optional[str] = None
_EXPLAINER: Any = None


def _load_artifacts() -> None:
    """Attempt to load artifacts once. All failures are captured, never raised."""
    global _LOAD_ATTEMPTED, _ARTIFACTS, _LOAD_ERROR, _EXPLAINER

    if _LOAD_ATTEMPTED:
        return

    with _LOCK:
        if _LOAD_ATTEMPTED:
            return
        _LOAD_ATTEMPTED = True
        try:
            import xgboost as xgb

            model_file = ARTIFACTS_DIR / MODEL_FILENAME
            calibration_file = ARTIFACTS_DIR / CALIBRATION_FILENAME
            meta_file = ARTIFACTS_DIR / META_FILENAME

            for path in (model_file, calibration_file, meta_file):
                if not path.exists():
                    raise FileNotFoundError(f"Missing risk v2 artifact: {path}")

            model = xgb.XGBClassifier()
            model.load_model(str(model_file))

            with open(calibration_file, "r", encoding="utf-8") as handle:
                calibration = json.load(handle)
            x_knots = np.asarray(calibration["X_thresholds_"], dtype=np.float64)
            y_knots = np.asarray(calibration["y_thresholds_"], dtype=np.float64)
            if len(x_knots) != len(y_knots) or len(x_knots) == 0:
                raise ValueError("Invalid isotonic calibration thresholds")

            with open(meta_file, "r", encoding="utf-8") as handle:
                meta = json.load(handle)

            features = list(meta["features"])
            quantile_table = np.asarray(meta["quantile_table"], dtype=np.float64)
            p40 = float(meta["band_cutoffs"]["p40_low_max"])
            p80 = float(meta["band_cutoffs"]["p80_medium_max"])

            _ARTIFACTS = {
                "model": model,
                "features": features,
                "feature_set": set(features),
                "x_knots": x_knots,
                "y_knots": y_knots,
                "quantile_table": quantile_table,
                "percentiles": np.linspace(0, 100, len(quantile_table)),
                "p40": p40,
                "p80": p80,
                "meta": meta,
            }
            _EXPLAINER = None
            _LOAD_ERROR = None
        except Exception as exc:  # noqa: BLE001 - failure must never crash the app
            _ARTIFACTS = None
            _EXPLAINER = None
            _LOAD_ERROR = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]


def is_loaded() -> bool:
    """Return whether the v2 artifacts are available, triggering a lazy load."""
    _load_artifacts()
    return _ARTIFACTS is not None


def get_error() -> Optional[str]:
    """Return the cached load error, if any."""
    _load_artifacts()
    return _LOAD_ERROR


def model_version() -> Optional[str]:
    """Human-readable model version from the saved metadata."""
    if not is_loaded():
        return None
    assert _ARTIFACTS is not None
    return str(_ARTIFACTS["meta"].get("model_name", "unknown"))


def _require_artifacts() -> Dict[str, Any]:
    _load_artifacts()
    if _ARTIFACTS is None:
        raise RuntimeError(f"Risk v2 artifacts unavailable: {_LOAD_ERROR}")
    return _ARTIFACTS


def _validate_keys(features: Dict[str, Any], artifact: Dict[str, Any]) -> List[str]:
    if not isinstance(features, dict):
        raise TypeError("features must be a dict")
    unknown = sorted(set(features) - artifact["feature_set"])
    if unknown:
        raise ValueError(f"Unknown risk feature keys: {unknown}")
    return list(features.keys())


def _prepare_frame(features: Dict[str, Any], artifact: Dict[str, Any]) -> pd.DataFrame:
    _validate_keys(features, artifact)
    row: Dict[str, float] = {}
    for name in artifact["features"]:
        value = features.get(name, np.nan)
        if value is None:
            value = np.nan
        try:
            row[name] = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Feature '{name}' must be numeric or NaN")
    return pd.DataFrame([row], columns=artifact["features"])


def _band(pd_value: float, artifact: Dict[str, Any]) -> str:
    if pd_value <= artifact["p40"]:
        return "LOW"
    if pd_value <= artifact["p80"]:
        return "MEDIUM"
    return "HIGH"


def predict(features: Dict[str, Any]) -> Dict[str, Any]:
    """Return calibrated reference-population PD, score and band for one profile."""
    artifact = _require_artifacts()
    frame = _prepare_frame(features, artifact)
    model = artifact["model"]

    raw_pd = float(model.predict_proba(frame)[:, 1][0])
    calibrated_pd = float(
        np.interp(
            raw_pd,
            artifact["x_knots"],
            artifact["y_knots"],
            left=float(artifact["y_knots"][0]),
            right=float(artifact["y_knots"][-1]),
        )
    )
    population_percentile = float(
        np.interp(
            calibrated_pd,
            artifact["quantile_table"],
            artifact["percentiles"],
            left=0.0,
            right=100.0,
        )
    )
    risk_score = round(100.0 - population_percentile, 2)

    return {
        "calibrated_pd": calibrated_pd,
        "risk_score_0_100": risk_score,
        "band": _band(calibrated_pd, artifact),
    }


def explain(features: Dict[str, Any], top_n: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """Return the largest SHAP log-odds factors raising and lowering risk."""
    if not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n must be a positive integer")

    artifact = _require_artifacts()
    frame = _prepare_frame(features, artifact)

    global _EXPLAINER
    with _LOCK:
        if _EXPLAINER is None:
            import shap

            _EXPLAINER = shap.TreeExplainer(artifact["model"])
        explainer = _EXPLAINER

    explanation = explainer(frame)
    values = np.asarray(explanation.values, dtype=np.float64)
    if values.ndim == 2:
        values = values[0]
    values = values.reshape(-1)

    total_abs = float(np.sum(np.abs(values)))
    contributions = list(zip(artifact["features"], values))

    def _factor(name: str, value: float, direction: str) -> Dict[str, Any]:
        relative = abs(value) / total_abs if total_abs > 0 else 0.0
        return {
            "feature": name,
            "label": FEATURE_LABELS[name],
            "direction": direction,
            "relative_size": round(float(relative), RELATIVE_SIZE_DECIMALS),
            "log_odds_contribution": round(float(value), LOG_ODDS_DECIMALS),
        }

    raising = sorted(
        ((name, value) for name, value in contributions if value > 0),
        key=lambda item: item[1],
        reverse=True,
    )[:top_n]
    lowering = sorted(
        ((name, value) for name, value in contributions if value < 0),
        key=lambda item: item[1],
    )[:top_n]

    return {
        "raising_risk": [_factor(name, value, "raises_risk") for name, value in raising],
        "lowering_risk": [_factor(name, value, "lowers_risk") for name, value in lowering],
    }


def _is_zero(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return np.isfinite(numeric) and numeric == 0.0


def input_summary(features: Dict[str, Any]) -> Dict[str, Any]:
    """Describe supplied/missing inputs and model-reliability for one profile."""
    artifact = _require_artifacts()
    provided_keys = _validate_keys(features, artifact)
    provided = [name for name in artifact["features"] if name in provided_keys]
    missing = [name for name in artifact["features"] if name not in provided_keys]

    all_history_flags_zero = all(
        flag in provided_keys and _is_zero(features[flag]) for flag in HISTORY_FLAGS
    )
    sparse_profile = len(provided) < MIN_PROVIDED_FEATURES_FOR_NORMAL_RELIABILITY

    if all_history_flags_zero or sparse_profile:
        reliability = RELIABILITY_LIMITED
        notes: List[str] = []
        if all_history_flags_zero:
            notes.append(
                "All credit-history flags are zero, so the reference model's accuracy is "
                "unproven for this profile."
            )
        if sparse_profile:
            notes.append(
                f"Only {len(provided)} of {len(artifact['features'])} model inputs were "
                "provided, so the signal is based on a sparse profile."
            )
        reliability_note = " ".join(notes)
    else:
        reliability = RELIABILITY_NORMAL
        reliability_note = (
            "At least 12 model inputs were provided and the profile is not flagged as "
            "having no credit history."
        )

    return {
        "provided": provided,
        "missing": missing,
        "provided_count": len(provided),
        "reliability": reliability,
        "reliability_note": reliability_note,
    }


def health() -> Dict[str, Any]:
    """Health payload for /health."""
    loaded = is_loaded()
    return {"loaded": loaded, "error": None if loaded else (get_error() or "unknown error")}
