"""
ICVER – Train XGBoost creditworthiness models with SHAP explainers.

Generates synthetic datasets for standard informal workers and gig workers,
trains two separate XGBRegressor models to predict creditworthiness scores (0-100),
fits SHAP TreeExplainers for both, and serialises artefacts into backend/ml/ as:
  - model_standard.pkl & explainer_standard.pkl
  - model_gig.pkl & explainer_gig.pkl

Usage (from project root):
    python -m backend.ml.train_model
Or from inside backend/:
    python -m ml.train_model
"""

import os
import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import shap
import joblib

# ---------------------------------------------------------------------------
# 1. Feature Definitions
# ---------------------------------------------------------------------------
standard_features = [
    'upi_monthly_inflow',
    'weekly_txn_frequency',
    'recharge_regularity_index',
    'days_since_last_txn',
    'unique_sender_count',
    'utility_payment_streak'
]

gig_features = standard_features + [
    'gig_rating',
    'gig_hours_per_week'
]

STANDARD_FEATURES = standard_features
GIG_FEATURES = gig_features

# ---------------------------------------------------------------------------
# 2. Synthetic Data Generation
# ---------------------------------------------------------------------------
SEED = 42
N_WORKERS = 500

np.random.seed(SEED)


def generate_synthetic_dataset(n: int = N_WORKERS, is_gig: bool = False) -> pd.DataFrame:
    """Create a synthetic dataset of informal or gig workers with financial features."""

    data = pd.DataFrame({
        # Average monthly UPI inflow in INR (₹5k–₹60k range, right-skewed)
        "upi_monthly_inflow": np.round(
            np.random.lognormal(mean=9.5, sigma=0.6, size=n).clip(5_000, 60_000), 2
        ),
        # Number of UPI transactions per week (1–35)
        "weekly_txn_frequency": np.random.poisson(lam=12, size=n).clip(1, 35),
        # Recharge regularity index 0.0–1.0 (1.0 = always recharges on time)
        "recharge_regularity_index": np.round(
            np.random.beta(a=5, b=2, size=n), 4
        ),
        # Days since last UPI transaction (0–90; lower is better)
        "days_since_last_txn": np.random.exponential(scale=7, size=n).clip(0, 90).astype(int),
        # Number of unique senders/customers sending money
        "unique_sender_count": np.random.poisson(lam=15, size=n).clip(1, 100),
        # Consecutive months of on-time utility bill payments
        "utility_payment_streak": np.random.poisson(lam=6, size=n).clip(0, 24),
    })

    if is_gig:
        data["gig_rating"] = np.round(
            np.random.uniform(low=3.5, high=5.0, size=n), 2
        )
        data["gig_hours_per_week"] = np.random.poisson(lam=35, size=n).clip(5, 80)

    # ---------------------------------------------------------------------------
    # Generate target score (0–100)
    # ---------------------------------------------------------------------------
    inflow_norm = np.clip(data["upi_monthly_inflow"] / 60_000, 0, 1)
    freq_norm = np.clip(data["weekly_txn_frequency"] / 25.0, 0, 1)
    regularity_norm = data["recharge_regularity_index"]
    recency_norm = np.clip(1.0 - data["days_since_last_txn"] / 90.0, 0, 1)
    senders_norm = np.clip(data["unique_sender_count"] / 50.0, 0, 1)
    streak_norm = np.clip(data["utility_payment_streak"] / 12.0, 0, 1)

    if not is_gig:
        score = (
            25 * inflow_norm
            + 20 * freq_norm
            + 20 * regularity_norm
            + 15 * recency_norm
            + 10 * senders_norm
            + 10 * streak_norm
        )
    else:
        rating_norm = np.clip((data["gig_rating"] - 3.0) / 2.0, 0, 1)
        hours_norm = np.clip(data["gig_hours_per_week"] / 60.0, 0, 1)
        score = (
            20 * inflow_norm
            + 15 * freq_norm
            + 15 * regularity_norm
            + 10 * recency_norm
            + 10 * senders_norm
            + 10 * streak_norm
            + 10 * rating_norm
            + 10 * hours_norm
        )

    noise = np.random.normal(0, 3, size=n)
    data["score"] = np.clip(np.round(score + noise, 2), 0, 100)

    return data


# ---------------------------------------------------------------------------
# 3. Model Training & SHAP Extraction
# ---------------------------------------------------------------------------
def train_model(df: pd.DataFrame, feature_cols: list):
    """Train an XGBRegressor and fit a SHAP TreeExplainer."""

    X = df[feature_cols]
    y = df["score"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEED
    )

    model = XGBRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.9,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=SEED,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    print(f"[train] Test MAE : {mae:.3f}")
    print(f"[train] Test R²  : {r2:.4f}")

    explainer = shap.TreeExplainer(model)
    print("[train] SHAP TreeExplainer fitted successfully.")

    return model, explainer


# ---------------------------------------------------------------------------
# 4. Serialization Helpers
# ---------------------------------------------------------------------------
def _artefact_dir() -> str:
    """Return the absolute path to backend/ml/ regardless of cwd."""
    return os.path.dirname(os.path.abspath(__file__))


def save_artefacts(model, explainer, model_type: str = "standard"):
    out_dir = _artefact_dir()
    model_path = os.path.join(out_dir, f"model_{model_type}.pkl")
    explainer_path = os.path.join(out_dir, f"explainer_{model_type}.pkl")

    joblib.dump(model, model_path)
    joblib.dump(explainer, explainer_path)

    print(f"[save] Model ({model_type})     → {model_path}")
    print(f"[save] Explainer ({model_type}) → {explainer_path}")


def load_artefacts(model_type: str = "standard"):
    """Load previously saved model and explainer from backend/ml/."""
    out_dir = _artefact_dir()
    model_path = os.path.join(out_dir, f"model_{model_type}.pkl")
    explainer_path = os.path.join(out_dir, f"explainer_{model_type}.pkl")

    if not os.path.exists(model_path) or not os.path.exists(explainer_path):
        raise FileNotFoundError(
            f"ML artefacts for '{model_type}' not found in {out_dir}. "
            "Run `python -m backend.ml.train_model` first."
        )

    model = joblib.load(model_path)
    explainer = joblib.load(explainer_path)
    print(f"[load] Model ({model_type}) and SHAP explainer loaded from {out_dir}")
    return model, explainer


# ---------------------------------------------------------------------------
# 5. Main Execution
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  ICVER – Training Standard & Gig Worker XGBoost Models")
    print("=" * 60)

    # 1. Standard Worker Model
    print("\n--- Training Standard Worker Model ---")
    df_std = generate_synthetic_dataset(is_gig=False)
    print(f"[data] Generated {len(df_std)} standard worker records.")
    model_std, explainer_std = train_model(df_std, standard_features)
    save_artefacts(model_std, explainer_std, model_type="standard")

    # 2. Gig Worker Model
    print("\n--- Training Gig Worker Model ---")
    df_gig = generate_synthetic_dataset(is_gig=True)
    print(f"[data] Generated {len(df_gig)} gig worker records.")
    model_gig, explainer_gig = train_model(df_gig, gig_features)
    save_artefacts(model_gig, explainer_gig, model_type="gig")

    print("\n✅ Training complete. Saved model_standard.pkl, explainer_standard.pkl, model_gig.pkl, and explainer_gig.pkl")
