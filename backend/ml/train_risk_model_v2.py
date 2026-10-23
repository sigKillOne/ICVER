#!/usr/bin/env python3
"""
v2 repayment-risk model: same Home Credit split and XGBoost recipe as v1,
with six currency/income-unit features excluded.
"""
from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import scipy
import shap
import sklearn
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from scipy.stats import ks_2samp

from backend.ml.train_risk_model import (
    DEFAULT_ARTIFACTS_DIR as V1_ARTIFACTS_DIR,
    PROCESSED_DATA_DIR,
    calibrate_probabilities,
    compute_risk_scores_and_bands,
    evaluate_test_set,
    load_and_validate_data,
    perform_stratified_split,
    run_cv_evaluation,
    run_shap_smoke_test,
    train_xgboost_model,
)

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parent.parent
DEFAULT_ARTIFACTS_DIR_V2 = MODULE_DIR / "artifacts" / "risk_v2"
V1_TEST_PREDICTIONS = PROCESSED_DATA_DIR / "test_predictions.parquet"
V2_TEST_PREDICTIONS = PROCESSED_DATA_DIR / "test_predictions_v2.parquet"
FEATURES_PATH = PROCESSED_DATA_DIR / "features_train.parquet"

RANDOM_STATE = 42
N_BOOTSTRAP = 1000
SHAP_SAMPLE_SIZE = 1000
SHAP_TOLERANCE = 1e-3

EXCLUDED_FEATURES: List[str] = [
    "income_total",
    "log_income",
    "income_per_family_member",
    "annuity_to_income",
    "credit_to_income",
    "bureau_total_debt",
]

EXCLUSION_REASONS: Dict[str, str] = {
    "income_total": (
        "Home Credit income currency and reporting period are undocumented, "
        "so this amount cannot be mapped to Indian workers' monthly rupee figures."
    ),
    "log_income": (
        "Derived from income_total; inherits the same undocumented currency and period."
    ),
    "income_per_family_member": (
        "Derived from income_total divided by family size; units cannot be mapped to INR."
    ),
    "annuity_to_income": (
        "Ratio of annuity to undocumented income; numerator and denominator currencies "
        "are not independently usable in an Indian rupee affordability engine."
    ),
    "credit_to_income": (
        "Ratio of credit amount to undocumented income; cannot be mapped to monthly INR."
    ),
    "bureau_total_debt": (
        "Aggregate bureau debt is in the dataset's undocumented currency and cannot be "
        "mapped to Indian rupee outstanding balances."
    ),
}

XGB_HYPERPARAMETERS: Dict[str, Union[str, float, int]] = {
    "tree_method": "hist",
    "learning_rate": 0.03,
    "max_depth": 4,
    "min_child_weight": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 5,
    "n_estimators": 3000,
    "eval_metric": "auc",
    "early_stopping_rounds": 100,
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------
class RiskArtifactsV2:
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

    def predict_raw_pd(self, df_input: pd.DataFrame) -> np.ndarray:
        X = df_input.reindex(columns=self.features)
        return self.model.predict_proba(X)[:, 1]

    def calibrate(self, raw_pd: np.ndarray) -> np.ndarray:
        return apply_isotonic_numpy(raw_pd, self.x_knots, self.y_knots)

    def predict_pd(self, df_input: pd.DataFrame) -> np.ndarray:
        return self.calibrate(self.predict_raw_pd(df_input))

    def predict_risk_score(self, df_input: pd.DataFrame) -> np.ndarray:
        pds = self.predict_pd(df_input)
        pop_pct = np.interp(
            pds, self.quantile_table, self.percentiles, left=0.0, right=100.0
        )
        return np.round(100.0 - pop_pct, 2)

    def predict_band(self, df_input: pd.DataFrame) -> np.ndarray:
        return assign_bands(self.predict_pd(df_input), self.p40, self.p80)


def apply_isotonic_numpy(
    raw_pd: np.ndarray, x_knots: np.ndarray, y_knots: np.ndarray
) -> np.ndarray:
    """Clip at the isotonic ends via numpy interpolation over saved thresholds."""
    return np.interp(
        raw_pd,
        x_knots,
        y_knots,
        left=float(y_knots[0]),
        right=float(y_knots[-1]),
    )


def assign_bands(pds: np.ndarray, p40: float, p80: float) -> np.ndarray:
    bands = np.empty(len(pds), dtype=object)
    bands[pds <= p40] = "LOW"
    bands[(pds > p40) & (pds <= p80)] = "MEDIUM"
    bands[pds > p80] = "HIGH"
    return bands


def load_risk_v2(artifacts_dir: Union[str, Path] = DEFAULT_ARTIFACTS_DIR_V2) -> RiskArtifactsV2:
    artifacts_dir = Path(artifacts_dir)
    model_file = artifacts_dir / "model_risk_v2.json"
    calib_file = artifacts_dir / "calibration_v2.json"
    meta_file = artifacts_dir / "risk_meta_v2.json"
    for f in (model_file, calib_file, meta_file):
        if not f.exists():
            raise FileNotFoundError(f"Missing required v2 artifact: {f}")

    model = xgb.XGBClassifier()
    model.load_model(str(model_file))

    with open(calib_file, "r", encoding="utf-8") as f:
        calib_data = json.load(f)
    x_knots = np.array(calib_data["X_thresholds_"], dtype=np.float64)
    y_knots = np.array(calib_data["y_thresholds_"], dtype=np.float64)

    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    features = list(meta["features"])
    quantile_table = np.array(meta["quantile_table"], dtype=np.float64)
    p40 = float(meta["band_cutoffs"]["p40_low_max"])
    p80 = float(meta["band_cutoffs"]["p80_medium_max"])

    return RiskArtifactsV2(
        model=model,
        features=features,
        x_knots=x_knots,
        y_knots=y_knots,
        quantile_table=quantile_table,
        p40=p40,
        p80=p80,
        meta=meta,
    )


def predict_pd_v2(
    df: pd.DataFrame,
    artifacts: Optional[RiskArtifactsV2] = None,
) -> np.ndarray:
    """Calibrated PD for a DataFrame that contains the 24 v2 features in any order."""
    if artifacts is None:
        artifacts = load_risk_v2()
    return artifacts.predict_pd(df)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _top_decile_lift(y: np.ndarray, pd_hat: np.ndarray) -> float:
    overall = float(y.mean())
    decile_bins = pd.qcut(pd.Series(pd_hat).rank(method="first"), q=10, labels=False).values
    mask = decile_bins == 9
    rate = float(y[mask].mean())
    return float(rate / overall) if overall > 0 else float("nan")


def calibration_table_10(y: np.ndarray, pd_hat: np.ndarray) -> pd.DataFrame:
    bins = pd.qcut(pd.Series(pd_hat).rank(method="first"), q=10, labels=False).values
    rows = []
    for b in range(10):
        sub = bins == b
        p_sub = pd_hat[sub]
        y_sub = y[sub]
        rows.append(
            {
                "bin": b + 1,
                "n_obs": int(sub.sum()),
                "n_defaults": int(y_sub.sum()),
                "mean_pred_pd": float(p_sub.mean()),
                "observed_default_rate": float(y_sub.mean()),
                "diff": float(y_sub.mean() - p_sub.mean()),
            }
        )
    return pd.DataFrame(rows)


def band_default_rates(y: np.ndarray, pd_hat: np.ndarray, bands: np.ndarray) -> pd.DataFrame:
    band_df = pd.DataFrame({"band": bands, "target": y, "calibrated_pd": pd_hat})
    stats = (
        band_df.groupby("band")
        .agg(
            n_clients=("target", "count"),
            n_defaults=("target", "sum"),
            observed_default_rate=("target", "mean"),
            mean_calibrated_pd=("calibrated_pd", "mean"),
        )
        .reindex(["LOW", "MEDIUM", "HIGH"])
        .reset_index()
    )
    return stats


def classification_metrics(y: np.ndarray, pd_hat: np.ndarray) -> Dict[str, float]:
    ks_res = ks_2samp(pd_hat[y == 1], pd_hat[y == 0])
    return {
        "roc_auc": float(roc_auc_score(y, pd_hat)),
        "pr_auc": float(average_precision_score(y, pd_hat)),
        "ks": float(ks_res.statistic),
        "brier": float(brier_score_loss(y, pd_hat)),
        "log_loss": float(log_loss(y, pd_hat)),
        "top_decile_lift": _top_decile_lift(y, pd_hat),
    }


def bootstrap_auc_ci(
    y: np.ndarray,
    pd_hat: np.ndarray,
    n_resamples: int = N_BOOTSTRAP,
    seed: int = RANDOM_STATE,
) -> Tuple[float, float, float]:
    rng = np.random.RandomState(seed)
    n = len(y)
    aucs = np.empty(n_resamples, dtype=np.float64)
    for i in range(n_resamples):
        idx = rng.randint(0, n, n)
        y_b = y[idx]
        if y_b.min() == y_b.max():
            aucs[i] = np.nan
            continue
        aucs[i] = roc_auc_score(y_b, pd_hat[idx])
    point = float(roc_auc_score(y, pd_hat))
    lo = float(np.nanpercentile(aucs, 2.5))
    hi = float(np.nanpercentile(aucs, 97.5))
    return point, lo, hi


def fmt_pct(x: float) -> str:
    return f"{x:.2%}"


def fmt5(x: float) -> str:
    return f"{x:.5f}"


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def assert_same_test_ids(df_raw: pd.DataFrame, idx_test: np.ndarray) -> None:
    if not V1_TEST_PREDICTIONS.exists():
        raise FileNotFoundError(
            f"Cannot verify the v1 test split: {V1_TEST_PREDICTIONS} is missing."
        )
    v1_pred = pd.read_parquet(V1_TEST_PREDICTIONS, columns=["SK_ID_CURR"])
    v2_ids = set(df_raw["SK_ID_CURR"].iloc[idx_test].astype(int).tolist())
    v1_ids = set(v1_pred["SK_ID_CURR"].astype(int).tolist())
    if v2_ids != v1_ids:
        only_v1 = sorted(v1_ids - v2_ids)[:10]
        only_v2 = sorted(v2_ids - v1_ids)[:10]
        raise AssertionError(
            "v2 test SK_ID_CURR set does not equal test_predictions.parquet. "
            f"v1 n={len(v1_ids)}, v2 n={len(v2_ids)}, "
            f"only_in_v1_sample={only_v1}, only_in_v2_sample={only_v2}"
        )
    print(
        f"[PASS] v2 test SK_ID_CURR set matches v1 test_predictions.parquet "
        f"({len(v2_ids):,} IDs)."
    )


def write_metrics_md(
    path: Path,
    meta: Dict,
    v1_metrics: Dict[str, float],
    v2_metrics: Dict[str, float],
    v1_ci: Tuple[float, float, float],
    v2_ci: Tuple[float, float, float],
    v1_calib: pd.DataFrame,
    v2_calib: pd.DataFrame,
    v1_bands: pd.DataFrame,
    v2_bands: pd.DataFrame,
    v2_deciles: pd.DataFrame,
    top15: pd.DataFrame,
    segment_aucs: Dict[str, Dict[str, float]],
    interp_max_abs_diff: float,
    shap_max_error: float,
    cv_mean: float,
    cv_std: float,
    cv_aucs: List[float],
    split_rates: Dict[str, float],
    best_iteration: int,
) -> None:
    lines: List[str] = []
    lines.append("# ICVER Repayment Risk Model v2 — Training & Evaluation Metrics")
    lines.append("")
    lines.append(f"**Training Timestamp:** {meta['timestamp']}  ")
    lines.append(f"**Runtime:** {meta['training_time_seconds']} seconds  ")
    lines.append(
        "**Target Dataset:** Home Credit Default Risk "
        "(`backend/data/processed/features_train.parquet`)"
    )
    lines.append("")
    lines.append("## 1. Why v2 exists")
    lines.append(
        "v1 used six features whose units cannot be mapped to Indian workers' monthly "
        "rupee figures because the Home Credit currency and income period are undocumented. "
        "v2 drops those six features and retrains with the same split, seed, XGBoost "
        "hyperparameters, early stopping, and isotonic calibration as v1. "
        "`credit_term_months` is kept because it is a ratio of two amounts in the same currency. "
        "Income and affordability stay in rule-based code, not in this model."
    )
    lines.append("")
    lines.append("### Excluded features")
    lines.append("| Feature | Reason |")
    lines.append("| :--- | :--- |")
    for feat in EXCLUDED_FEATURES:
        lines.append(f"| `{feat}` | {EXCLUSION_REASONS[feat]} |")
    lines.append("")
    lines.append(f"- **v2 feature count:** {meta['n_features']} (v1 had 30)")
    lines.append(f"- **Seed:** {meta['seed']}")
    lines.append("")
    lines.append("## 2. Dataset & split (identical to v1)")
    lines.append(
        f"- **Total population:** {meta['split_sizes']['total']:,} applicants"
    )
    lines.append(
        f"- **Train (60%):** {meta['split_sizes']['train']:,} rows "
        f"(default rate {split_rates['train']:.4%})"
    )
    lines.append(
        f"- **Validation (20%):** {meta['split_sizes']['validation']:,} rows "
        f"(default rate {split_rates['validation']:.4%})"
    )
    lines.append(
        f"- **Test (20%):** {meta['split_sizes']['test']:,} rows "
        f"(default rate {split_rates['test']:.4%})"
    )
    lines.append(
        "- **Test SK_ID_CURR set:** asserted equal to "
        "`backend/data/processed/test_predictions.parquet`"
    )
    lines.append("- **Stratification:** `TARGET`, `random_state=42`, same `train_test_split` path as v1")
    lines.append("")
    lines.append("## 3. XGBoost hyperparameters (copied from v1)")
    lines.append("| Parameter | Value |")
    lines.append("| :--- | :--- |")
    for k, v in XGB_HYPERPARAMETERS.items():
        lines.append(f"| `{k}` | {v} |")
    lines.append(f"| best_iteration (this run) | {best_iteration} |")
    lines.append("")
    lines.append("## 4. Cross-validation (train split only)")
    lines.append(
        f"- **5-fold stratified CV AUC:** **{cv_mean:.5f}** (std **{cv_std:.5f}**)"
    )
    for i, auc in enumerate(cv_aucs, start=1):
        lines.append(f"- Fold {i}: {auc:.5f}")
    lines.append("")
    lines.append("## 5. v1 vs v2 on the same test set")
    lines.append(
        "v1 numbers are recomputed from `test_predictions.parquet` (calibrated PD). "
        "v2 numbers use this run's calibrated PD. Both use the same `SK_ID_CURR` test set."
    )
    lines.append("")
    lines.append("| Metric | v1 (30 features) | v2 (24 features) | Δ (v2 − v1) |")
    lines.append("| :--- | :---: | :---: | :---: |")

    def row(name: str, key: str, nd: int = 5) -> None:
        a, b = v1_metrics[key], v2_metrics[key]
        lines.append(f"| **{name}** | {a:.{nd}f} | **{b:.{nd}f}** | {b - a:+.{nd}f} |")

    row("ROC AUC", "roc_auc")
    row("PR AUC", "pr_auc")
    row("KS", "ks")
    row("Brier", "brier")
    row("Log loss", "log_loss")
    row("Top-decile lift", "top_decile_lift", nd=2)
    lines.append(
        f"| **ROC AUC 95% bootstrap CI** "
        f"(n={N_BOOTSTRAP}, seed={RANDOM_STATE}) | "
        f"{v1_ci[0]:.5f} [{v1_ci[1]:.5f}, {v1_ci[2]:.5f}] | "
        f"**{v2_ci[0]:.5f} [{v2_ci[1]:.5f}, {v2_ci[2]:.5f}]** | — |"
    )
    lines.append("")
    lines.append("### 10-bin calibration table (test set)")
    lines.append("")
    lines.append("**v1**")
    lines.append("| Bin | Count | Defaults | Mean predicted PD | Observed default rate | Diff |")
    lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
    for _, r in v1_calib.iterrows():
        lines.append(
            f"| {int(r['bin'])} | {int(r['n_obs']):,} | {int(r['n_defaults']):,} | "
            f"{r['mean_pred_pd']:.2%} | {r['observed_default_rate']:.2%} | {r['diff']:+.4f} |"
        )
    lines.append("")
    lines.append("**v2**")
    lines.append("| Bin | Count | Defaults | Mean predicted PD | Observed default rate | Diff |")
    lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
    for _, r in v2_calib.iterrows():
        lines.append(
            f"| {int(r['bin'])} | {int(r['n_obs']):,} | {int(r['n_defaults']):,} | "
            f"{r['mean_pred_pd']:.2%} | {r['observed_default_rate']:.2%} | {r['diff']:+.4f} |"
        )
    lines.append("")
    lines.append("### Default rate by risk band (test set)")
    lines.append("")
    lines.append("Bands are LOW = lowest 40% of validation calibrated PD, MEDIUM = next 40%, HIGH = top 20%. Each model uses its own validation cutoffs.")
    lines.append("")
    lines.append("**v1**")
    lines.append("| Band | Applicants | Defaults | Observed default rate | Mean predicted PD |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for _, r in v1_bands.iterrows():
        lines.append(
            f"| **{r['band']}** | {int(r['n_clients']):,} | {int(r['n_defaults']):,} | "
            f"**{r['observed_default_rate']:.2%}** | {r['mean_calibrated_pd']:.2%} |"
        )
    lines.append("")
    lines.append("**v2**")
    lines.append("| Band | Applicants | Defaults | Observed default rate | Mean predicted PD |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for _, r in v2_bands.iterrows():
        lines.append(
            f"| **{r['band']}** | {int(r['n_clients']):,} | {int(r['n_defaults']):,} | "
            f"**{r['observed_default_rate']:.2%}** | {r['mean_calibrated_pd']:.2%} |"
        )
    lines.append("")
    lines.append("## 6. v2 predicted-risk deciles (test set)")
    lines.append("| Decile | Applicants | Defaults | Default rate | Lift | Mean PD |")
    lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
    for _, r in v2_deciles.iterrows():
        lines.append(
            f"| {int(r['decile'])} | {int(r['n_clients']):,} | {int(r['n_defaults']):,} | "
            f"**{r['default_rate']:.2%}** | {r['lift']:.2f}x | {r['mean_pd']:.2%} |"
        )
    lines.append("")
    lines.append("## 7. Thin-file segments (v2 test AUC)")
    lines.append(
        "Flags joined from `features_train.parquet` onto the shared test `SK_ID_CURR` set."
    )
    lines.append("")
    lines.append("| Segment | n | Defaults | Default rate | v2 ROC AUC |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for key, label in (
        ("no_bureau_history", "`has_bureau_history == 0`"),
        ("no_installment_history", "`has_installment_history == 0`"),
    ):
        s = segment_aucs[key]
        auc_s = "n/a (single class)" if np.isnan(s["roc_auc"]) else f"{s['roc_auc']:.5f}"
        lines.append(
            f"| {label} | {int(s['n']):,} | {int(s['n_defaults']):,} | "
            f"{s['default_rate']:.2%} | **{auc_s}** |"
        )
    lines.append("")
    lines.append("## 8. Risk score and policy bands (v2)")
    lines.append(
        "- **Score:** `risk_score_0_100 = 100 − population_percentile(calibrated_PD)` "
        "using the validation quantile table."
    )
    p40 = meta["band_cutoffs"]["p40_low_max"]
    p80 = meta["band_cutoffs"]["p80_medium_max"]
    lines.append(f"- **LOW:** calibrated PD ≤ {p40:.6f} (lowest 40% of validation PD)")
    lines.append(f"- **MEDIUM:** {p40:.6f} < PD ≤ {p80:.6f} (next 40%)")
    lines.append(f"- **HIGH:** PD > {p80:.6f} (top 20%)")
    lines.append("")
    lines.append("## 9. Feature importance (v2, top 15 by gain)")
    lines.append("| Rank | Feature | Gain |")
    lines.append("| :---: | :--- | :---: |")
    for idx, r in top15.iterrows():
        lines.append(f"| {idx + 1} | `{r['feature']}` | {r['gain']:,.2f} |")
    lines.append("")
    lines.append("## 10. SHAP additivity and calibration reload")
    lines.append(f"- **SHAP sample:** {SHAP_SAMPLE_SIZE} test rows, tolerance `{SHAP_TOLERANCE}`")
    lines.append(f"- **Maximum SHAP additivity error:** `{shap_max_error:.8e}`")
    lines.append(
        "- **Numpy isotonic vs sklearn `IsotonicRegression.predict` on the test set:** "
        f"max absolute difference `{interp_max_abs_diff:.8e}`"
    )
    lines.append("")
    lines.append("## 11. Environment")
    for pkg, ver in meta["package_versions"].items():
        lines.append(f"- `{pkg}`: {ver}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    start_time = time.time()
    print("=" * 80)
    print("ICVER REPAYMENT RISK MODEL v2")
    print("=" * 80)

    df_raw, X_all, y, feature_names_v1 = load_and_validate_data()
    missing_excl = [c for c in EXCLUDED_FEATURES if c not in feature_names_v1]
    if missing_excl:
        raise AssertionError(f"Excluded features missing from v1 table: {missing_excl}")

    feature_names = [c for c in feature_names_v1 if c not in EXCLUDED_FEATURES]
    assert "TARGET" not in feature_names
    assert len(feature_names) == 24, f"Expected 24 features, got {len(feature_names)}"
    assert set(EXCLUDED_FEATURES).isdisjoint(feature_names)

    split_dict = perform_stratified_split(df_raw, X_all, y, random_state=RANDOM_STATE)
    assert_same_test_ids(df_raw, split_dict["idx_test"])

    X_train = split_dict["X_train"][feature_names]
    X_val = split_dict["X_val"][feature_names]
    X_test = split_dict["X_test"][feature_names]
    y_train = split_dict["y_train"]
    y_val = split_dict["y_val"]
    y_test = split_dict["y_test"]

    cv_mean, cv_std, cv_aucs = run_cv_evaluation(X_train, y_train, random_state=RANDOM_STATE)
    model = train_xgboost_model(X_train, y_train, X_val, y_val, random_state=RANDOM_STATE)
    best_iteration = int(model.best_iteration)

    calib_info = calibrate_probabilities(model, X_val, y_val, X_test, y_test)

    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(calib_info["val_raw_preds"], y_val)
    sklearn_test = iso.predict(calib_info["test_raw_preds"])
    numpy_test = apply_isotonic_numpy(
        calib_info["test_raw_preds"],
        np.asarray(calib_info["x_knots"], dtype=np.float64),
        np.asarray(calib_info["y_knots"], dtype=np.float64),
    )
    interp_max_abs_diff = float(np.max(np.abs(sklearn_test - numpy_test)))
    print(f"Numpy vs sklearn isotonic max abs diff on test: {interp_max_abs_diff:.8e}")

    score_info = compute_risk_scores_and_bands(
        calib_info["val_calibrated_pd"], calib_info["test_calibrated_pd"], y_test
    )
    eval_info = evaluate_test_set(
        y_test, calib_info["test_calibrated_pd"], model, feature_names
    )
    shap_max_error = run_shap_smoke_test(model, X_test, sample_size=SHAP_SAMPLE_SIZE)

    test_ids = df_raw["SK_ID_CURR"].iloc[split_dict["idx_test"]].astype(int).values
    y_test_arr = np.asarray(y_test, dtype=np.int64)
    v2_pd = np.asarray(calib_info["test_calibrated_pd"], dtype=np.float64)

    v1_pred = pd.read_parquet(V1_TEST_PREDICTIONS)
    v1_aligned = (
        pd.DataFrame({"SK_ID_CURR": test_ids})
        .merge(v1_pred, on="SK_ID_CURR", how="left", validate="one_to_one")
    )
    if v1_aligned["calibrated_pd"].isna().any():
        raise AssertionError("v1 test_predictions.parquet missing IDs after alignment.")
    v1_pd = v1_aligned["calibrated_pd"].to_numpy(dtype=np.float64)
    v1_bands_arr = v1_aligned["band"].to_numpy()

    v1_metrics = classification_metrics(y_test_arr, v1_pd)
    v2_metrics = classification_metrics(y_test_arr, v2_pd)
    v1_ci = bootstrap_auc_ci(y_test_arr, v1_pd)
    v2_ci = bootstrap_auc_ci(y_test_arr, v2_pd)
    v1_calib = calibration_table_10(y_test_arr, v1_pd)
    v2_calib = calibration_table_10(y_test_arr, v2_pd)
    v1_band_stats = band_default_rates(y_test_arr, v1_pd, v1_bands_arr)
    v2_band_stats = score_info["band_stats"]

    flags = df_raw.iloc[split_dict["idx_test"]][
        ["SK_ID_CURR", "has_bureau_history", "has_installment_history"]
    ].copy()
    flags["SK_ID_CURR"] = flags["SK_ID_CURR"].astype(int)
    flags = flags.reset_index(drop=True)
    flags["TARGET"] = y_test_arr
    flags["calibrated_pd"] = v2_pd

    def segment_auc(mask: np.ndarray) -> Dict[str, float]:
        n = int(mask.sum())
        y_s = y_test_arr[mask]
        p_s = v2_pd[mask]
        n_def = int(y_s.sum())
        rate = float(y_s.mean()) if n else float("nan")
        if n == 0 or y_s.min() == y_s.max():
            auc = float("nan")
        else:
            auc = float(roc_auc_score(y_s, p_s))
        return {"n": n, "n_defaults": n_def, "default_rate": rate, "roc_auc": auc}

    bureau_flag = flags["has_bureau_history"].to_numpy()
    instal_flag = flags["has_installment_history"].to_numpy()
    segment_aucs = {
        "no_bureau_history": segment_auc(bureau_flag == 0),
        "no_installment_history": segment_auc(instal_flag == 0),
    }
    print(
        "v2 AUC no bureau history "
        f"(n={segment_aucs['no_bureau_history']['n']}): "
        f"{segment_aucs['no_bureau_history']['roc_auc']}"
    )
    print(
        "v2 AUC no installment history "
        f"(n={segment_aucs['no_installment_history']['n']}): "
        f"{segment_aucs['no_installment_history']['roc_auc']}"
    )

    artifacts_dir = DEFAULT_ARTIFACTS_DIR_V2
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    model_path = artifacts_dir / "model_risk_v2.json"
    model.save_model(str(model_path))
    print(f"Saved native model to {model_path}")

    calib_export = {
        "method": "isotonic",
        "X_thresholds_": [float(x) for x in calib_info["x_knots"]],
        "y_thresholds_": [float(y_) for y_ in calib_info["y_knots"]],
    }
    calib_path = artifacts_dir / "calibration_v2.json"
    with open(calib_path, "w", encoding="utf-8") as f:
        json.dump(calib_export, f, indent=2)
    print(f"Saved calibration to {calib_path}")

    package_versions = {
        "python": platform.python_version(),
        "xgboost": xgb.__version__,
        "shap": shap.__version__,
        "sklearn": sklearn.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }
    training_time = round(time.time() - start_time, 2)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    meta_export = {
        "model_name": "ICVER Repayment Risk Model v2 (XGBoost)",
        "timestamp": timestamp,
        "training_time_seconds": training_time,
        "seed": RANDOM_STATE,
        "features": feature_names,
        "n_features": len(feature_names),
        "excluded_features": [
            {"name": name, "reason": EXCLUSION_REASONS[name]} for name in EXCLUDED_FEATURES
        ],
        "hyperparameters": XGB_HYPERPARAMETERS,
        "best_iteration": best_iteration,
        "split_sizes": {
            "train": int(len(X_train)),
            "validation": int(len(X_val)),
            "test": int(len(X_test)),
            "total": int(len(df_raw)),
        },
        "band_cutoffs": {
            "p40_low_max": float(score_info["band_cutoffs"]["p40_low_max"]),
            "p80_medium_max": float(score_info["band_cutoffs"]["p80_medium_max"]),
            "definition": score_info["band_cutoffs"]["definition"],
            "policy_note": score_info["band_cutoffs"]["policy_note"],
        },
        "quantile_table": [float(x) for x in score_info["quantile_table"]],
        "package_versions": package_versions,
        "cross_validation_train_auc": {
            "mean": round(cv_mean, 5),
            "std": round(cv_std, 5),
            "folds": [round(float(a), 5) for a in cv_aucs],
        },
        "isotonic_numpy_vs_sklearn_max_abs_diff": interp_max_abs_diff,
        "test_metrics": {
            "roc_auc": round(v2_metrics["roc_auc"], 5),
            "pr_auc": round(v2_metrics["pr_auc"], 5),
            "ks_statistic": round(v2_metrics["ks"], 5),
            "brier_score_calibrated": round(v2_metrics["brier"], 5),
            "log_loss_calibrated": round(v2_metrics["log_loss"], 5),
            "top_decile_lift": round(v2_metrics["top_decile_lift"], 2),
            "roc_auc_bootstrap_ci_95": {
                "point": round(v2_ci[0], 5),
                "low": round(v2_ci[1], 5),
                "high": round(v2_ci[2], 5),
                "n_resamples": N_BOOTSTRAP,
                "seed": RANDOM_STATE,
            },
            "shap_max_error": shap_max_error,
            "segments": {
                "no_bureau_history": {
                    "n": segment_aucs["no_bureau_history"]["n"],
                    "roc_auc": (
                        None
                        if np.isnan(segment_aucs["no_bureau_history"]["roc_auc"])
                        else round(segment_aucs["no_bureau_history"]["roc_auc"], 5)
                    ),
                },
                "no_installment_history": {
                    "n": segment_aucs["no_installment_history"]["n"],
                    "roc_auc": (
                        None
                        if np.isnan(segment_aucs["no_installment_history"]["roc_auc"])
                        else round(segment_aucs["no_installment_history"]["roc_auc"], 5)
                    ),
                },
            },
        },
        "v1_test_metrics_same_ids": {
            "roc_auc": round(v1_metrics["roc_auc"], 5),
            "pr_auc": round(v1_metrics["pr_auc"], 5),
            "ks_statistic": round(v1_metrics["ks"], 5),
            "brier_score_calibrated": round(v1_metrics["brier"], 5),
            "log_loss_calibrated": round(v1_metrics["log_loss"], 5),
            "top_decile_lift": round(v1_metrics["top_decile_lift"], 2),
            "roc_auc_bootstrap_ci_95": {
                "point": round(v1_ci[0], 5),
                "low": round(v1_ci[1], 5),
                "high": round(v1_ci[2], 5),
                "n_resamples": N_BOOTSTRAP,
                "seed": RANDOM_STATE,
            },
        },
    }
    meta_path = artifacts_dir / "risk_meta_v2.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_export, f, indent=2)
    print(f"Saved metadata to {meta_path}")

    test_pred_df = pd.DataFrame(
        {
            "SK_ID_CURR": test_ids,
            "TARGET": y_test_arr,
            "calibrated_pd": v2_pd,
            "risk_score_0_100": score_info["test_scores"],
            "band": score_info["test_bands"],
        }
    )
    test_pred_df.to_parquet(V2_TEST_PREDICTIONS, index=False)
    print(f"Saved test predictions to {V2_TEST_PREDICTIONS} ({len(test_pred_df):,} rows)")

    split_rates = {
        "train": float(y_train.mean()),
        "validation": float(y_val.mean()),
        "test": float(y_test.mean()),
    }
    write_metrics_md(
        path=artifacts_dir / "metrics_v2.md",
        meta=meta_export,
        v1_metrics=v1_metrics,
        v2_metrics=v2_metrics,
        v1_ci=v1_ci,
        v2_ci=v2_ci,
        v1_calib=v1_calib,
        v2_calib=v2_calib,
        v1_bands=v1_band_stats,
        v2_bands=v2_band_stats,
        v2_deciles=eval_info["deciles_df"],
        top15=eval_info["top15_features_df"],
        segment_aucs=segment_aucs,
        interp_max_abs_diff=interp_max_abs_diff,
        shap_max_error=shap_max_error,
        cv_mean=cv_mean,
        cv_std=cv_std,
        cv_aucs=list(cv_aucs),
        split_rates=split_rates,
        best_iteration=best_iteration,
    )
    print(f"Saved metrics to {artifacts_dir / 'metrics_v2.md'}")

    print("\nVerifying load_risk_v2 / predict_pd_v2...")
    reloaded = load_risk_v2(artifacts_dir)
    reloaded_pd = predict_pd_v2(X_test, artifacts=reloaded)
    max_pd_diff = float(np.max(np.abs(v2_pd - reloaded_pd)))
    print(f"Reload vs in-memory calibrated PD max abs diff: {max_pd_diff:.8e}")
    if max_pd_diff > 1e-6:
        raise AssertionError(f"Reloaded v2 predictions differ by {max_pd_diff}")
    print("[PASS] Reloaded v2 artifacts match in-memory calibrated PD.")

    total_time = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"v2 TRAINING COMPLETED IN {total_time:.2f}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
