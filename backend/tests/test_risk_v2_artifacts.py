"""Tests for ICVER repayment-risk model v2 artifacts and inference helpers."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.ml.train_risk_model_v2 import (
    EXCLUDED_FEATURES,
    PROCESSED_DATA_DIR,
    assign_bands,
    load_risk_v2,
    predict_pd_v2,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = REPO_ROOT / "backend" / "ml" / "artifacts" / "risk_v2"
META_PATH = ARTIFACTS_DIR / "risk_meta_v2.json"
FEATURES_PATH = PROCESSED_DATA_DIR / "features_train.parquet"
PRED_PATH = PROCESSED_DATA_DIR / "test_predictions_v2.parquet"

HISTORY_FEATURES = [
    "n_prev_loans",
    "n_installments",
    "late_share",
    "underpaid_share",
    "mean_days_late",
    "max_days_late",
    "missing_payment_share",
    "recent_late_share",
    "has_installment_history",
    "bureau_n_credits",
    "bureau_n_active",
    "bureau_max_days_overdue",
    "has_bureau_history",
    "prev_n_apps",
    "prev_refused_share",
    "has_prev_application",
]


@pytest.fixture(scope="module")
def artifacts():
    if not META_PATH.exists():
        pytest.fail(f"v2 artifacts missing at {ARTIFACTS_DIR}; run python -m backend.ml.train_risk_model_v2")
    return load_risk_v2(ARTIFACTS_DIR)


def test_excluded_features_absent_from_saved_list(artifacts):
    saved = artifacts.features
    for name in EXCLUDED_FEATURES:
        assert name not in saved, f"{name} must not appear in the v2 feature list"


def test_feature_list_has_24_entries_and_no_target(artifacts):
    assert len(artifacts.features) == 24
    assert len(set(artifacts.features)) == 24
    assert "TARGET" not in artifacts.features
    assert "SK_ID_CURR" not in artifacts.features


def test_predictions_are_deterministic(artifacts):
    rng = np.random.RandomState(0)
    row = {feat: float(rng.random()) for feat in artifacts.features}
    df = pd.DataFrame([row])
    # Column order must not matter.
    df_shuffled = df[list(reversed(artifacts.features))]
    p1 = predict_pd_v2(df, artifacts=artifacts)
    p2 = predict_pd_v2(df, artifacts=artifacts)
    p3 = predict_pd_v2(df_shuffled, artifacts=artifacts)
    assert p1.shape == (1,)
    np.testing.assert_array_equal(p1, p2)
    np.testing.assert_allclose(p1, p3, rtol=0, atol=1e-12)


def test_all_nan_history_features_still_predict_pd(artifacts):
    row = {feat: 0.0 for feat in artifacts.features}
    for feat in HISTORY_FEATURES:
        assert feat in artifacts.features
        row[feat] = np.nan
    df = pd.DataFrame([row])
    pd_hat = predict_pd_v2(df, artifacts=artifacts)
    assert pd_hat.shape == (1,)
    assert 0.0 <= float(pd_hat[0]) <= 1.0


def test_reload_parity_against_saved_test_predictions(artifacts):
    if not FEATURES_PATH.exists() or not PRED_PATH.exists():
        pytest.skip(
            "git-ignored data files absent "
            f"(need {FEATURES_PATH.name} and {PRED_PATH.name} under backend/data/processed/)"
        )

    saved = pd.read_parquet(PRED_PATH).head(500)
    feats = pd.read_parquet(FEATURES_PATH, columns=["SK_ID_CURR"] + list(artifacts.features))
    merged = saved.merge(feats, on="SK_ID_CURR", how="left", validate="one_to_one")
    assert merged["SK_ID_CURR"].notna().all()
    reloaded = predict_pd_v2(merged, artifacts=artifacts)
    np.testing.assert_allclose(
        reloaded,
        merged["calibrated_pd"].to_numpy(dtype=np.float64),
        rtol=0,
        atol=1e-5,
    )


def test_band_assignment_matches_saved_cutoffs(artifacts):
    p40 = artifacts.p40
    p80 = artifacts.p80
    assert p40 < p80

    synthetic = np.array([p40, p40 + 1e-12, p80, p80 + 1e-12], dtype=np.float64)
    bands = assign_bands(synthetic, p40, p80)
    np.testing.assert_array_equal(bands, np.array(["LOW", "MEDIUM", "MEDIUM", "HIGH"], dtype=object))

    if not PRED_PATH.exists():
        pytest.skip(
            f"git-ignored data files absent (need {PRED_PATH.name} to check saved bands)"
        )
    saved = pd.read_parquet(PRED_PATH)
    expected = assign_bands(saved["calibrated_pd"].to_numpy(dtype=np.float64), p40, p80)
    np.testing.assert_array_equal(expected, saved["band"].to_numpy())
