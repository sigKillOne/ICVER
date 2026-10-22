#!/usr/bin/env python3
"""
Training and Calibration Pipeline for ICVER Repayment Risk Model.

Trains an XGBoost credit risk classification model on Home Credit Default Risk data,
fits isotonic calibration on the validation set, benchmarks against a logistic regression
baseline and external source features, conducts SHAP additivity smoke tests, and exports
production artifacts (native XGBoost JSON, calibration knots, metadata, and test predictions).
"""
import json
import platform
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Union

import numpy as np
import pandas as pd
import scipy
from scipy.stats import ks_2samp
import shap
import sklearn
from sklearn.calibration import calibration_curve
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

# Paths
MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parent.parent
PROCESSED_DATA_DIR = REPO_ROOT / "backend" / "data" / "processed"
DEFAULT_ARTIFACTS_DIR = MODULE_DIR / "artifacts" / "risk"


# ==============================================================================
# 1. Data Loading & Validation
# ==============================================================================
def load_and_validate_data(
    features_path: Path = PROCESSED_DATA_DIR / "features_train.parquet",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, List[str]]:
    """
    Load features_train.parquet, run integrity asserts, and extract model features.
    """
    if not features_path.exists():
        raise FileNotFoundError(
            f"ERROR: Feature table not found at {features_path}. "
            "Please run 'python -m backend.ml.features_home_credit' first."
        )

    print(f"Loading feature table from {features_path}...")
    df = pd.read_parquet(features_path)

    n_rows = len(df)
    assert n_rows == 307511, f"Assertion Failed: Expected 307,511 rows, got {n_rows:,}"
    assert df["SK_ID_CURR"].nunique() == 307511, "Assertion Failed: SK_ID_CURR is not unique"
    assert "TARGET" in df.columns, "Assertion Failed: TARGET column missing from feature table"

    # Model features: exactly the 30 columns other than SK_ID_CURR and TARGET
    feature_cols = [c for c in df.columns if c not in ("SK_ID_CURR", "TARGET")]

    assert "TARGET" not in feature_cols, "Assertion Failed: TARGET must not be in feature list"
    assert not any(c.upper().startswith("EXT_SOURCE") for c in feature_cols), (
        "Assertion Failed: EXT_SOURCE columns must not be in model features"
    )
    assert not any("GENDER" in c.upper() for c in feature_cols), (
        "Assertion Failed: GENDER columns must not be in model features"
    )
    assert len(feature_cols) == 30, f"Assertion Failed: Expected exactly 30 features, got {len(feature_cols)}"

    X = df[feature_cols]
    y = df["TARGET"]

    print(f"Loaded {n_rows:,} rows across {len(feature_cols)} model features.")
    return df, X, y, feature_cols


# ==============================================================================
# 2. Stratified Data Splitting
# ==============================================================================
def perform_stratified_split(
    df: pd.DataFrame,
    X: pd.DataFrame,
    y: pd.Series,
    random_state: int = 42,
) -> Dict[str, Union[pd.DataFrame, pd.Series, np.ndarray]]:
    """
    Perform 60% train, 20% validation, 20% test stratified split on TARGET.
    """
    print("\nSplitting data into 60% Train, 20% Validation, 20% Test (stratified on TARGET)...")
    indices = np.arange(len(df))

    # First split: 80% train+val, 20% test
    X_train_val, X_test, y_train_val, y_test, idx_train_val, idx_test = train_test_split(
        X, y, indices, test_size=0.20, stratify=y, random_state=random_state
    )

    # Second split: from 80%, split 75% train (60% total) and 25% val (20% total)
    X_train, X_val, y_train, y_val, idx_train, idx_val = train_test_split(
        X_train_val, y_train_val, idx_train_val, test_size=0.25, stratify=y_train_val, random_state=random_state
    )

    split_dict = {
        "X_train": X_train,
        "y_train": y_train,
        "idx_train": idx_train,
        "X_val": X_val,
        "y_val": y_val,
        "idx_val": idx_val,
        "X_test": X_test,
        "y_test": y_test,
        "idx_test": idx_test,
    }

    print(f" - Train Split:      {len(X_train):,} rows ({len(X_train)/len(df):.1%}), Default Rate: {y_train.mean():.4%}")
    print(f" - Validation Split: {len(X_val):,} rows ({len(X_val)/len(df):.1%}), Default Rate: {y_val.mean():.4%}")
    print(f" - Test Split:       {len(X_test):,} rows ({len(X_test)/len(df):.1%}), Default Rate: {y_test.mean():.4%}")
    return split_dict


# ==============================================================================
# 3. 5-Fold Stratified Cross-Validation on Train Split
# ==============================================================================
def run_cv_evaluation(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int = 42,
) -> Tuple[float, float, List[float]]:
    """
    Run 5-fold stratified cross-validation on the train split only using the XGBoost config.
    """
    print("\nRunning 5-fold Stratified Cross-Validation on the Train Split only...")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)
    cv_aucs = []

    for fold, (train_idx, val_idx) in enumerate(skf.split(X_train, y_train), start=1):
        X_f_tr, y_f_tr = X_train.iloc[train_idx], y_train.iloc[train_idx]
        X_f_va, y_f_va = X_train.iloc[val_idx], y_train.iloc[val_idx]

        clf = xgb.XGBClassifier(
            tree_method="hist",
            learning_rate=0.03,
            max_depth=4,
            min_child_weight=50,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=5,
            n_estimators=3000,
            eval_metric="auc",
            early_stopping_rounds=100,
            random_state=random_state + fold,
            n_jobs=-1,
        )

        clf.fit(X_f_tr, y_f_tr, eval_set=[(X_f_va, y_f_va)], verbose=False)
        fold_pred = clf.predict_proba(X_f_va)[:, 1]
        auc = roc_auc_score(y_f_va, fold_pred)
        cv_aucs.append(auc)
        print(f"   Fold {fold}/5 AUC: {auc:.5f} (stopped at iter {clf.best_iteration})")

    mean_auc = float(np.mean(cv_aucs))
    std_auc = float(np.std(cv_aucs))
    print(f"5-Fold CV Train Split AUC: {mean_auc:.5f} (+/- {std_auc:.5f})")
    return mean_auc, std_auc, cv_aucs


# ==============================================================================
# 4. Primary Model Training (XGBoost)
# ==============================================================================
def train_xgboost_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    random_state: int = 42,
) -> xgb.XGBClassifier:
    """
    Train primary XGBoost classifier with early stopping on validation split.
    """
    print("\nTraining Primary XGBoost Model on Train Split (evaluating on Validation Split)...")
    clf = xgb.XGBClassifier(
        tree_method="hist",
        learning_rate=0.03,
        max_depth=4,
        min_child_weight=50,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=5,
        n_estimators=3000,
        eval_metric="auc",
        early_stopping_rounds=100,
        random_state=random_state,
        n_jobs=-1,
    )

    t0 = time.time()
    clf.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    elapsed = time.time() - t0

    val_preds = clf.predict_proba(X_val)[:, 1]
    val_auc = roc_auc_score(y_val, val_preds)

    print(f"XGBoost training complete in {elapsed:.2f}s.")
    print(f" - Best Iteration:  {clf.best_iteration}")
    print(f" - Validation AUC:   {val_auc:.5f}")
    return clf


# ==============================================================================
# 5. Baseline Logistic Regression
# ==============================================================================
def train_baseline_logistic(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    random_state: int = 42,
) -> Dict[str, float]:
    """
    Train baseline Logistic Regression with median imputation and standard scaling.
    """
    print("\nTraining Baseline Logistic Regression Pipeline (Imputer + Scaler + LogisticRegression)...")
    pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, random_state=random_state)),
        ]
    )

    t0 = time.time()
    pipeline.fit(X_train, y_train)
    elapsed = time.time() - t0

    val_preds = pipeline.predict_proba(X_val)[:, 1]
    test_preds = pipeline.predict_proba(X_test)[:, 1]

    val_auc = roc_auc_score(y_val, val_preds)
    test_auc = roc_auc_score(y_test, test_preds)
    test_brier = brier_score_loss(y_test, test_preds)
    test_logloss = log_loss(y_test, test_preds)

    print(f"Logistic Regression trained in {elapsed:.2f}s:")
    print(f" - Val AUC:   {val_auc:.5f}")
    print(f" - Test AUC:  {test_auc:.5f}")
    print(f" - Test Brier: {test_brier:.5f}")
    print(f" - Test LogLoss: {test_logloss:.5f}")

    return {
        "val_auc": float(val_auc),
        "test_auc": float(test_auc),
        "test_brier": float(test_brier),
        "test_logloss": float(test_logloss),
    }


# ==============================================================================
# 6. Comparison Model with External Sources
# ==============================================================================
def train_comparison_ext(
    idx_train: np.ndarray,
    idx_val: np.ndarray,
    idx_test: np.ndarray,
    random_state: int = 42,
) -> float:
    """
    Train comparison XGBoost model on features_train_with_ext.parquet to assess EXT_SOURCE lift.
    Never saved to artifacts.
    """
    ext_path = PROCESSED_DATA_DIR / "features_train_with_ext.parquet"
    if not ext_path.exists():
        print(f"Warning: {ext_path} not found. Skipping EXT_SOURCE comparison.")
        return np.nan

    print("\nTraining Comparison Model with External Sources (features_train_with_ext.parquet)...")
    df_ext = pd.read_parquet(ext_path)
    X_ext = df_ext.drop(columns=["SK_ID_CURR", "TARGET"])
    y_ext = df_ext["TARGET"]

    X_tr = X_ext.iloc[idx_train]
    y_tr = y_ext.iloc[idx_train]
    X_va = X_ext.iloc[idx_val]
    y_va = y_ext.iloc[idx_val]
    X_te = X_ext.iloc[idx_test]
    y_te = y_ext.iloc[idx_test]

    clf_ext = xgb.XGBClassifier(
        tree_method="hist",
        learning_rate=0.03,
        max_depth=4,
        min_child_weight=50,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=5,
        n_estimators=3000,
        eval_metric="auc",
        early_stopping_rounds=100,
        random_state=random_state,
        n_jobs=-1,
    )

    t0 = time.time()
    clf_ext.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
    elapsed = time.time() - t0

    test_preds_ext = clf_ext.predict_proba(X_te)[:, 1]
    test_auc_ext = roc_auc_score(y_te, test_preds_ext)

    print(f"Comparison model with EXT_SOURCE trained in {elapsed:.2f}s:")
    print(f" - Best Iteration: {clf_ext.best_iteration}")
    print(f" - Test AUC with EXT_SOURCE: {test_auc_ext:.5f}")
    return float(test_auc_ext)


# ==============================================================================
# 7. Probability Calibration (Isotonic Regression)
# ==============================================================================
def calibrate_probabilities(
    model: xgb.XGBClassifier,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> Dict[str, Union[np.ndarray, Dict, pd.DataFrame]]:
    """
    Fit isotonic regression on validation predictions, apply to test predictions,
    and compute Brier score, log loss, and 10-bin calibration table.
    """
    print("\nFitting Isotonic Calibration on Validation Set...")
    val_raw_preds = model.predict_proba(X_val)[:, 1]
    test_raw_preds = model.predict_proba(X_test)[:, 1]

    # Fit isotonic regression
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(val_raw_preds, y_val)

    val_calibrated_pd = iso.predict(val_raw_preds)
    test_calibrated_pd = iso.predict(test_raw_preds)

    # Calibration knots
    x_knots = iso.X_thresholds_.tolist()
    y_knots = iso.y_thresholds_.tolist()

    # Pre/Post metrics on test set
    brier_before = float(brier_score_loss(y_test, test_raw_preds))
    brier_after = float(brier_score_loss(y_test, test_calibrated_pd))
    logloss_before = float(log_loss(y_test, test_raw_preds))
    logloss_after = float(log_loss(y_test, test_calibrated_pd))

    print(f"Calibration Results on Test Set:")
    print(f" - Brier Score: {brier_before:.5f} (raw) -> {brier_after:.5f} (calibrated)")
    print(f" - Log Loss:    {logloss_before:.5f} (raw) -> {logloss_after:.5f} (calibrated)")

    # 10-bin calibration table on test set
    bins = pd.qcut(pd.Series(test_calibrated_pd).rank(method="first"), q=10, labels=False).values
    calib_rows = []
    y_test_arr = y_test.values
    for b in range(10):
        sub_mask = (bins == b)
        p_sub = test_calibrated_pd[sub_mask]
        y_sub = y_test_arr[sub_mask]

        calib_rows.append(
            {
                "bin": b + 1,
                "n_obs": int(len(p_sub)),
                "n_defaults": int(y_sub.sum()),
                "min_pred_pd": float(p_sub.min()),
                "max_pred_pd": float(p_sub.max()),
                "mean_pred_pd": float(p_sub.mean()),
                "observed_default_rate": float(y_sub.mean()),
                "diff": float(y_sub.mean() - p_sub.mean()),
            }
        )
    calib_table = pd.DataFrame(calib_rows)

    return {
        "val_raw_preds": val_raw_preds,
        "val_calibrated_pd": val_calibrated_pd,
        "test_raw_preds": test_raw_preds,
        "test_calibrated_pd": test_calibrated_pd,
        "x_knots": x_knots,
        "y_knots": y_knots,
        "brier_before": brier_before,
        "brier_after": brier_after,
        "logloss_before": logloss_before,
        "logloss_after": logloss_after,
        "calib_table": calib_table,
    }


# ==============================================================================
# 8. Risk Scoring (0-100) & Risk Bands
# ==============================================================================
def compute_risk_scores_and_bands(
    val_calibrated_pd: np.ndarray,
    test_calibrated_pd: np.ndarray,
    y_test: pd.Series,
) -> Dict[str, Union[np.ndarray, List, Dict, pd.DataFrame]]:
    """
    Map calibrated PDs to a 0-100 Risk Score (100 = safest, 0 = riskiest)
    using validation set quantile table, and segment into LOW/MEDIUM/HIGH policy bands.
    """
    print("\nComputing Risk Scores (0-100) and Policy Risk Bands...")
    percentiles = np.linspace(0, 100, 101)
    quantile_table = np.percentile(val_calibrated_pd, percentiles).tolist()

    # Cutoffs on validation set: LOW = lowest 40%, MEDIUM = next 40%, HIGH = top 20%
    p40 = float(np.percentile(val_calibrated_pd, 40.0))
    p80 = float(np.percentile(val_calibrated_pd, 80.0))

    def map_pd_to_score(pds: np.ndarray) -> np.ndarray:
        pop_pct = np.interp(pds, quantile_table, percentiles, left=0.0, right=100.0)
        return np.round(100.0 - pop_pct, 2)

    def map_pd_to_band(pds: np.ndarray) -> np.ndarray:
        bands = np.empty(len(pds), dtype=object)
        bands[pds <= p40] = "LOW"
        bands[(pds > p40) & (pds <= p80)] = "MEDIUM"
        bands[pds > p80] = "HIGH"
        return bands

    test_scores = map_pd_to_score(test_calibrated_pd)
    test_bands = map_pd_to_band(test_calibrated_pd)

    # Observed default rate by band on test set
    band_df = pd.DataFrame(
        {
            "band": test_bands,
            "target": y_test.values,
            "calibrated_pd": test_calibrated_pd,
        }
    )

    band_stats = (
        band_df.groupby("band")
        .agg(
            n_clients=("target", "count"),
            n_defaults=("target", "sum"),
            observed_default_rate=("target", "mean"),
            mean_calibrated_pd=("calibrated_pd", "mean"),
        )
        .loc[["LOW", "MEDIUM", "HIGH"]]
        .reset_index()
    )

    print("Observed Default Rates by Risk Band on Test Set:")
    for _, row in band_stats.iterrows():
        print(
            f" - Band {row['band']:<6}: {row['n_clients']:>6,} clients, "
            f"Observed Default Rate: {row['observed_default_rate']:>7.2%}, "
            f"Mean PD: {row['mean_calibrated_pd']:>7.2%}"
        )

    return {
        "quantile_table": quantile_table,
        "band_cutoffs": {
            "p40_low_max": p40,
            "p80_medium_max": p80,
            "definition": "LOW: PD <= p40, MEDIUM: p40 < PD <= p80, HIGH: PD > p80",
            "policy_note": "These cutoffs (40% / 40% / 20%) are a credit policy choice and can be tuned.",
        },
        "test_scores": test_scores,
        "test_bands": test_bands,
        "band_stats": band_stats,
    }


# ==============================================================================
# 9. Test Set Evaluation & Deciles
# ==============================================================================
def evaluate_test_set(
    y_test: pd.Series,
    test_calibrated_pd: np.ndarray,
    model: xgb.XGBClassifier,
    feature_names: List[str],
) -> Dict[str, Union[float, pd.DataFrame]]:
    """
    Compute comprehensive test metrics: ROC AUC, PR AUC, KS, Brier, LogLoss,
    predicted risk deciles, top decile lift, and top 15 features by gain.
    """
    print("\nEvaluating Final Calibrated Model on Unseen Test Split...")
    test_auc = float(roc_auc_score(y_test, test_calibrated_pd))
    test_pr_auc = float(average_precision_score(y_test, test_calibrated_pd))

    # KS statistic
    y_test_arr = y_test.values
    ks_res = ks_2samp(test_calibrated_pd[y_test_arr == 1], test_calibrated_pd[y_test_arr == 0])
    ks_stat = float(ks_res.statistic)

    brier = float(brier_score_loss(y_test, test_calibrated_pd))
    lloss = float(log_loss(y_test, test_calibrated_pd))

    overall_default_rate = float(y_test.mean())

    # Predicted-risk deciles
    decile_bins = pd.qcut(pd.Series(test_calibrated_pd).rank(method="first"), q=10, labels=False).values
    decile_rows = []
    for d in range(10):
        mask = (decile_bins == d)
        d_pds = test_calibrated_pd[mask]
        d_targets = y_test_arr[mask]
        d_rate = float(d_targets.mean())
        d_lift = float(d_rate / overall_default_rate) if overall_default_rate > 0 else np.nan

        decile_rows.append(
            {
                "decile": d + 1,
                "n_clients": int(len(d_pds)),
                "n_defaults": int(d_targets.sum()),
                "default_rate": d_rate,
                "lift": d_lift,
                "min_pd": float(d_pds.min()),
                "max_pd": float(d_pds.max()),
                "mean_pd": float(d_pds.mean()),
            }
        )
    deciles_df = pd.DataFrame(decile_rows)
    top_decile_lift = float(deciles_df.iloc[-1]["lift"])

    # Feature importances by gain
    booster = model.get_booster()
    score_dict = booster.get_score(importance_type="gain")
    # Map f0, f1... to feature names if necessary
    feature_gain_rows = []
    for feat in feature_names:
        gain = score_dict.get(feat, 0.0)
        feature_gain_rows.append({"feature": feat, "gain": gain})
    importance_df = (
        pd.DataFrame(feature_gain_rows)
        .sort_values(by="gain", ascending=False)
        .head(15)
        .reset_index(drop=True)
    )

    print(f"Test Set Evaluation Metrics:")
    print(f" - ROC AUC:           {test_auc:.5f}")
    print(f" - PR AUC:            {test_pr_auc:.5f}")
    print(f" - KS Statistic:      {ks_stat:.5f} ({ks_stat*100:.2f}%)")
    print(f" - Brier Score:       {brier:.5f}")
    print(f" - Log Loss:          {lloss:.5f}")
    print(f" - Top Decile Lift:   {top_decile_lift:.2f}x (Default Rate: {deciles_df.iloc[-1]['default_rate']:.2%})")

    return {
        "test_auc": test_auc,
        "test_pr_auc": test_pr_auc,
        "ks_stat": ks_stat,
        "brier_score": brier,
        "log_loss": lloss,
        "top_decile_lift": top_decile_lift,
        "deciles_df": deciles_df,
        "top15_features_df": importance_df,
    }


# ==============================================================================
# 10. SHAP Smoke Test
# ==============================================================================
def run_shap_smoke_test(
    model: xgb.XGBClassifier,
    X_test: pd.DataFrame,
    sample_size: int = 1000,
) -> float:
    """
    Compute TreeExplainer SHAP values for sample rows and verify additivity:
    base_value + sum(shap_values) == margin within 1e-3.
    """
    print(f"\nRunning SHAP Additivity Smoke Test on {sample_size:,} Test Sample Rows...")
    X_sample = X_test.head(sample_size)

    try:
        explainer = shap.TreeExplainer(model)
        shap_res = explainer(X_sample)

        base_val = explainer.expected_value
        margin = model.predict(X_sample, output_margin=True)
        shap_sum = shap_res.values.sum(axis=1)

        diff = np.abs(base_val + shap_sum - margin)
        max_error = float(np.max(diff))

        print(f"SHAP Additivity Test Passed! Maximum error: {max_error:.8e} (threshold: 1e-3).")
        assert max_error < 1e-3, f"SHAP additivity error {max_error} exceeded 1e-3 threshold"
        return max_error
    except Exception as e:
        print(f"ERROR: SHAP smoke test failed with XGBoost: {e}", file=sys.stderr)
        raise e


# ==============================================================================
# 11. Artifact Loader
# ==============================================================================
class RiskArtifacts:
    """Rebuilt risk model and calibration wrapper for inference."""

    def __init__(
        self,
        model: xgb.XGBClassifier,
        features: List[str],
        x_knots: np.ndarray,
        y_knots: np.ndarray,
        quantile_table: np.ndarray,
        p40: float,
        p80: float,
        meta: Dict,
    ):
        self.model = model
        self.features = features
        self.x_knots = x_knots
        self.y_knots = y_knots
        self.quantile_table = quantile_table
        self.percentiles = np.linspace(0, 100, len(quantile_table))
        self.p40 = p40
        self.p80 = p80
        self.meta = meta

    def predict_pd(self, df_input: pd.DataFrame) -> np.ndarray:
        """Predict calibrated probability of default."""
        X = df_input[self.features]
        raw_pd = self.model.predict_proba(X)[:, 1]
        calibrated_pd = np.interp(raw_pd, self.x_knots, self.y_knots, left=self.y_knots[0], right=self.y_knots[-1])
        return calibrated_pd

    def predict_risk_score(self, df_input: pd.DataFrame) -> np.ndarray:
        """Predict 0-100 risk score (100 = safest, 0 = riskiest)."""
        pds = self.predict_pd(df_input)
        pop_pct = np.interp(pds, self.quantile_table, self.percentiles, left=0.0, right=100.0)
        return np.round(100.0 - pop_pct, 2)

    def predict_band(self, df_input: pd.DataFrame) -> np.ndarray:
        """Predict policy risk band: LOW, MEDIUM, or HIGH."""
        pds = self.predict_pd(df_input)
        bands = np.empty(len(pds), dtype=object)
        bands[pds <= self.p40] = "LOW"
        bands[(pds > self.p40) & (pds <= self.p80)] = "MEDIUM"
        bands[pds > self.p80] = "HIGH"
        return bands


def load_risk_artifacts(artifacts_dir: Union[str, Path] = DEFAULT_ARTIFACTS_DIR) -> RiskArtifacts:
    """
    Rebuild the model and isotonic calibration from saved artifacts.
    """
    artifacts_dir = Path(artifacts_dir)

    model_file = artifacts_dir / "model_risk.json"
    calib_file = artifacts_dir / "calibration.json"
    meta_file = artifacts_dir / "risk_meta.json"

    for f in (model_file, calib_file, meta_file):
        if not f.exists():
            raise FileNotFoundError(f"Missing required artifact: {f}")

    # 1. Load XGBoost model
    model = xgb.XGBClassifier()
    model.load_model(str(model_file))

    # 2. Load calibration knots
    with open(calib_file, "r", encoding="utf-8") as f:
        calib_data = json.load(f)
    x_knots = np.array(calib_data["X_thresholds_"], dtype=np.float64)
    y_knots = np.array(calib_data["y_thresholds_"], dtype=np.float64)

    # 3. Load metadata
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    features = meta["features"]
    quantile_table = np.array(meta["quantile_table"], dtype=np.float64)
    p40 = float(meta["band_cutoffs"]["p40_low_max"])
    p80 = float(meta["band_cutoffs"]["p80_medium_max"])

    return RiskArtifacts(
        model=model,
        features=features,
        x_knots=x_knots,
        y_knots=y_knots,
        quantile_table=quantile_table,
        p40=p40,
        p80=p80,
        meta=meta,
    )


# ==============================================================================
# 12. Save Artifacts & Markdown Report
# ==============================================================================
def save_artifacts_and_metrics(
    artifacts_dir: Path,
    model: xgb.XGBClassifier,
    calib_info: Dict,
    score_info: Dict,
    eval_info: Dict,
    baseline_info: Dict,
    ext_test_auc: float,
    cv_mean: float,
    cv_std: float,
    feature_names: List[str],
    split_dict: Dict,
    shap_max_error: float,
    df_raw: pd.DataFrame,
    start_time: float,
) -> None:
    """
    Write model_risk.json, calibration.json, risk_meta.json, test_predictions.parquet,
    and comprehensive metrics.md.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Save native XGBoost model
    model_path = artifacts_dir / "model_risk.json"
    model.save_model(str(model_path))
    print(f"Saved native model to {model_path}")

    # 2. Save calibration knots
    calib_path = artifacts_dir / "calibration.json"
    calib_export = {
        "method": "isotonic",
        "X_thresholds_": calib_info["x_knots"],
        "y_thresholds_": calib_info["y_knots"],
    }
    with open(calib_path, "w", encoding="utf-8") as f:
        json.dump(calib_export, f, indent=2)
    print(f"Saved calibration knots to {calib_path}")

    # 3. Save risk metadata
    meta_path = artifacts_dir / "risk_meta.json"
    meta_export = {
        "model_name": "ICVER Repayment Risk Model (XGBoost)",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "training_time_seconds": round(time.time() - start_time, 2),
        "seed": 42,
        "features": feature_names,
        "n_features": len(feature_names),
        "split_sizes": {
            "train": len(split_dict["X_train"]),
            "validation": len(split_dict["X_val"]),
            "test": len(split_dict["X_test"]),
            "total": len(df_raw),
        },
        "band_cutoffs": score_info["band_cutoffs"],
        "quantile_table": score_info["quantile_table"],
        "package_versions": {
            "python": platform.python_version(),
            "xgboost": xgb.__version__,
            "shap": shap.__version__,
            "sklearn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "cross_validation_train_auc": {
            "mean": round(cv_mean, 5),
            "std": round(cv_std, 5),
        },
        "baseline_logistic": baseline_info,
        "comparison_with_ext_auc": round(ext_test_auc, 5) if not np.isnan(ext_test_auc) else None,
        "test_metrics": {
            "roc_auc": round(eval_info["test_auc"], 5),
            "pr_auc": round(eval_info["test_pr_auc"], 5),
            "ks_statistic": round(eval_info["ks_stat"], 5),
            "brier_score_raw": round(calib_info["brier_before"], 5),
            "brier_score_calibrated": round(calib_info["brier_after"], 5),
            "log_loss_raw": round(calib_info["logloss_before"], 5),
            "log_loss_calibrated": round(calib_info["logloss_after"], 5),
            "top_decile_lift": round(eval_info["top_decile_lift"], 2),
            "shap_max_error": shap_max_error,
        },
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_export, f, indent=2)
    print(f"Saved risk metadata to {meta_path}")

    # 4. Save test_predictions.parquet for fairness audit
    test_pred_path = PROCESSED_DATA_DIR / "test_predictions.parquet"
    test_idx = split_dict["idx_test"]
    test_pred_df = pd.DataFrame(
        {
            "SK_ID_CURR": df_raw["SK_ID_CURR"].iloc[test_idx].values,
            "TARGET": split_dict["y_test"].values,
            "calibrated_pd": np.round(calib_info["test_calibrated_pd"], 6),
            "risk_score_0_100": score_info["test_scores"],
            "band": score_info["test_bands"],
        }
    )
    test_pred_df.to_parquet(test_pred_path, index=False)
    print(f"Saved test predictions to {test_pred_path} ({len(test_pred_df):,} rows)")

    # 5. Build and write metrics.md
    metrics_path = artifacts_dir / "metrics.md"

    md_lines = []
    md_lines.append("# ICVER Repayment Risk Model - Training & Evaluation Metrics\n")
    md_lines.append(f"**Training Timestamp:** {meta_export['timestamp']}  ")
    md_lines.append(f"**Runtime:** {meta_export['training_time_seconds']} seconds  ")
    md_lines.append(f"**Target Dataset:** Home Credit Default Risk (`backend/data/processed/features_train.parquet`)\n")

    md_lines.append("## 1. Dataset & Split Architecture")
    md_lines.append(f"- **Total Population:** {len(df_raw):,} applicants across 30 non-demographic features")
    md_lines.append(f"- **Train Split (60%):** {len(split_dict['X_train']):,} rows (Default Rate: {split_dict['y_train'].mean():.4%})")
    md_lines.append(f"- **Validation Split (20%):** {len(split_dict['X_val']):,} rows (Default Rate: {split_dict['y_val'].mean():.4%})")
    md_lines.append(f"- **Test Split (20%):** {len(split_dict['X_test']):,} rows (Default Rate: {split_dict['y_test'].mean():.4%})")
    md_lines.append(f"- **Stratification:** Strict stratified sampling on `TARGET` with random seed 42\n")

    md_lines.append("## 2. Model Performance Summary (Unseen Test Set)")
    md_lines.append("| Metric | XGBoost (Calibrated) | Logistic Regression Baseline | Benchmark (with EXT_SOURCE) |")
    md_lines.append("| :--- | :---: | :---: | :---: |")
    md_lines.append(f"| **ROC AUC** | **{eval_info['test_auc']:.5f}** | {baseline_info['test_auc']:.5f} | **{ext_test_auc:.5f}** |")
    md_lines.append(f"| **PR AUC** | **{eval_info['test_pr_auc']:.5f}** | - | - |")
    md_lines.append(f"| **KS Statistic** | **{eval_info['ks_stat']*100:.2f}%** ({eval_info['ks_stat']:.4f}) | - | - |")
    md_lines.append(f"| **Brier Score** | **{calib_info['brier_after']:.5f}** | {baseline_info['test_brier']:.5f} | - |")
    md_lines.append(f"| **Log Loss** | **{calib_info['logloss_after']:.5f}** | {baseline_info['test_logloss']:.5f} | - |")
    md_lines.append(f"| **Top Decile Lift** | **{eval_info['top_decile_lift']:.2f}x** | - | - |\n")

    md_lines.append("## 3. Cross-Validation & Baseline Comparisons")
    md_lines.append(f"- **5-Fold Stratified CV on Train Split:** Mean AUC = **{cv_mean:.5f}** (std: **{cv_std:.5f}**)")
    md_lines.append(f"- **Logistic Regression Baseline Test AUC:** **{baseline_info['test_auc']:.5f}** (XGBoost improvement: **+{(eval_info['test_auc'] - baseline_info['test_auc'])*100:.2f}%** AUC)")
    md_lines.append(f"- **External Source Lift (`features_train_with_ext.parquet`):** Test AUC = **{ext_test_auc:.5f}** (adds **+{(ext_test_auc - eval_info['test_auc'])*100:.2f}%** AUC over alternative-data features alone)\n")

    md_lines.append("## 4. Probability Calibration (Isotonic Regression)")
    md_lines.append(f"- **Calibration Method:** Isotonic regression fitted strictly on validation-set predictions.")
    md_lines.append(f"- **Brier Score:** {calib_info['brier_before']:.5f} (raw) -> **{calib_info['brier_after']:.5f}** (calibrated)")
    md_lines.append(f"- **Log Loss:** {calib_info['logloss_before']:.5f} (raw) -> **{calib_info['logloss_after']:.5f}** (calibrated)\n")

    md_lines.append("### 10-Bin Calibration Table (Test Set)")
    md_lines.append("| Bin | Count | Defaults | Mean Predicted PD | Observed Default Rate | Diff |")
    md_lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
    for _, r in calib_info["calib_table"].iterrows():
        md_lines.append(
            f"| {int(r['bin'])} | {int(r['n_obs']):,} | {int(r['n_defaults']):,} | "
            f"{r['mean_pred_pd']:.2%} | {r['observed_default_rate']:.2%} | {r['diff']:+.4f} |"
        )
    md_lines.append("")

    md_lines.append("## 5. Predicted Risk Deciles & Top-Decile Lift")
    md_lines.append("| Decile | Applicants | Defaults | Default Rate | Lift vs Average | Mean Predicted PD |")
    md_lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
    for _, r in eval_info["deciles_df"].iterrows():
        md_lines.append(
            f"| {int(r['decile'])} | {int(r['n_clients']):,} | {int(r['n_defaults']):,} | "
            f"**{r['default_rate']:.2%}** | {r['lift']:.2f}x | {r['mean_pd']:.2%} |"
        )
    md_lines.append("")

    md_lines.append("## 6. Risk Score & Policy Risk Bands")
    md_lines.append("- **Score Formula:** `risk_score_0_100 = 100 - population_percentile(calibrated_PD)` (Higher score = Safer)")
    md_lines.append(f"- **Policy Cutoffs (from Validation Quantiles):**")
    md_lines.append(f"  - **LOW Risk:** Calibrated PD <= {score_info['band_cutoffs']['p40_low_max']:.2%} (Lowest 40% of risk)")
    md_lines.append(f"  - **MEDIUM Risk:** {score_info['band_cutoffs']['p40_low_max']:.2%} < Calibrated PD <= {score_info['band_cutoffs']['p80_medium_max']:.2%} (Middle 40%)")
    md_lines.append(f"  - **HIGH Risk:** Calibrated PD > {score_info['band_cutoffs']['p80_medium_max']:.2%} (Top 20% highest risk)")
    md_lines.append(f"  > *Note: These cutoffs are a credit policy choice and can be tailored to the lender's risk tolerance and capital reserves.*\n")

    md_lines.append("### Observed Default Rates by Risk Band (Test Set)")
    md_lines.append("| Band | Applicants | Defaults | Observed Default Rate | Mean Predicted PD |")
    md_lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for _, r in score_info["band_stats"].iterrows():
        md_lines.append(
            f"| **{r['band']}** | {int(r['n_clients']):,} | {int(r['n_defaults']):,} | "
            f"**{r['observed_default_rate']:.2%}** | {r['mean_calibrated_pd']:.2%} |"
        )
    md_lines.append("")

    md_lines.append("## 7. Feature Importance (Top 15 by Gain)")
    md_lines.append("| Rank | Feature Name | Total Gain |")
    md_lines.append("| :---: | :--- | :---: |")
    for idx, r in eval_info["top15_features_df"].iterrows():
        md_lines.append(f"| {idx+1} | `{r['feature']}` | {r['gain']:,.2f} |")
    md_lines.append("")

    md_lines.append("## 8. SHAP Additivity Verification")
    md_lines.append(f"- **Explainer:** `shap.TreeExplainer` on saved model")
    md_lines.append(f"- **Sample Size:** 1,000 test observations")
    md_lines.append(f"- **Verification:** `base_value + sum(shap_values) == margin_prediction` within `1e-3`")
    md_lines.append(f"- **Maximum Observed Error:** `{shap_max_error:.8e}` (PASS)\n")

    md_lines.append("## 9. Environment & Package Versions")
    for pkg, ver in meta_export["package_versions"].items():
        md_lines.append(f"- `{pkg}`: {ver}")
    md_lines.append("")

    metrics_text = "\n".join(md_lines)
    with open(metrics_path, "w", encoding="utf-8") as f:
        f.write(metrics_text)
    print(f"Saved metrics summary to {metrics_path}")


# ==============================================================================
# 13. Main Orchestration
# ==============================================================================
def main():
    start_time = time.time()
    print("=" * 80)
    print("ICVER REPAYMENT RISK MODEL TRAINING & EVALUATION PIPELINE")
    print("=" * 80)

    # 1. Load and validate data
    df_raw, X, y, feature_names = load_and_validate_data()

    # 2. Stratified split (60% train, 20% val, 20% test)
    split_dict = perform_stratified_split(df_raw, X, y, random_state=42)
    X_train, y_train = split_dict["X_train"], split_dict["y_train"]
    X_val, y_val = split_dict["X_val"], split_dict["y_val"]
    X_test, y_test = split_dict["X_test"], split_dict["y_test"]

    # 3. 5-fold CV on train split only
    cv_mean, cv_std, _ = run_cv_evaluation(X_train, y_train, random_state=42)

    # 4. Train primary XGBoost model on train split
    model = train_xgboost_model(X_train, y_train, X_val, y_val, random_state=42)

    # 5. Baseline Logistic Regression
    baseline_info = train_baseline_logistic(X_train, y_train, X_val, y_val, X_test, y_test, random_state=42)

    # 6. Comparison model with EXT_SOURCE features (never saved)
    ext_test_auc = train_comparison_ext(
        split_dict["idx_train"], split_dict["idx_val"], split_dict["idx_test"], random_state=42
    )

    # 7. Probability Calibration (Isotonic Regression)
    calib_info = calibrate_probabilities(model, X_val, y_val, X_test, y_test)

    # 8. Risk Scores (0-100) and Policy Risk Bands
    score_info = compute_risk_scores_and_bands(
        calib_info["val_calibrated_pd"], calib_info["test_calibrated_pd"], y_test
    )

    # 9. Test set evaluation (unseen test set)
    eval_info = evaluate_test_set(y_test, calib_info["test_calibrated_pd"], model, feature_names)

    # 10. SHAP smoke test
    shap_max_error = run_shap_smoke_test(model, X_test, sample_size=1000)

    # 11. Save artifacts and generate metrics.md
    save_artifacts_and_metrics(
        artifacts_dir=DEFAULT_ARTIFACTS_DIR,
        model=model,
        calib_info=calib_info,
        score_info=score_info,
        eval_info=eval_info,
        baseline_info=baseline_info,
        ext_test_auc=ext_test_auc,
        cv_mean=cv_mean,
        cv_std=cv_std,
        feature_names=feature_names,
        split_dict=split_dict,
        shap_max_error=shap_max_error,
        df_raw=df_raw,
        start_time=start_time,
    )

    # 12. Reload test: verify load_risk_artifacts reproduces predictions exactly
    print("\nVerifying Artifact Loader (load_risk_artifacts)...")
    reloaded_artifacts = load_risk_artifacts(DEFAULT_ARTIFACTS_DIR)
    reloaded_test_pd = reloaded_artifacts.predict_pd(X_test)
    max_pd_diff = float(np.max(np.abs(calib_info["test_calibrated_pd"] - reloaded_test_pd)))
    print(f"Artifact reload test max difference: {max_pd_diff:.8e}")
    assert max_pd_diff < 1e-6, f"Reloaded predictions differ from in-memory predictions by {max_pd_diff}"
    print("[PASS] Reloaded artifacts produce identical predictions to in-memory model!")

    total_time = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"TRAINING PIPELINE COMPLETED SUCCESSFULLY IN {total_time:.2f}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
