"""Pydantic v2 request/response schemas for the /api/v1/verify flow."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_MONEY_VALUE = 1_000_000_000.0  # Request sanity bound, not a credit policy threshold.
MAX_HOUSEHOLD_SIZE = 50  # Request sanity bound.
MAX_OCCUPATION_LENGTH = 100
MAX_SMS_MESSAGES = 300  # Request-size assumption; larger batches are rejected.
MAX_SMS_MESSAGE_LENGTH = 500  # Assumption: one bank SMS fits comfortably in 500 chars.
MIN_TENURE_MONTHS = 1
MAX_TENURE_MONTHS = 120

# What-if sanity bounds. These are product assumptions, not credit-policy limits.
WHAT_IF_MIN_UPI_MONTHS = 1
WHAT_IF_MAX_UPI_MONTHS = 12
WHAT_IF_MAX_UPI_INFLOW = 10_000_000.0
WHAT_IF_MAX_UNIQUE_SENDERS = 1_000

DECISION_SUPPORT_DISCLAIMER = (
    "Decision support only. The lender makes the credit decision. "
    "ICVER does not set interest rates or loan limits."
)


def _validate_monthly_outgoings(
    value: Optional[Dict[str, float]],
) -> Optional[Dict[str, float]]:
    if value is None:
        return None
    cleaned: Dict[str, float] = {}
    for key, amount in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("monthly_outgoings keys must be non-empty strings")
        if amount is None or not math.isfinite(float(amount)):
            raise ValueError(f"monthly_outgoings['{key}'] must be a finite number")
        if float(amount) < 0:
            raise ValueError(f"monthly_outgoings['{key}'] must be non-negative")
        if float(amount) > MAX_MONEY_VALUE:
            raise ValueError(f"monthly_outgoings['{key}'] exceeds the sanity bound")
        cleaned[key] = float(amount)
    return cleaned


class SMSMessage(BaseModel):
    """One client-supplied SMS with its client-supplied receipt timestamp."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    text: str = Field(min_length=1, max_length=MAX_SMS_MESSAGE_LENGTH)
    received_at: datetime

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "received_at must include a timezone offset (ISO-8601), for example "
                "2026-01-31T23:30:00+05:30"
            )
        return value


class VerifyRequest(BaseModel):
    """Lender request to verify income and obtain decision support."""

    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        json_schema_extra={
            "example": {
                "worker_id": "WRK-10024",
                "consent_id": "CNS-89472-2026",
                "phone_number": "9876543210",
                "stated_monthly_income": 30000.0,
                "monthly_outgoings": {
                    "food": 8000.0,
                    "rent": 6000.0,
                    "existing_emi": 1500.0,
                },
                "household_size": 4,
                "occupation_type": "Street vendor",
                "proposed_emi": 2500.0,
                "tenure_months": 24,
            }
        },
    )

    worker_id: str = Field(min_length=1, max_length=50)
    consent_id: Optional[str] = Field(default=None, max_length=50)
    phone_number: Optional[str] = Field(default=None, max_length=20)
    stated_monthly_income: Optional[float] = Field(
        default=None, ge=0.0, le=MAX_MONEY_VALUE
    )
    monthly_outgoings: Optional[Dict[str, float]] = Field(default=None)
    household_size: Optional[int] = Field(default=None, ge=1, le=MAX_HOUSEHOLD_SIZE)
    occupation_type: Optional[str] = Field(
        default=None, max_length=MAX_OCCUPATION_LENGTH
    )
    sms_log: Optional[List[SMSMessage]] = Field(
        default=None, max_length=MAX_SMS_MESSAGES
    )
    proposed_emi: Optional[float] = Field(
        default=None, ge=0.0, le=MAX_MONEY_VALUE
    )
    tenure_months: Optional[int] = Field(
        default=None, ge=MIN_TENURE_MONTHS, le=MAX_TENURE_MONTHS
    )

    @field_validator("monthly_outgoings")
    @classmethod
    def validate_outgoings(
        cls, value: Optional[Dict[str, float]]
    ) -> Optional[Dict[str, float]]:
        return _validate_monthly_outgoings(value)

    @field_validator("sms_log", mode="before")
    @classmethod
    def validate_sms_log(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, list):
            return value
        if len(value) > MAX_SMS_MESSAGES:
            raise ValueError(
                f"sms_log accepts at most {MAX_SMS_MESSAGES} messages per request"
            )
        for message in value:
            if isinstance(message, str):
                raise ValueError(
                    "Each sms_log item must be an object with 'text' (max "
                    f"{MAX_SMS_MESSAGE_LENGTH} chars) and 'received_at' (ISO-8601 "
                    "datetime with a timezone offset). Plain strings are no longer "
                    "accepted."
                )
        return value


class WhatIfRequest(BaseModel):
    """Hypothetical scenario inputs; never persisted and never a credit record."""

    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        json_schema_extra={
            "example": {
                "worker_id": "demo-low_risk_full_history",
                "consent_id": "demo-consent-low_risk_full_history",
                "hypothetical_upi_monthly_inflows": [
                    32000.0,
                    33000.0,
                    31500.0,
                    32500.0,
                    31800.0,
                    32200.0,
                ],
                "hypothetical_unique_senders": [14, 15, 14, 16, 15, 14],
                "stated_monthly_income": 30000.0,
                "monthly_outgoings": {
                    "food": 7000.0,
                    "rent": 6000.0,
                    "existing_emi": 500.0,
                },
                "household_size": 4,
                "proposed_emi": 2500.0,
                "tenure_months": 24,
            }
        },
    )

    worker_id: str = Field(min_length=1, max_length=50)
    consent_id: Optional[str] = Field(default=None, max_length=50)
    phone_number: Optional[str] = Field(default=None, max_length=20)
    hypothetical_upi_monthly_inflows: Optional[List[float]] = Field(
        default=None,
        min_length=WHAT_IF_MIN_UPI_MONTHS,
        max_length=WHAT_IF_MAX_UPI_MONTHS,
    )
    hypothetical_unique_senders: Optional[List[int]] = Field(
        default=None, max_length=WHAT_IF_MAX_UPI_MONTHS
    )
    stated_monthly_income: Optional[float] = Field(
        default=None, ge=0.0, le=MAX_MONEY_VALUE
    )
    monthly_outgoings: Optional[Dict[str, float]] = Field(default=None)
    household_size: Optional[int] = Field(default=None, ge=1, le=MAX_HOUSEHOLD_SIZE)
    proposed_emi: Optional[float] = Field(
        default=None, ge=0.0, le=MAX_MONEY_VALUE
    )
    tenure_months: Optional[int] = Field(
        default=None, ge=MIN_TENURE_MONTHS, le=MAX_TENURE_MONTHS
    )

    @field_validator("monthly_outgoings")
    @classmethod
    def validate_outgoings(
        cls, value: Optional[Dict[str, float]]
    ) -> Optional[Dict[str, float]]:
        return _validate_monthly_outgoings(value)

    @field_validator("hypothetical_upi_monthly_inflows")
    @classmethod
    def validate_hypothetical_inflows(
        cls, value: Optional[List[float]]
    ) -> Optional[List[float]]:
        if value is None:
            return None
        cleaned: List[float] = []
        for amount in value:
            numeric = float(amount)
            if not math.isfinite(numeric):
                raise ValueError(
                    "hypothetical_upi_monthly_inflows must contain finite numbers"
                )
            if numeric < 0.0 or numeric > WHAT_IF_MAX_UPI_INFLOW:
                raise ValueError(
                    "hypothetical_upi_monthly_inflows must be between 0 and "
                    f"{WHAT_IF_MAX_UPI_INFLOW:,.0f}"
                )
            cleaned.append(numeric)
        return cleaned

    @field_validator("hypothetical_unique_senders")
    @classmethod
    def validate_hypothetical_senders(
        cls, value: Optional[List[int]]
    ) -> Optional[List[int]]:
        if value is None:
            return None
        cleaned: List[int] = []
        for senders in value:
            if senders < 0 or senders > WHAT_IF_MAX_UNIQUE_SENDERS:
                raise ValueError(
                    "hypothetical_unique_senders must be between 0 and "
                    f"{WHAT_IF_MAX_UNIQUE_SENDERS}"
                )
            cleaned.append(int(senders))
        return cleaned

    @model_validator(mode="after")
    def validate_senders_length(self) -> "WhatIfRequest":
        senders = self.hypothetical_unique_senders
        inflows = self.hypothetical_upi_monthly_inflows
        if senders:
            if inflows is None:
                raise ValueError(
                    "hypothetical_unique_senders requires "
                    "hypothetical_upi_monthly_inflows"
                )
            if len(senders) != len(inflows):
                raise ValueError(
                    "hypothetical_unique_senders must be empty or the same length "
                    "as hypothetical_upi_monthly_inflows"
                )
        return self


class IncomeSummary(BaseModel):
    low: Optional[float]
    mid: Optional[float]
    high: Optional[float]
    conservative: Optional[float]
    stated: Optional[float]
    stated_vs_evidence_ratio: Optional[float]


class ExpensesSummary(BaseModel):
    estimated: Optional[float]
    complete: bool


class EvidenceSummary(BaseModel):
    confidence_score: int
    confidence_level: str
    confidence_capped: bool
    components: Dict[str, Dict[str, int]]
    months: int
    provenance: Dict[str, str]
    flags: List[Dict[str, str]]
    reasons: List[str]
    consistency_note: Optional[str] = None


class AffordabilitySummary(BaseModel):
    foir_current: Optional[float]
    foir_with_proposed: Optional[float]
    foir_cap: float
    max_affordable_emi: Optional[float]


class SmsClippedMonth(BaseModel):
    month: str
    sms_total: float
    upi_total: float
    used_total: float


class SmsSummary(BaseModel):
    received: int = 0
    used: int = 0
    dropped: int = 0
    dropped_by_reason: Dict[str, int] = Field(default_factory=dict)
    clipped_months: List[SmsClippedMonth] = Field(default_factory=list)
    monthly_credits: Dict[str, float] = Field(default_factory=dict)


class RiskFactor(BaseModel):
    feature: str
    label: str
    direction: str
    relative_size: float
    log_odds_contribution: float


class RiskSignalSummary(BaseModel):
    available: bool
    display_priority: str = "primary"
    display_note: Optional[str] = None
    band: Optional[str] = None
    risk_score_0_100: Optional[float] = None
    reference_population_pd: Optional[float] = None
    reference_note: Optional[str] = None
    reliability: Optional[str] = None
    reliability_note: Optional[str] = None
    inputs_provided_count: int = 0
    inputs_missing: List[str] = Field(default_factory=list)
    top_factors_raising_risk: List[RiskFactor] = Field(default_factory=list)
    top_factors_lowering_risk: List[RiskFactor] = Field(default_factory=list)
    reason: Optional[str] = None


class RecommendationSummary(BaseModel):
    code: str
    reasons: List[str]
    caveats: List[str]


class WhatIfOutcomeSummary(BaseModel):
    """The subset of verification results compared in a what-if response."""

    income_low: Optional[float]
    income_mid: Optional[float]
    surplus_conservative: Optional[float]
    confidence_score: int
    confidence_level: str
    max_affordable_emi: Optional[float]
    flags: List[Dict[str, str]]


class WhatIfBaselineSummary(WhatIfOutcomeSummary):
    recommendation_code: str


class WhatIfScenarioSummary(WhatIfOutcomeSummary):
    hypothetical_recommendation_code: str


class WhatIfDeltas(BaseModel):
    income_low: Optional[float]
    surplus: Optional[float]
    max_affordable_emi: Optional[float]
    confidence_score: Optional[float]


class WhatIfResponse(BaseModel):
    hypothetical: bool = True
    baseline: WhatIfBaselineSummary
    scenario: WhatIfScenarioSummary
    deltas: WhatIfDeltas
    notes: List[str]
    data_notice: Optional[str] = None
    disclaimer: str = DECISION_SUPPORT_DISCLAIMER


class VerifyResponse(BaseModel):
    verification_id: str
    worker_id: str
    consent_id: str
    created_at: datetime
    income: IncomeSummary
    expenses: ExpensesSummary
    surplus_conservative: Optional[float]
    evidence: EvidenceSummary
    affordability: AffordabilitySummary
    risk_signal: RiskSignalSummary
    recommendation: RecommendationSummary
    sms_summary: SmsSummary = Field(default_factory=SmsSummary)
    model_version: str
    engine_version: str
    sms_ignored_reason: Optional[str] = None
    data_notice: Optional[str] = None
    disclaimer: str = DECISION_SUPPORT_DISCLAIMER
