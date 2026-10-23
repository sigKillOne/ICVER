"""Deterministic decision-support recommendation rules for the /verify flow.

ICVER recommends the next underwriting step only. It never approves or rejects a loan
and never sets price or loan-size terms.
"""

from __future__ import annotations

from typing import Any, Dict, List

INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
NEEDS_MORE_EVIDENCE = "NEEDS_MORE_EVIDENCE"
NOT_AFFORDABLE_AT_REQUESTED_EMI = "NOT_AFFORDABLE_AT_REQUESTED_EMI"
MANUAL_REVIEW_HIGH_RISK = "MANUAL_REVIEW_HIGH_RISK"
PROCEED_TO_UNDERWRITING = "PROCEED_TO_UNDERWRITING"

# Named policy labels (no numeric assumption is needed for these rule inputs).
NO_EVIDENCE_FLAG = "NO_EVIDENCE"
STATED_OVERSTATED_FLAG = "STATED_OVERSTATED"
UNVERIFIED_EVIDENCE_ONLY_FLAG = "UNVERIFIED_EVIDENCE_ONLY"
SINGLE_SOURCE_FLAG = "SINGLE_SOURCE"
LOW_CONFIDENCE = "LOW"
MEDIUM_CONFIDENCE = "MEDIUM"
HIGH_RISK_BAND = "HIGH"
LIMITED_RELIABILITY = "LIMITED"
CLIENT_SUPPLIED_SMS_PROVENANCE = "client_supplied_unverified"

UNVERIFIED_SMS_ONLY_REASON = (
    "income rests only on client-supplied, unverified SMS; a verifiable source such "
    "as a bank statement or account-aggregator data is needed"
)
CAVEAT_RISK_SIGNAL_UNAVAILABLE = (
    "No credit-history profile available; this recommendation rests on income "
    "verification and affordability only"
)
CAVEAT_MEDIUM_CONFIDENCE = "Evidence confidence is MEDIUM; supporting documents may be requested."
CAVEAT_EXPENSES_INCOMPLETE = (
    "Monthly expenses are incomplete, so the conservative surplus may be overstated."
)
CAVEAT_SINGLE_SOURCE = "Only one evidence source was available; independent cross-checks are limited."
CAVEAT_LIMITED_RELIABILITY = (
    "The reference-population risk signal has LIMITED reliability for this worker profile."
)
CAVEAT_UNVERIFIED_SMS = (
    "SMS evidence is client-supplied and unverified; used only to cross-check "
    "database evidence"
)


def _has_flag(evidence_result: Any, code: str) -> bool:
    return any(flag.get("code") == code for flag in evidence_result.flags)


def _flag_message(evidence_result: Any, code: str) -> str | None:
    for flag in evidence_result.flags:
        if flag.get("code") == code:
            return flag.get("message")
    return None


def _risk_caveats(risk: Dict[str, Any]) -> List[str]:
    caveats: List[str] = []
    if not risk.get("available", False):
        caveats.append(CAVEAT_RISK_SIGNAL_UNAVAILABLE)
    if risk.get("reliability") == LIMITED_RELIABILITY:
        caveats.append(CAVEAT_LIMITED_RELIABILITY)
    return caveats


def _sms_caveat(affordability: Dict[str, Any]) -> List[str]:
    if (
        affordability.get("sms_provenance") == CLIENT_SUPPLIED_SMS_PROVENANCE
        and affordability.get("upi_provenance", "database") == "database"
    ):
        return [CAVEAT_UNVERIFIED_SMS]
    return []


def recommend(
    evidence_result: Any,
    risk: Dict[str, Any],
    affordability: Dict[str, Any],
) -> Dict[str, List[str] | str]:
    """Apply the recommendation rules in priority order and add non-blocking caveats."""
    reasons: List[str] = []

    if _has_flag(evidence_result, NO_EVIDENCE_FLAG):
        return {
            "code": INSUFFICIENT_EVIDENCE,
            "reasons": ["No reliable UPI or bank SMS evidence was available to verify income."],
            "caveats": [],
        }

    if evidence_result.evidence_confidence_level == LOW_CONFIDENCE:
        return {
            "code": NEEDS_MORE_EVIDENCE,
            "reasons": [
                f"Evidence confidence is LOW ({evidence_result.evidence_confidence_score}/100); "
                "more transaction history or corroborating evidence is needed."
            ],
            "caveats": _risk_caveats(risk) + _sms_caveat(affordability),
        }

    if _has_flag(evidence_result, STATED_OVERSTATED_FLAG):
        message = _flag_message(evidence_result, STATED_OVERSTATED_FLAG)
        return {
            "code": NEEDS_MORE_EVIDENCE,
            "reasons": [
                message
                or "Stated income is materially above the verified evidence, so more evidence is needed."
            ],
            "caveats": _risk_caveats(risk) + _sms_caveat(affordability),
        }

    if _has_flag(evidence_result, UNVERIFIED_EVIDENCE_ONLY_FLAG):
        return {
            "code": NEEDS_MORE_EVIDENCE,
            "reasons": [UNVERIFIED_SMS_ONLY_REASON],
            "caveats": _risk_caveats(risk),
        }

    proposed_emi = affordability.get("proposed_emi")
    max_affordable_emi = affordability.get("max_affordable_emi")
    if (
        proposed_emi is not None
        and max_affordable_emi is not None
        and float(proposed_emi) > float(max_affordable_emi)
    ):
        return {
            "code": NOT_AFFORDABLE_AT_REQUESTED_EMI,
            "reasons": [
                f"Requested EMI of \u20b9{float(proposed_emi):,.2f} exceeds the maximum "
                f"affordable EMI of \u20b9{float(max_affordable_emi):,.2f} under the "
                "conservative affordability test."
            ],
            "caveats": _risk_caveats(risk) + _sms_caveat(affordability),
        }

    if risk.get("band") == HIGH_RISK_BAND:
        return {
            "code": MANUAL_REVIEW_HIGH_RISK,
            "reasons": [
                "The reference-population repayment-risk band is HIGH; manual review is recommended."
            ],
            "caveats": _risk_caveats(risk) + _sms_caveat(affordability),
        }

    reasons.append(
        "Evidence is sufficient and the requested obligation is within the conservative "
        "affordability test; proceed to lender underwriting."
    )

    caveats: List[str] = []
    if evidence_result.evidence_confidence_level == MEDIUM_CONFIDENCE:
        caveats.append(CAVEAT_MEDIUM_CONFIDENCE)
    if not evidence_result.expenses_complete:
        caveats.append(CAVEAT_EXPENSES_INCOMPLETE)
    if _has_flag(evidence_result, SINGLE_SOURCE_FLAG):
        caveats.append(CAVEAT_SINGLE_SOURCE)
    if not risk.get("available", False):
        caveats.append(CAVEAT_RISK_SIGNAL_UNAVAILABLE)
    if risk.get("reliability") == LIMITED_RELIABILITY:
        caveats.append(CAVEAT_LIMITED_RELIABILITY)
    if affordability.get("sms_provenance") == CLIENT_SUPPLIED_SMS_PROVENANCE:
        caveats.append(CAVEAT_UNVERIFIED_SMS)

    return {
        "code": PROCEED_TO_UNDERWRITING,
        "reasons": reasons,
        "caveats": caveats,
    }
