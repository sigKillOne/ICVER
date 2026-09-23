"""
ICVER – Train XGBoost creditworthiness model with SHAP explainer.

Generates a synthetic dataset of 500 informal workers with realistic
financial features, trains an XGBRegressor to predict a creditworthiness
score between 0 and 100, fits a SHAP TreeExplainer, and serialises both
artifacts into backend/ml/ as model.pkl and explainer.pkl.

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
import shap
import joblib

# ---------------------------------------------------------------------------
# 1. Synthetic data generation
# ---------------------------------------------------------------------------
SEED = 42
N_WORKERS = 500

np.random.seed(SEED)


def generate_synthetic_dataset(n: int = N_WORKERS) -> pd.DataFrame:
    """Create a synthetic dataset of informal workers with financial features."""

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
    })

    # ---------------------------------------------------------------------------
    # 2. Generate a synthetic target score (0–100)
    # ---------------------------------------------------------------------------
    # The formula loosely mirrors how a real underwriting model would weigh
    # these features – high inflow, high frequency, high regularity, and low
    # recency all drive a higher score.
    # Each component is normalised to contribute up to its weight in points.
    inflow_norm = np.clip(data["upi_monthly_inflow"] / 60_000, 0, 1)      # 0-1
    freq_norm = np.clip(data["weekly_txn_frequency"] / 25.0, 0, 1)         # 0-1
    regularity_norm = data["recharge_regularity_index"]                     # already 0-1
    recency_norm = np.clip(1.0 - data["days_since_last_txn"] / 90.0, 0, 1) # 0-1

    score = (
        30 * inflow_norm
        + 25 * freq_norm
        + 25 * regularity_norm
        + 20 * recency_norm
    )
    # Add realistic noise and clip to 0–100
    noise = np.random.normal(0, 3, size=n)
    data["score"] = np.clip(np.round(score + noise, 2), 0, 100)

    return data


# ---------------------------------------------------------------------------
# 3. Training pipeline
# ---------------------------------------------------------------------------
FEATURE_COLS = [
    "upi_monthly_inflow",
    "weekly_txn_frequency",
    "recharge_regularity_index",
    "days_since_last_txn",
]


def train_model(df: pd.DataFrame):
    """Train an XGBRegressor and fit a SHAP TreeExplainer."""

    X = df[FEATURE_COLS]
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

    # Evaluate on test set
    from sklearn.metrics import mean_absolute_error, r2_score

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    print(f"[train] Test MAE : {mae:.3f}")
    print(f"[train] Test R²  : {r2:.4f}")

    # Fit SHAP explainer
    explainer = shap.TreeExplainer(model)
    print("[train] SHAP TreeExplainer fitted successfully.")

    return model, explainer


# ---------------------------------------------------------------------------
# 4. Serialisation helpers
# ---------------------------------------------------------------------------
def _artefact_dir() -> str:
    """Return the absolute path to backend/ml/ regardless of cwd."""
    return os.path.dirname(os.path.abspath(__file__))


def save_artefacts(model, explainer):
    out_dir = _artefact_dir()
    model_path = os.path.join(out_dir, "model.pkl")
    explainer_path = os.path.join(out_dir, "explainer.pkl")

    joblib.dump(model, model_path)
    joblib.dump(explainer, explainer_path)

    print(f"[save] Model     → {model_path}")
    print(f"[save] Explainer → {explainer_path}")


def load_artefacts():
    """Load previously saved model and explainer from backend/ml/."""
    out_dir = _artefact_dir()
    model_path = os.path.join(out_dir, "model.pkl")
    explainer_path = os.path.join(out_dir, "explainer.pkl")

    if not os.path.exists(model_path) or not os.path.exists(explainer_path):
        raise FileNotFoundError(
            f"ML artefacts not found in {out_dir}. "
            "Run `python -m backend.ml.train_model` first."
        )

    model = joblib.load(model_path)
    explainer = joblib.load(explainer_path)
    print(f"[load] Model and SHAP explainer loaded from {out_dir}")
    return model, explainer


# ---------------------------------------------------------------------------
# 5. Entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  ICVER – Training XGBoost Creditworthiness Model")
    print("=" * 60)

    df = generate_synthetic_dataset()
    print(f"[data] Generated {len(df)} synthetic worker records.")
    print(df.describe().round(2).to_string())
    print()

    model, explainer = train_model(df)
    save_artefacts(model, explainer)

    print()
    print("✅  Training complete.  model.pkl & explainer.pkl saved.")
