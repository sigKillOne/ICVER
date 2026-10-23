import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session

try:
    from backend.core.config import settings
    from backend.core.phone import normalize_phone
    from backend.models.database import get_db, FinancialRecord, ScoreHistory, WorkerConsent
    from backend.schemas.income_verification import (
        ConsentRequest,
        ConsentResponse,
        ScoringRequest,
        ScoringResponse,
        IncomeBreakdown,
    )
    from backend.ml.train_model import load_artefacts, STANDARD_FEATURES, GIG_FEATURES
    from backend.ml.graph_fraud import detect_circular_inflation
    from backend.core.parser import extract_upi_inflow
except ModuleNotFoundError:
    from core.config import settings
    from core.phone import normalize_phone
    from models.database import get_db, FinancialRecord, ScoreHistory, WorkerConsent
    from schemas.income_verification import (
        ConsentRequest,
        ConsentResponse,
        ScoringRequest,
        ScoringResponse,
        IncomeBreakdown,
    )
    from ml.train_model import load_artefacts, STANDARD_FEATURES, GIG_FEATURES
    from ml.graph_fraud import detect_circular_inflation
    from core.parser import extract_upi_inflow

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
    logger.warning("ML artefacts not found – scoring will require loaded models. %s", exc)


def is_ml_ready() -> bool:
    """Return whether ML models and explainers are loaded and ready."""
    return _ml_ready and _model_standard is not None and _model_gig is not None


def is_standard_model_ready() -> bool:
    return _model_standard is not None and _explainer_standard is not None


def is_gig_model_ready() -> bool:
    return _model_gig is not None and _explainer_gig is not None


# In-memory storage for rapid score retrieval by worker_id
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
# Consent endpoints (Persisted in Database)
# ---------------------------------------------------------------------------

@router.post(
    "/consent",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record worker data access consent",
    description="Registers informal worker's explicit consent for income verification data processing."
)
def create_consent(
    payload: ConsentRequest,
    db: Session = Depends(get_db)
):
    if not payload.consent_given:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consent must be explicitly granted to proceed with income verification."
        )

    try:
        norm_phone = normalize_phone(payload.phone_number)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid phone number: {exc}"
        )

    consent_id = f"CNS-{uuid.uuid4().hex[:8].upper()}-{datetime.now().year}"
    recorded_at = datetime.now(timezone.utc)

    db_consent = WorkerConsent(
        id=consent_id,
        worker_id=payload.worker_id,
        phone_number=norm_phone,
        scope=payload.consent_purpose,
        granted_at=recorded_at,
        expires_at=None,
        revoked_at=None,
    )
    db.add(db_consent)
    db.commit()
    db.refresh(db_consent)

    return ConsentResponse(
        consent_id=db_consent.id,
        worker_id=db_consent.worker_id,
        phone_number=db_consent.phone_number,
        status="ACTIVE",
        message="Consent successfully granted and logged.",
        created_at=db_consent.granted_at
    )


@router.get(
    "/consent/{consent_id}",
    response_model=ConsentResponse,
    summary="Retrieve consent record",
    description="Fetches details of recorded consent using consent reference ID."
)
def get_consent(
    consent_id: str,
    db: Session = Depends(get_db)
):
    consent = db.query(WorkerConsent).filter(WorkerConsent.id == consent_id).first()
    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consent record '{consent_id}' not found."
        )

    now_utc = datetime.now(timezone.utc)
    if consent.revoked_at is not None:
        status_str = "REVOKED"
    elif consent.expires_at is not None:
        exp = consent.expires_at if consent.expires_at.tzinfo else consent.expires_at.replace(tzinfo=timezone.utc)
        status_str = "EXPIRED" if exp < now_utc else "ACTIVE"
    else:
        status_str = "ACTIVE"

    return ConsentResponse(
        consent_id=consent.id,
        worker_id=consent.worker_id,
        phone_number=consent.phone_number,
        status=status_str,
        message=f"Consent record is {status_str.lower()}.",
        created_at=consent.granted_at
    )


@router.post(
    "/consent/{consent_id}/revoke",
    response_model=ConsentResponse,
    summary="Revoke worker data access consent",
    description="Revokes previously granted consent, blocking subsequent score requests."
)
def revoke_consent(
    consent_id: str,
    db: Session = Depends(get_db)
):
    consent = db.query(WorkerConsent).filter(WorkerConsent.id == consent_id).first()
    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consent record '{consent_id}' not found."
        )

    if consent.revoked_at is None:
        consent.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(consent)

    return ConsentResponse(
        consent_id=consent.id,
        worker_id=consent.worker_id,
        phone_number=consent.phone_number,
        status="REVOKED",
        message="Consent revoked successfully.",
        created_at=consent.granted_at
    )


# ---------------------------------------------------------------------------
# Scoring endpoints – powered by dual XGBoost + SHAP
# ---------------------------------------------------------------------------

@router.post(
    "/score",
    response_model=ScoringResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate informal worker income and creditworthiness score",
    description="Processes UPI transaction history and mobile recharge logs through XGBoost models (standard or gig) to output creditworthiness score, decision tier, and SHAP explanations."
)
def calculate_score(
    payload: ScoringRequest,
    db: Session = Depends(get_db)
):
    # --- 1. Consent Verification ---
    if not payload.consent_id or not payload.consent_id.strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing consent_id. Valid active worker consent is required for scoring."
        )

    consent = db.query(WorkerConsent).filter(WorkerConsent.id == payload.consent_id).first()
    if not consent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown consent_id '{payload.consent_id}'. Consent record not found."
        )

    if consent.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Consent has been revoked."
        )

    now_utc = datetime.now(timezone.utc)
    if consent.expires_at is not None:
        exp = consent.expires_at if consent.expires_at.tzinfo else consent.expires_at.replace(tzinfo=timezone.utc)
        if exp < now_utc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Consent has expired."
            )

    if consent.worker_id != payload.worker_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Consent record belongs to a different worker ID."
        )

    # Check phone number against consent
    if payload.phone_number:
        try:
            req_phone = normalize_phone(payload.phone_number)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid phone_number in request: {exc}"
            )
        if req_phone != consent.phone_number:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Consent phone number does not match requested phone number."
            )
        phone_number = req_phone
    else:
        phone_number = consent.phone_number

    # --- 2. Query FinancialRecord ---
    record = db.query(FinancialRecord).filter(
        (FinancialRecord.mobile_number == phone_number) |
        (FinancialRecord.mobile_number == phone_number[-10:])
    ).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No financial records found for this mobile number."
        )

    # --- 3. Feature extraction and overrides handling ---
    allow_overrides = getattr(settings, "ALLOW_FEATURE_OVERRIDES", False)

    if allow_overrides and payload.upi_monthly_inflow is not None:
        upi_monthly_inflow = float(payload.upi_monthly_inflow)
    else:
        upi_monthly_inflow = float(record.upi_monthly_inflow or 0.0)

    monthly_household_income = float(record.monthly_household_income or 0.0)

    # Unstructured Data Ingestion: Parse Raw SMS Transaction Logs
    if payload.sms_log:
        sms_inflow = extract_upi_inflow(payload.sms_log)
        upi_monthly_inflow += sms_inflow
        monthly_household_income += sms_inflow
        logger.info("Unstructured SMS ingestion extracted ₹%.2f from SMS log", sms_inflow)

    if allow_overrides and payload.weekly_txn_frequency is not None:
        weekly_txn_frequency = payload.weekly_txn_frequency
    else:
        weekly_txn_frequency = record.weekly_txn_frequency

    if allow_overrides and payload.recharge_regularity_index is not None:
        recharge_regularity_index = payload.recharge_regularity_index
    else:
        recharge_regularity_index = record.recharge_regularity_index

    if allow_overrides and payload.days_since_last_txn is not None:
        days_since_last_txn = payload.days_since_last_txn
    else:
        days_since_last_txn = record.days_since_last_txn

    if allow_overrides and payload.unique_sender_count is not None:
        unique_sender_count = payload.unique_sender_count
    else:
        unique_sender_count = record.unique_sender_count

    if allow_overrides and payload.utility_payment_streak is not None:
        utility_payment_streak = payload.utility_payment_streak
    else:
        utility_payment_streak = record.utility_payment_streak

    if allow_overrides and payload.gig_rating is not None:
        gig_rating = payload.gig_rating
    else:
        gig_rating = record.gig_rating if record.gig_rating is not None else 4.0

    if allow_overrides and payload.gig_hours_per_week is not None:
        gig_hours_per_week = payload.gig_hours_per_week
    else:
        gig_hours_per_week = record.gig_hours_per_week if record.gig_hours_per_week is not None else 35

    # --- 4. Model Selection ---
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

    # --- 5. ML Inference (HTTP 503 if unavailable) ---
    if not _ml_ready or model is None or explainer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML scoring models are unavailable or failed to load. Scoring cannot proceed."
        )

    score, decision_tier, shap_reasons, confidence = _predict_and_explain(
        model, explainer, feature_cols, features
    )

    # --- 6. Network Fraud Detection ---
    is_fraud = detect_circular_inflation(payload.worker_id, weekly_txn_frequency)
    if is_fraud:
        score = int(score * 0.8)
        shap_reasons = ["-20.00 for Synthetic Volume Flag (Circular Inflation Detected)"] + shap_reasons

    # Recalculate decision tier if penalized
    if score >= 70:
        decision_tier = "Eligible"
    elif score >= 45:
        decision_tier = "Review"
    else:
        decision_tier = "Ineligible"

    # --- 7. RBI FOIR Guardrail (MFI Regulatory Compliance) ---
    effective_income = monthly_household_income if monthly_household_income > 0 else 1.0
    monthly_business_expenses = record.monthly_business_expenses or 0.0
    monthly_household_expenses = record.monthly_household_expenses or 0.0
    existing_monthly_emi = record.existing_monthly_emi or 0.0
    proposed_loan_emi = record.proposed_loan_emi or 0.0

    foir_percentage = round(
        ((existing_monthly_emi + proposed_loan_emi) / effective_income) * 100, 2
    )
    available_surplus = round(
        monthly_household_income
        - (monthly_business_expenses + monthly_household_expenses + existing_monthly_emi + proposed_loan_emi),
        2,
    )
    rbi_max_cap = 50.0

    if foir_percentage > rbi_max_cap:
        rbi_compliant = False
        decision_tier = "High Risk"
        shap_reasons = [
            f"RBI Guardrail Violation: Household Debt Burden exceeds 50% Cap (FOIR = {foir_percentage:.1f}%)"
        ] + shap_reasons
    else:
        rbi_compliant = True

    # --- 8. Income estimation (Fall back to database record, treat missing as missing) ---
    if payload.monthly_cashflow_avg is not None:
        cashflow = payload.monthly_cashflow_avg
    elif getattr(record, "monthly_cashflow_avg", None) is not None:
        cashflow = record.monthly_cashflow_avg
    else:
        cashflow = upi_monthly_inflow if upi_monthly_inflow > 0 else None

    if payload.gig_platform_earnings is not None:
        gig = payload.gig_platform_earnings
    elif getattr(record, "gig_platform_earnings", None) is not None:
        gig = record.gig_platform_earnings
    else:
        gig = None

    # For non-gig workers with no explicit gig earnings, gig income is None
    if not record.is_gig_worker and payload.gig_platform_earnings is None and getattr(record, "gig_platform_earnings", None) is None:
        gig = None

    cashflow_val = cashflow if cashflow is not None else 0.0
    gig_val = gig if gig is not None else 0.0

    gig_weight = 0.85 if (record.is_gig_worker or gig_val > 0) else 0.5
    base_estimate = (cashflow_val * 0.6) + (gig_val * gig_weight)
    recharge_total = (recharge_regularity_index or 0.0) * 4.0 * 299.0
    stability_index = 0.92 if (upi_monthly_inflow > 0 or recharge_total > 0) else 0.85
    risk_factor = 1.0

    final_verified_income = round(base_estimate * stability_index * risk_factor, 2)

    # --- 9. Risk category from ML score ---
    if score >= 70:
        risk_category = "LOW"
    elif score >= 45:
        risk_category = "MEDIUM"
    else:
        risk_category = "HIGH"

    scored_at = datetime.now(timezone.utc)

    # Save score to history
    audit_tier = (
        f"{decision_tier} | FOIR={foir_percentage:.1f}% | RBI={'OK' if rbi_compliant else 'VIOLATION'}"
    )
    score_history = ScoreHistory(
        mobile_number=phone_number,
        credit_score=score,
        risk_tier=audit_tier
    )
    db.add(score_history)
    db.commit()

    if not rbi_compliant:
        risk_category = "HIGH"

    # --- 10. Dynamic Risk-Based Pricing Engine ---
    if not rbi_compliant or decision_tier == "High Risk" or risk_category == "HIGH":
        interest_rate_apr = 0.0
        max_loan_limit = 0.0
        estimated_emi = 0.0
    else:
        if score >= 80:
            interest_rate_apr = 12.5
        elif score >= 60:
            interest_rate_apr = 18.0
        else:
            interest_rate_apr = 24.0

        max_loan_limit = round(max(0.0, available_surplus * 12.0), 2)

        # Baseline ₹50,000 loan over 12 months EMI calculation
        p = 50000.0
        n = 12
        r = (interest_rate_apr / 100.0) / 12.0
        if r > 0:
            numerator = p * r * ((1.0 + r) ** n)
            denominator = ((1.0 + r) ** n) - 1.0
            estimated_emi = round(numerator / denominator, 2)
        else:
            estimated_emi = 0.0

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
        scored_at=scored_at,
        foir_percentage=foir_percentage,
        available_surplus=available_surplus,
        rbi_compliant=rbi_compliant,
        rbi_max_cap=rbi_max_cap,
        interest_rate_apr=interest_rate_apr,
        max_loan_limit=max_loan_limit,
        estimated_emi=estimated_emi,
    )

    _scores_db[payload.worker_id] = response
    return response


@router.get(
    "/score/{worker_id}",
    response_model=ScoringResponse,
    summary="Get worker latest score",
    description="Retrieves the most recent verified score for a given worker ID."
)
def get_worker_score(worker_id: str):
    if worker_id not in _scores_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No score record found for worker ID '{worker_id}'."
        )
    return _scores_db[worker_id]
