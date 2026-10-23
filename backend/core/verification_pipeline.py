"""Orchestration for the /verify income-verification and decision-support flow."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

try:
    from backend.core import risk_v2
    from backend.core.config import settings
    from backend.core.consent import validate_consent
    from backend.core.income_verification import EvidenceInput, VerificationResult, verify
    from backend.core.phone import normalize_phone
    from backend.core.recommendation import recommend
    from backend.models.database import (
        FinancialRecord,
        VerificationResultRecord,
        WorkerMonthlyEvidence,
        WorkerRiskProfile,
    )
    from backend.schemas.verification import (
        AffordabilitySummary,
        EvidenceSummary,
        ExpensesSummary,
        IncomeSummary,
        RecommendationSummary,
        RiskFactor,
        RiskSignalSummary,
        VerifyRequest,
        VerifyResponse,
    )
except ModuleNotFoundError:  # pragma: no cover - flat module execution fallback
    from core import risk_v2
    from core.config import settings
    from core.consent import validate_consent
    from core.income_verification import EvidenceInput, VerificationResult, verify
    from core.phone import normalize_phone
    from core.recommendation import recommend
    from models.database import (
        FinancialRecord,
        VerificationResultRecord,
        WorkerMonthlyEvidence,
        WorkerRiskProfile,
    )
    from schemas.verification import (
        AffordabilitySummary,
        EvidenceSummary,
        ExpensesSummary,
        IncomeSummary,
        RecommendationSummary,
        RiskFactor,
        RiskSignalSummary,
        VerifyRequest,
        VerifyResponse,
    )

ENGINE_VERSION = "income-verification-engine-v1"  # Module path/version of the engine.
EXISTING_EMI_KEY = "existing_emi"
RISK_TOP_N = 3
INDIA_PHONE_LAST_DIGITS = 10  # Canonical Indian numbers are +91 plus ten digits.
VERIFICATION_ID_BYTES = 12
FOIR_DECIMALS = 4
MONEY_DECIMALS = 2
RISK_UNAVAILABLE_REASON = (
    "No repayment-risk profile is available for this worker, so the reference-population "
    "risk signal cannot be computed."
)
SMS_IGNORED_NO_DATES = (
    "SMS log ignored: the parser can extract per-message amounts but not transaction "
    "dates, so credits cannot be grouped by calendar month without inventing data."
)
SMS_PROVENANCE_IGNORED = "ignored_no_dates"
SMS_PROVENANCE_NOT_PROVIDED = "not_provided"
SMS_PROVENANCE_CLIENT = "client_supplied_unverified"
UPI_PROVENANCE_DATABASE = "database"
FALLBACK_EVIDENCE_REASON = (
    "No monthly UPI evidence rows were found; a single labelled fallback month was "
    "derived from the worker's database aggregate, which triggers the engine's "
    "SHORT_HISTORY caution."
)
REFERENCE_POPULATION_NOTE = (
    "Reference-population signal calibrated to the Home Credit Default Risk dataset "
    "(about 8% default rate). This is not this individual's probability of default. "
    "The model was validated on applicants with credit history; its accuracy for "
    "profiles with no credit history is unproven."
)


def compute_affordability(
    evidence_result: VerificationResult,
    monthly_outgoings: Optional[Dict[str, float]],
    proposed_emi: Optional[float],
    foir_cap: float,
) -> Dict[str, Any]:
    """Compute conservative affordability from verified income, never stated income.

    Existing EMI may already be included inside the engine's expense estimate. Taking the
    minimum of the FOIR headroom and the conservative surplus is deliberately the stricter
    of the two constraints and avoids double counting the same obligation twice.
    """
    conservative_income = evidence_result.income_low
    outgoings = monthly_outgoings or {}
    existing_emi = float(outgoings.get(EXISTING_EMI_KEY, 0.0) or 0.0)

    if conservative_income is None or conservative_income <= 0:
        return {
            "foir_current": None,
            "foir_with_proposed": None,
            "foir_cap": float(foir_cap),
            "max_affordable_emi": None,
            "existing_emi": existing_emi,
            "proposed_emi": proposed_emi,
        }

    foir_current = existing_emi / conservative_income
    foir_with_proposed = (
        (existing_emi + float(proposed_emi)) / conservative_income
        if proposed_emi is not None
        else None
    )

    surplus = evidence_result.monthly_surplus_conservative
    surplus_value = float(surplus) if surplus is not None else 0.0
    foir_headroom = float(foir_cap) * conservative_income - existing_emi
    max_affordable_emi = max(0.0, min(foir_headroom, surplus_value))

    return {
        "foir_current": round(float(foir_current), FOIR_DECIMALS),
        "foir_with_proposed": (
            round(float(foir_with_proposed), FOIR_DECIMALS)
            if foir_with_proposed is not None
            else None
        ),
        "foir_cap": float(foir_cap),
        "max_affordable_emi": round(float(max_affordable_emi), MONEY_DECIMALS),
        "existing_emi": existing_emi,
        "proposed_emi": proposed_emi,
    }


def _load_upi_evidence(
    db: Session, worker_id: str, record: FinancialRecord
) -> tuple[list[float], list[int], bool]:
    rows = (
        db.query(WorkerMonthlyEvidence)
        .filter(WorkerMonthlyEvidence.worker_id == worker_id)
        .order_by(WorkerMonthlyEvidence.year_month)
        .all()
    )
    if rows:
        inflows = [float(row.upi_inflow or 0.0) for row in rows]
        senders = [
            int(row.upi_unique_senders)
            for row in rows
            if row.upi_unique_senders is not None
        ]
        return inflows, senders, False

    aggregate = record.upi_monthly_inflow
    if aggregate is None:
        return [], [], False

    senders = []
    if record.unique_sender_count is not None:
        senders = [int(record.unique_sender_count)]
    return [float(aggregate)], senders, True


def _fetch_worker(db: Session, phone_number: str) -> FinancialRecord:
    record = (
        db.query(FinancialRecord)
        .filter(
            (FinancialRecord.mobile_number == phone_number)
            | (
                FinancialRecord.mobile_number
                == phone_number[-INDIA_PHONE_LAST_DIGITS:]
            )
        )
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No worker financial record found for the consented phone number.",
        )
    return record


def _build_risk_signal(
    db: Session, worker_id: str, request: VerifyRequest
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    profile = (
        db.query(WorkerRiskProfile)
        .filter(WorkerRiskProfile.worker_id == worker_id)
        .first()
    )
    if not profile:
        return (
            RiskSignalSummary(available=False, reason=RISK_UNAVAILABLE_REASON).model_dump(),
            {"available": False, "reason": RISK_UNAVAILABLE_REASON},
        )

    features = dict(profile.features or {})
    if request.tenure_months is not None:
        # credit_term_months is the one model feature a request may supply.
        features["credit_term_months"] = float(request.tenure_months)

    try:
        summary = risk_v2.input_summary(features)
        prediction = risk_v2.predict(features)
        explanation = risk_v2.explain(features, top_n=RISK_TOP_N)
    except Exception as exc:  # noqa: BLE001 - keep decision support available
        reason = f"Risk signal could not be computed from this profile: {exc}"
        return (
            RiskSignalSummary(available=False, reason=reason).model_dump(),
            {"available": False, "reason": reason},
        )

    factors_raising = [RiskFactor(**item) for item in explanation["raising_risk"]]
    factors_lowering = [RiskFactor(**item) for item in explanation["lowering_risk"]]

    full_signal = RiskSignalSummary(
        available=True,
        band=prediction["band"],
        risk_score_0_100=prediction["risk_score_0_100"],
        reference_population_pd=prediction["calibrated_pd"],
        reference_note=REFERENCE_POPULATION_NOTE,
        reliability=summary["reliability"],
        reliability_note=summary["reliability_note"],
        inputs_provided_count=summary["provided_count"],
        inputs_missing=summary["missing"],
        top_factors_raising_risk=factors_raising,
        top_factors_lowering_risk=factors_lowering,
    )
    compact = {
        "available": True,
        "band": prediction["band"],
        "reference_population_pd": prediction["calibrated_pd"],
        "risk_score_0_100": prediction["risk_score_0_100"],
        "reliability": summary["reliability"],
    }
    return full_signal.model_dump(), compact


def run_verification(db: Session, request: VerifyRequest) -> VerifyResponse:
    """Run the deterministic verification, risk and recommendation pipeline."""
    if not risk_v2.is_loaded():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Risk v2 artifacts are unavailable; verification cannot proceed.",
        )

    consent = validate_consent(
        db, request.consent_id, request.worker_id, request.phone_number
    )
    phone_number = (
        normalize_phone(request.phone_number)
        if request.phone_number
        else consent.phone_number
    )
    record = _fetch_worker(db, phone_number)

    upi_inflows, upi_senders, used_fallback = _load_upi_evidence(
        db, request.worker_id, record
    )

    if request.sms_log:
        sms_provenance = SMS_PROVENANCE_IGNORED
        sms_ignored_reason: Optional[str] = SMS_IGNORED_NO_DATES
    else:
        sms_provenance = SMS_PROVENANCE_NOT_PROVIDED
        sms_ignored_reason = None

    evidence_input = EvidenceInput(
        stated_monthly_income=request.stated_monthly_income,
        upi_monthly_inflows=upi_inflows,
        upi_unique_senders_per_month=upi_senders,
        # SMS is deliberately omitted because the parser exposes no transaction dates.
        sms_monthly_credits=[],
        monthly_outgoings=request.monthly_outgoings or {},
        household_size=request.household_size,
        occupation_type=request.occupation_type,
    )
    evidence_result = verify(evidence_input)
    if used_fallback:
        evidence_result.reasons.insert(0, FALLBACK_EVIDENCE_REASON)

    affordability = compute_affordability(
        evidence_result,
        request.monthly_outgoings,
        request.proposed_emi,
        settings.FOIR_CAP,
    )
    affordability_for_recommendation = dict(affordability)
    affordability_for_recommendation["sms_provenance"] = sms_provenance

    risk_signal, risk_for_recommendation = _build_risk_signal(
        db, request.worker_id, request
    )
    recommendation = recommend(
        evidence_result, risk_for_recommendation, affordability_for_recommendation
    )

    created_at = datetime.now(timezone.utc)
    verification_id = f"VRF-{uuid.uuid4().hex[:VERIFICATION_ID_BYTES].upper()}"

    response = VerifyResponse(
        verification_id=verification_id,
        worker_id=request.worker_id,
        consent_id=consent.id,
        created_at=created_at,
        income=IncomeSummary(
            low=evidence_result.income_low,
            mid=evidence_result.income_mid,
            high=evidence_result.income_high,
            conservative=evidence_result.income_low,
            stated=request.stated_monthly_income,
            stated_vs_evidence_ratio=evidence_result.stated_vs_evidence_ratio,
        ),
        expenses=ExpensesSummary(
            estimated=evidence_result.estimated_expenses,
            complete=evidence_result.expenses_complete,
        ),
        surplus_conservative=evidence_result.monthly_surplus_conservative,
        evidence=EvidenceSummary(
            confidence_score=evidence_result.evidence_confidence_score,
            confidence_level=evidence_result.evidence_confidence_level,
            confidence_capped=evidence_result.confidence_capped,
            components=evidence_result.confidence_components,
            months=evidence_result.months_of_evidence,
            provenance={"upi": UPI_PROVENANCE_DATABASE, "sms": sms_provenance},
            flags=evidence_result.flags,
            reasons=evidence_result.reasons,
        ),
        affordability=AffordabilitySummary(
            foir_current=affordability["foir_current"],
            foir_with_proposed=affordability["foir_with_proposed"],
            foir_cap=affordability["foir_cap"],
            max_affordable_emi=affordability["max_affordable_emi"],
        ),
        risk_signal=RiskSignalSummary(**risk_signal),
        recommendation=RecommendationSummary(**recommendation),
        model_version=risk_v2.model_version() or "unknown",
        engine_version=ENGINE_VERSION,
        sms_ignored_reason=sms_ignored_reason,
    )

    stored = VerificationResultRecord(
        id=verification_id,
        worker_id=request.worker_id,
        consent_id=consent.id,
        result=response.model_dump(mode="json"),
        created_at=created_at,
    )
    db.add(stored)
    db.commit()
    return response


def get_stored_verification(
    db: Session, verification_id: str, consent_id: Optional[str]
) -> VerifyResponse:
    """Fetch a stored verification after re-validating consent for the same worker."""
    stored = (
        db.query(VerificationResultRecord)
        .filter(VerificationResultRecord.id == verification_id)
        .first()
    )
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification '{verification_id}' not found.",
        )

    validate_consent(db, consent_id, stored.worker_id)
    return VerifyResponse.model_validate(stored.result)
