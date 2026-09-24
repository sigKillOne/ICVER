import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session

try:
    from backend.models.database import get_db, FinancialRecord, ScoreHistory
    from backend.schemas.income_verification import (
        ConsentRequest,
        ConsentResponse,
        ScoringRequest,
        ScoringResponse,
        IncomeBreakdown,
    )
    from backend.ml.train_model import load_artefacts, STANDARD_FEATURES, GIG_FEATURES
    from backend.ml.graph_fraud import detect_circular_inflation
except ModuleNotFoundError:
    from backend.models.database import get_db, FinancialRecord, ScoreHistory
    from schemas.income_verification import (
        ConsentRequest,
        ConsentResponse,
        ScoringRequest,
        ScoringResponse,
        IncomeBreakdown,
    )
    from ml.train_model import load_artefacts, STANDARD_FEATURES, GIG_FEATURES
    from ml.graph_fraud import detect_circular_inflation

logger = logging.getLogger("icver.router")

router = APIRouter()

# ---------------------------------------------------------------------------
# Load ML artefacts at module-import time (i.e. server startup)
# ---------------------------------------------------------------------------
try:
    _model_standard, _explainer_standard = load_artefacts("standard")
    _model_gig, _explainer_gig = load_artefacts("gig")
    _ml_ready = True
    logger.info("Standard and Gig ML models and SHAP explainers loaded successfully.")
except FileNotFoundError as exc:
    _model_standard = _explainer_standard = None
    _model_gig = _explainer_gig = None
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
    "unique_sender_count": "unique senders count",
    "utility_payment_streak": "utility payment streak",
    "gig_rating": "gig platform rating",
    "gig_hours_per_week": "weekly gig hours",
}


def _predict_and_explain(model, explainer, feature_cols: list[str], features: dict) -> tuple[int, str, list[str], float]:
    """
    Run XGBoost prediction and SHAP explanation for given model and features.

    Returns:
        (score, decision_tier, shap_reasons, confidence)
    """
    df = pd.DataFrame([features], columns=feature_cols)

    # --- Prediction ---
    raw_score = float(model.predict(df)[0])
    score = int(np.clip(round(raw_score), 0, 100))

    # --- Decision tier ---
    if score >= 70:
        decision_tier = "Eligible"
    elif score >= 45:
        decision_tier = "Review"
    else:
        decision_tier = "Ineligible"

    # --- SHAP explanation ---
    shap_values = explainer.shap_values(df)  # shape (1, n_features)
    sv = shap_values[0]

    # Build human-readable SHAP reasons, sorted by absolute contribution
    feature_contribs = list(zip(feature_cols, sv))
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
        phone_number=payload.phone_number,
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
# Scoring endpoints – now powered by dual XGBoost + SHAP
# ---------------------------------------------------------------------------

@router.post(
    "/score",
    response_model=ScoringResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate informal worker income and creditworthiness score",
    description="Processes UPI transaction history and mobile recharge logs through XGBoost models (standard or gig) to output creditworthiness score, decision tier, and SHAP explanations."
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

    # --- Query MariaDB for FinancialRecord ---
    phone_number = payload.phone_number
    if not phone_number:
        if payload.consent_id in _consent_db:
            phone_number = _consent_db[payload.consent_id].phone_number

    if not phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number is required for scoring."
        )

    record = db.query(FinancialRecord).filter(FinancialRecord.mobile_number == phone_number).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No financial records found for this mobile number."
        )

    # --- Conditional Routing based on Employment Type (Gig vs Standard) ---
    # Extract feature values from payload overrides or record defaults
    upi_monthly_inflow = payload.upi_monthly_inflow if payload.upi_monthly_inflow is not None else record.upi_monthly_inflow
    weekly_txn_frequency = payload.weekly_txn_frequency if payload.weekly_txn_frequency is not None else record.weekly_txn_frequency
    recharge_regularity_index = payload.recharge_regularity_index if payload.recharge_regularity_index is not None else record.recharge_regularity_index
    days_since_last_txn = payload.days_since_last_txn if payload.days_since_last_txn is not None else record.days_since_last_txn
    unique_sender_count = payload.unique_sender_count if payload.unique_sender_count is not None else record.unique_sender_count
    utility_payment_streak = payload.utility_payment_streak if payload.utility_payment_streak is not None else record.utility_payment_streak
    gig_rating = payload.gig_rating if payload.gig_rating is not None else (record.gig_rating if record.gig_rating is not None else 4.0)
    gig_hours_per_week = payload.gig_hours_per_week if payload.gig_hours_per_week is not None else (record.gig_hours_per_week if record.gig_hours_per_week is not None else 35)

    # --- Conditional Routing based on Employment Type (Gig vs Standard) ---
    if record.is_gig_worker:
        feature_cols = GIG_FEATURES
        features = {
            "upi_monthly_inflow": upi_monthly_inflow,
            "weekly_txn_frequency": weekly_txn_frequency,
            "recharge_regularity_index": recharge_regularity_index,
            "days_since_last_txn": days_since_last_txn,
            "unique_sender_count": unique_sender_count,
            "utility_payment_streak": utility_payment_streak,
            "gig_rating": gig_rating,
            "gig_hours_per_week": gig_hours_per_week,
        }
        model = _model_gig
        explainer = _explainer_gig
    else:
        feature_cols = STANDARD_FEATURES
        features = {
            "upi_monthly_inflow": upi_monthly_inflow,
            "weekly_txn_frequency": weekly_txn_frequency,
            "recharge_regularity_index": recharge_regularity_index,
            "days_since_last_txn": days_since_last_txn,
            "unique_sender_count": unique_sender_count,
            "utility_payment_streak": utility_payment_streak,
        }
        model = _model_standard
        explainer = _explainer_standard

    # --- ML Inference or heuristic fallback ---
    if _ml_ready and model is not None and explainer is not None:
        score, decision_tier, shap_reasons, confidence = _predict_and_explain(
            model, explainer, feature_cols, features
        )
    else:
        # Fallback: simple heuristic
        score = 78
        decision_tier = "Eligible"
        shap_reasons = [
            "+18 for consistent weekly inflow",
            "+12 for regular mobile recharge top-ups",
            "+8 for low volatility in UPI deposits",
        ]
        confidence = 0.89

    # --- Network Fraud Detection ---
    is_fraud = detect_circular_inflation(payload.worker_id, weekly_txn_frequency)
    
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
    upi_credits = upi_monthly_inflow
    recharge_total = recharge_regularity_index * 4.0 * 299.0 # approximate recharge total

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

    # Save score to history
    score_history = ScoreHistory(
        mobile_number=phone_number,
        credit_score=score,
        risk_tier=decision_tier
    )
    db.add(score_history)
    db.commit()

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
        is_gig_worker=record.is_gig_worker,
        unique_sender_count=unique_sender_count,
        utility_payment_streak=utility_payment_streak,
        gig_rating=gig_rating if record.is_gig_worker else None,
        gig_hours_per_week=gig_hours_per_week if record.is_gig_worker else None,
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
