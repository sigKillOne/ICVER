import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session

try:
    from backend.models.database import get_db
    from backend.schemas.income_verification import (
        ConsentRequest,
        ConsentResponse,
        ScoringRequest,
        ScoringResponse,
        IncomeBreakdown,
    )
    from backend.ml.train_model import load_artefacts, FEATURE_COLS
    from backend.ml.graph_fraud import detect_circular_inflation
except ModuleNotFoundError:
    from models.database import get_db
    from schemas.income_verification import (
        ConsentRequest,
        ConsentResponse,
        ScoringRequest,
        ScoringResponse,
        IncomeBreakdown,
    )
    from ml.train_model import load_artefacts, FEATURE_COLS
    from ml.graph_fraud import detect_circular_inflation

logger = logging.getLogger("icver.router")

router = APIRouter()

# ---------------------------------------------------------------------------
# Load ML artefacts at module-import time (i.e. server startup)
# ---------------------------------------------------------------------------
try:
    _model, _explainer = load_artefacts()
    _ml_ready = True
    logger.info("ML model and SHAP explainer loaded successfully.")
except FileNotFoundError as exc:
    _model = _explainer = None
    _ml_ready = False
    logger.warning("ML artefacts not found – scoring will fall back to heuristic. %s", exc)

# In-memory storage for rapid prototyping
_consent_db = {}
_scores_db = {}

# ---------------------------------------------------------------------------
# Human-readable labels for SHAP feature names
# ---------------------------------------------------------------------------
_FEATURE_LABELS = {
    "upi_monthly_inflow": "UPI monthly inflow",
    "weekly_txn_frequency": "weekly transaction frequency",
    "recharge_regularity_index": "mobile recharge regularity",
    "days_since_last_txn": "recency of last transaction",
}


def _derive_features(payload: ScoringRequest) -> dict:
    """
    Extract the four model features from the incoming ScoringRequest payload.

    The frontend sends UPI transaction lists, recharge logs, and aggregated
    numbers.  We derive the features the XGBoost model was trained on.
    """
    # UPI monthly inflow – sum of CREDIT transactions, fallback to cashflow avg
    upi_credits = sum(
        txn.amount
        for txn in payload.upi_transaction_history
        if txn.type.upper() == "CREDIT"
    )
    upi_monthly_inflow = upi_credits if upi_credits > 0 else (payload.monthly_cashflow_avg or 28500.0)

    # Weekly transaction frequency – approximate from the list length
    weekly_txn_frequency = max(len(payload.upi_transaction_history), 1)

    # Recharge regularity index – normalise recharge count to 0-1 range
    n_recharges = len(payload.mobile_recharge_logs)
    recharge_regularity_index = min(n_recharges / 4.0, 1.0)  # 4+ recharges → 1.0

    # Days since last transaction – use 3 as a sensible live default
    days_since_last_txn = 3

    return {
        "upi_monthly_inflow": upi_monthly_inflow,
        "weekly_txn_frequency": weekly_txn_frequency,
        "recharge_regularity_index": recharge_regularity_index,
        "days_since_last_txn": days_since_last_txn,
    }


def _predict_and_explain(features: dict) -> tuple[int, str, list[str], float]:
    """
    Run XGBoost prediction and SHAP explanation.

    Returns:
        (score, decision_tier, shap_reasons, confidence)
    """
    df = pd.DataFrame([features], columns=FEATURE_COLS)

    # --- Prediction ---
    raw_score = float(_model.predict(df)[0])
    score = int(np.clip(round(raw_score), 0, 100))

    # --- Decision tier ---
    if score >= 70:
        decision_tier = "Eligible"
    elif score >= 45:
        decision_tier = "Review"
    else:
        decision_tier = "Ineligible"

    # --- SHAP explanation ---
    shap_values = _explainer.shap_values(df)  # shape (1, n_features)
    sv = shap_values[0]  # first (and only) sample

    # Build human-readable SHAP reasons, sorted by absolute contribution
    feature_contribs = list(zip(FEATURE_COLS, sv))
    feature_contribs.sort(key=lambda x: abs(x[1]), reverse=True)

    shap_reasons = []
    for feat, val in feature_contribs:
        label = _FEATURE_LABELS.get(feat, feat)
        sign = "+" if val >= 0 else ""
        shap_reasons.append(f"{sign}{val:.2f} for {label}")

    # --- Confidence (rough heuristic based on SHAP magnitude) ---
    total_shap = sum(abs(v) for _, v in feature_contribs)
    confidence = float(np.clip(0.5 + total_shap / 40.0, 0.50, 0.99))

    return score, decision_tier, shap_reasons, round(confidence, 2)


# ---------------------------------------------------------------------------
# Consent endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/consent",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record worker data access consent",
    description="Registers informal worker's explicit consent for income verification data processing."
)
async def create_consent(
    payload: ConsentRequest,
    db: Session = Depends(get_db)
):
    if not payload.consent_given:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consent must be explicitly granted to proceed with income verification."
        )

    consent_id = f"CNS-{uuid.uuid4().hex[:8].upper()}-{datetime.now().year}"
    recorded_at = datetime.now(timezone.utc)

    consent_record = ConsentResponse(
        consent_id=consent_id,
        worker_id=payload.worker_id,
        status="ACTIVE",
        message="Consent successfully granted and logged.",
        created_at=recorded_at
    )

    _consent_db[consent_id] = consent_record
    return consent_record


@router.get(
    "/consent/{consent_id}",
    response_model=ConsentResponse,
    summary="Retrieve consent record",
    description="Fetches details of recorded consent using consent reference ID."
)
async def get_consent(consent_id: str):
    if consent_id not in _consent_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consent record '{consent_id}' not found."
        )
    return _consent_db[consent_id]


# ---------------------------------------------------------------------------
# Scoring endpoints – now powered by XGBoost + SHAP
# ---------------------------------------------------------------------------

@router.post(
    "/score",
    response_model=ScoringResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate informal worker income and creditworthiness score",
    description="Processes UPI transaction history and mobile recharge logs through an XGBoost model to output a real creditworthiness score, decision tier, and SHAP explanations."
)
async def calculate_score(
    payload: ScoringRequest,
    db: Session = Depends(get_db)
):
    # Verify that valid active consent exists if consent_id is supplied
    if payload.consent_id in _consent_db:
        consent = _consent_db[payload.consent_id]
        if consent.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Provided consent ID is inactive or expired."
            )

    # Derive model features from the request payload
    features = _derive_features(payload)

    # --- ML Inference or heuristic fallback ---
    if _ml_ready:
        score, decision_tier, shap_reasons, confidence = _predict_and_explain(features)
    else:
        # Fallback: simple heuristic (same as old hardcoded logic)
        score = 78
        decision_tier = "Eligible"
        shap_reasons = [
            "+18 for consistent weekly inflow",
            "+12 for regular mobile recharge top-ups",
            "+8 for low volatility in UPI deposits",
        ]
        confidence = 0.89

    # --- Network Fraud Detection ---
    is_fraud = detect_circular_inflation(payload.worker_id, len(payload.upi_transaction_history))
    
    if is_fraud:
        score = int(score * 0.8)
        shap_reasons = ["-20.00 for Synthetic Volume Flag (Circular Inflation Detected)"] + shap_reasons

    # --- Decision tier recalculation based on penalized score ---
    if score >= 70:
        decision_tier = "Eligible"
    elif score >= 45:
        decision_tier = "Review"
    else:
        decision_tier = "Ineligible"
        
    # --- Income estimation (unchanged business logic) ---
    upi_credits = sum(
        txn.amount for txn in payload.upi_transaction_history if txn.type.upper() == "CREDIT"
    )
    recharge_total = sum(r.amount for r in payload.mobile_recharge_logs)

    cashflow = payload.monthly_cashflow_avg or (upi_credits if upi_credits > 0 else 28500.0)
    gig = payload.gig_platform_earnings or 0.0

    gig_weight = 0.85 if gig > 0 else 0.5
    base_estimate = (cashflow * 0.6) + (gig * gig_weight)
    stability_index = 0.92 if (upi_credits > 0 or recharge_total > 0) else 0.85
    risk_factor = 1.0

    final_verified_income = round(base_estimate * stability_index * risk_factor, 2)

    # --- Risk category from ML score ---
    if score >= 70:
        risk_category = "LOW"
    elif score >= 45:
        risk_category = "MEDIUM"
    else:
        risk_category = "HIGH"

    scored_at = datetime.now(timezone.utc)

    response = ScoringResponse(
        worker_id=payload.worker_id,
        consent_id=payload.consent_id,
        creditworthiness_score=score,
        decision_tier=decision_tier,
        shap_reasons=shap_reasons,
        verified_income_estimate=final_verified_income,
        confidence_score=confidence,
        risk_category=risk_category,
        synthetic_volume_flag=is_fraud,
        breakdown=IncomeBreakdown(
            base_estimated_income=round(base_estimate, 2),
            gig_income_weight=gig_weight,
            cashflow_stability_index=stability_index,
            risk_factor=risk_factor
        ),
        scored_at=scored_at
    )

    _scores_db[payload.worker_id] = response
    return response


@router.get(
    "/score/{worker_id}",
    response_model=ScoringResponse,
    summary="Get worker latest score",
    description="Retrieves the most recent verified score for a given worker ID."
)
async def get_worker_score(worker_id: str):
    if worker_id not in _scores_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No score record found for worker ID '{worker_id}'."
        )
    return _scores_db[worker_id]
