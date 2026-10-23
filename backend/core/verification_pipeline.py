"""Orchestration for the /verify income-verification and decision-support flow."""

from __future__ import annotations

import calendar
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

try:
    from backend.core import risk_v2
    from backend.core.config import settings
    from backend.core.consent import validate_consent
    from backend.core.income_verification import EvidenceInput, VerificationResult, verify
    from backend.core.parser import extract_upi_inflow
    from backend.core.phone import normalize_phone
    from backend.core.recommendation import (
        INSUFFICIENT_EVIDENCE,
        LIMITED_RELIABILITY,
        UNVERIFIED_EVIDENCE_ONLY_FLAG,
        recommend,
    )
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
        SmsClippedMonth,
        SmsSummary,
        VerifyRequest,
        VerifyResponse,
    )
except ModuleNotFoundError:  # pragma: no cover - flat module execution fallback
    from core import risk_v2
    from core.config import settings
    from core.consent import validate_consent
    from core.income_verification import EvidenceInput, VerificationResult, verify
    from core.parser import extract_upi_inflow
    from core.phone import normalize_phone
    from core.recommendation import (
        INSUFFICIENT_EVIDENCE,
        LIMITED_RELIABILITY,
        UNVERIFIED_EVIDENCE_ONLY_FLAG,
        recommend,
    )
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
        SmsClippedMonth,
        SmsSummary,
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
# Asia/Kolkata is the source timezone for Indian bank and UPI SMS receipts.
INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")
SMS_LOOKBACK_MONTHS = 12  # Assumption: one year of SMS history is the useful review window.
SMS_MONTH_KEY_FORMAT = "%Y-%m"
SMS_CONFIDENCE_CEILING = "MEDIUM"  # Assumption: unverified SMS alone cannot support HIGH confidence.
SMS_PROVENANCE_NOT_PROVIDED = "not_provided"
SMS_PROVENANCE_CLIENT = "client_supplied_unverified"
SMS_PROVENANCE_NONE_USABLE = "ignored_none_usable"
UPI_PROVENANCE_DATABASE = "database"
UPI_PROVENANCE_NONE = "none"
SMS_DROP_FUTURE = "future_received_at"
SMS_DROP_TOO_OLD = "older_than_12_months"
SMS_DROP_DUPLICATE = "duplicate"
SMS_DROP_UNPARSEABLE = "unparseable"
SMS_DROP_DEBIT = "debit"
SMS_DROP_REASONS: Tuple[str, ...] = (
    SMS_DROP_FUTURE,
    SMS_DROP_TOO_OLD,
    SMS_DROP_DUPLICATE,
    SMS_DROP_UNPARSEABLE,
    SMS_DROP_DEBIT,
)
# Assumption: the parser exposes credit extraction only, so these words identify a debit
# message that yielded no parseable credit amount. This is only used for summary counts.
SMS_DEBIT_KEYWORDS: Tuple[str, ...] = (
    "debited",
    "debit",
    "withdrawn",
    "withdrawal",
    "spent",
    "purchase",
    "paid to",
    "sent to",
)
SMS_IGNORED_NOTHING_USABLE = (
    "SMS messages were provided, but none could be used: every message was dated "
    "outside the allowed 12-month window, was an exact duplicate, was a debit, or had "
    "no parseable credit amount."
)
SMS_CONFIDENCE_CAP_REASON = (
    "Confidence capped at MEDIUM because income evidence rests only on client-supplied, "
    "unverified SMS."
)
UNVERIFIED_SMS_FLAG = "UNVERIFIED_SMS"
UNVERIFIED_SMS_MESSAGE = (
    "SMS evidence is client-supplied and unverified; it is used only to cross-check "
    "database UPI evidence."
)
UNVERIFIED_EVIDENCE_ONLY_MESSAGE = (
    "All income evidence comes from client-supplied, unverified SMS; no database UPI "
    "evidence is available."
)
DISPLAY_PRIORITY_PRIMARY = "primary"
DISPLAY_PRIORITY_SECONDARY = "secondary"
DISPLAY_NOTE_INSUFFICIENT = (
    "Secondary because income evidence is insufficient to support a risk-based view."
)
DISPLAY_NOTE_UNAVAILABLE = (
    "Secondary because no credit-history profile is available for this worker."
)
DISPLAY_NOTE_LIMITED = (
    "Secondary because the credit-history profile has LIMITED reliability."
)
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


def _subtract_months(moment: datetime, months: int) -> datetime:
    """Return the same clock time a whole number of calendar months earlier."""
    month_index = moment.year * 12 + (moment.month - 1) - months
    year, month_zero_based = divmod(month_index, 12)
    month = month_zero_based + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _looks_like_debit(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in SMS_DEBIT_KEYWORDS)


def _build_sms_evidence(
    messages: Optional[List[Any]],
    now_utc: datetime,
    upi_by_month: Dict[str, float],
) -> Tuple[List[float], List[float], SmsSummary, str, Optional[str]]:
    """Aggregate SMS credits in IST and apply anti-inflation clipping.

    The SMS text and timestamps are client-supplied. Raw text is never retained; only
    month-level aggregates and counts leave this function.
    """
    messages = messages or []
    earliest_allowed = _subtract_months(now_utc, SMS_LOOKBACK_MONTHS)
    dropped_by_reason = {reason: 0 for reason in SMS_DROP_REASONS}
    seen: set[tuple[str, datetime]] = set()
    month_totals: Dict[str, float] = {}
    used = 0

    for message in messages:
        received_at = message.received_at
        if received_at > now_utc:
            dropped_by_reason[SMS_DROP_FUTURE] += 1
            continue
        if received_at < earliest_allowed:
            dropped_by_reason[SMS_DROP_TOO_OLD] += 1
            continue

        dedupe_key = (message.text, received_at)
        if dedupe_key in seen:
            dropped_by_reason[SMS_DROP_DUPLICATE] += 1
            continue
        seen.add(dedupe_key)

        try:
            amount = float(extract_upi_inflow(message.text))
        except Exception:  # noqa: BLE001 - malformed SMS must never break verification
            amount = 0.0

        if amount <= 0:
            reason = (
                SMS_DROP_DEBIT
                if _looks_like_debit(message.text)
                else SMS_DROP_UNPARSEABLE
            )
            dropped_by_reason[reason] += 1
            continue

        month_key = received_at.astimezone(INDIA_TIMEZONE).strftime(
            SMS_MONTH_KEY_FORMAT
        )
        month_totals[month_key] = month_totals.get(month_key, 0.0) + amount
        used += 1

    positive_upi_months = {
        month_key for month_key, value in upi_by_month.items() if value > 0
    }
    sms_months = set(month_totals)
    sms_covers_upi_months = bool(sms_months) and sms_months == positive_upi_months
    # The engine compares parallel monthly lists and cannot represent sparse missing
    # months. When both sources exist but the SMS log is sparse, fold the union into a
    # single conservative series for the engine; this keeps months with only SMS
    # unclipped without inventing false source disagreements.
    all_months = (
        sorted(set(upi_by_month) | sms_months)
        if positive_upi_months
        else (sorted(sms_months) if sms_months else sorted(upi_by_month))
    )
    upi_series: List[float] = []
    sms_series: List[float] = []
    clipped_months: List[SmsClippedMonth] = []

    for month_key in all_months:
        raw_sms_total = float(month_totals.get(month_key, 0.0))
        upi_total = float(upi_by_month.get(month_key, 0.0) or 0.0)
        used_sms_total = raw_sms_total
        if month_key in upi_by_month and raw_sms_total > upi_total:
            used_sms_total = max(upi_total, 0.0)
            clipped_months.append(
                SmsClippedMonth(
                    month=month_key,
                    sms_total=round(raw_sms_total, MONEY_DECIMALS),
                    upi_total=round(upi_total, MONEY_DECIMALS),
                    used_total=round(used_sms_total, MONEY_DECIMALS),
                )
            )
        upi_series.append(upi_total)
        sms_series.append(used_sms_total)

    monthly_credits = {
        month_key: round(value, MONEY_DECIMALS)
        for month_key, value in zip(all_months, sms_series)
    }
    dropped = sum(dropped_by_reason.values())
    summary = SmsSummary(
        received=len(messages),
        used=used,
        dropped=dropped,
        dropped_by_reason=dropped_by_reason,
        clipped_months=clipped_months,
        monthly_credits=monthly_credits,
    )

    if not messages:
        provenance = SMS_PROVENANCE_NOT_PROVIDED
    elif used == 0:
        provenance = SMS_PROVENANCE_NONE_USABLE
    else:
        provenance = SMS_PROVENANCE_CLIENT

    ignored_reason = (
        SMS_IGNORED_NOTHING_USABLE if messages and used == 0 else None
    )
    if not positive_upi_months or sms_covers_upi_months:
        engine_upi_series = upi_series
        engine_sms_series = sms_series
    else:
        engine_upi_series = [
            max(upi_value, sms_value)
            for upi_value, sms_value in zip(upi_series, sms_series)
        ]
        engine_sms_series = [0.0] * len(sms_series)
    return (
        engine_sms_series,
        engine_upi_series,
        summary,
        provenance,
        ignored_reason,
    )


def _load_upi_evidence(
    db: Session,
    worker_id: str,
    record: FinancialRecord,
    fallback_month_key: str,
) -> Tuple[List[str], List[float], List[int], bool]:
    rows = (
        db.query(WorkerMonthlyEvidence)
        .filter(WorkerMonthlyEvidence.worker_id == worker_id)
        .order_by(WorkerMonthlyEvidence.year_month)
        .all()
    )
    if rows:
        month_keys = [row.year_month for row in rows]
        inflows = [float(row.upi_inflow or 0.0) for row in rows]
        senders = [
            int(row.upi_unique_senders)
            for row in rows
            if row.upi_unique_senders is not None
        ]
        return month_keys, inflows, senders, False

    aggregate = record.upi_monthly_inflow
    if aggregate is None:
        return [], [], [], False

    senders = []
    if record.unique_sender_count is not None:
        senders = [int(record.unique_sender_count)]
    return [fallback_month_key], [float(aggregate)], senders, True


def _apply_unverified_sms_only(evidence_result: VerificationResult) -> None:
    """Add the verified-only flag and cap confidence at MEDIUM."""
    if not any(
        flag.get("code") == UNVERIFIED_EVIDENCE_ONLY_FLAG
        for flag in evidence_result.flags
    ):
        evidence_result.flags.append(
            {
                "code": UNVERIFIED_EVIDENCE_ONLY_FLAG,
                "severity": "HIGH",
                "message": UNVERIFIED_EVIDENCE_ONLY_MESSAGE,
            }
        )

    if evidence_result.evidence_confidence_level == "HIGH":
        evidence_result.evidence_confidence_level = SMS_CONFIDENCE_CEILING
        evidence_result.confidence_capped = True
        evidence_result.reasons.insert(0, SMS_CONFIDENCE_CAP_REASON)


def _apply_risk_display(risk_signal: Dict[str, Any], recommendation_code: str) -> None:
    """Explain when the risk signal is secondary rather than the primary driver."""
    note: Optional[str] = None
    if recommendation_code == INSUFFICIENT_EVIDENCE:
        note = DISPLAY_NOTE_INSUFFICIENT
    elif not risk_signal.get("available", False):
        note = DISPLAY_NOTE_UNAVAILABLE
    elif risk_signal.get("reliability") == LIMITED_RELIABILITY:
        note = DISPLAY_NOTE_LIMITED

    if note:
        risk_signal["display_priority"] = DISPLAY_PRIORITY_SECONDARY
        risk_signal["display_note"] = note
    else:
        risk_signal["display_priority"] = DISPLAY_PRIORITY_PRIMARY
        risk_signal["display_note"] = None


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

    now_utc = datetime.now(timezone.utc)
    fallback_month_key = now_utc.astimezone(INDIA_TIMEZONE).strftime(
        SMS_MONTH_KEY_FORMAT
    )
    upi_month_keys, upi_inflows, upi_senders, used_fallback = _load_upi_evidence(
        db, request.worker_id, record, fallback_month_key
    )
    upi_by_month = dict(zip(upi_month_keys, upi_inflows))
    sms_series, upi_series, sms_summary, sms_provenance, sms_ignored_reason = (
        _build_sms_evidence(request.sms_log, now_utc, upi_by_month)
    )

    has_database_upi = any(value > 0 for value in upi_inflows)
    sms_only_evidence = sms_summary.used > 0 and not has_database_upi
    upi_provenance = (
        UPI_PROVENANCE_DATABASE if has_database_upi else UPI_PROVENANCE_NONE
    )

    evidence_input = EvidenceInput(
        stated_monthly_income=request.stated_monthly_income,
        upi_monthly_inflows=upi_series,
        upi_unique_senders_per_month=upi_senders,
        sms_monthly_credits=sms_series,
        monthly_outgoings=request.monthly_outgoings or {},
        household_size=request.household_size,
        occupation_type=request.occupation_type,
    )
    evidence_result = verify(evidence_input)
    if used_fallback:
        evidence_result.reasons.insert(0, FALLBACK_EVIDENCE_REASON)
    if sms_only_evidence:
        _apply_unverified_sms_only(evidence_result)
    elif has_database_upi and sms_summary.used > 0:
        evidence_result.flags.append(
            {
                "code": UNVERIFIED_SMS_FLAG,
                "severity": "MEDIUM",
                "message": UNVERIFIED_SMS_MESSAGE,
            }
        )

    affordability = compute_affordability(
        evidence_result,
        request.monthly_outgoings,
        request.proposed_emi,
        settings.FOIR_CAP,
    )
    affordability_for_recommendation = dict(affordability)
    affordability_for_recommendation["sms_provenance"] = sms_provenance
    affordability_for_recommendation["upi_provenance"] = upi_provenance

    risk_signal, risk_for_recommendation = _build_risk_signal(
        db, request.worker_id, request
    )
    recommendation = recommend(
        evidence_result, risk_for_recommendation, affordability_for_recommendation
    )
    _apply_risk_display(risk_signal, str(recommendation["code"]))

    created_at = now_utc
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
            provenance={"upi": upi_provenance, "sms": sms_provenance},
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
        sms_summary=sms_summary,
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
