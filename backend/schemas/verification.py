"""Pydantic v2 request/response schemas for the /api/v1/verify flow."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MONEY_VALUE = 1_000_000_000.0  # Request sanity bound, not a credit policy threshold.
MAX_HOUSEHOLD_SIZE = 50  # Request sanity bound.
MAX_OCCUPATION_LENGTH = 100
MAX_SMS_MESSAGES = 1_000  # Request sanity bound.
MAX_SMS_MESSAGE_LENGTH = 5_000
MIN_TENURE_MONTHS = 1
MAX_TENURE_MONTHS = 120


class VerifyRequest(BaseModel):
    """Lender request to verify income and obtain decision support."""

    model_config = ConfigDict(
        extra="forbid",
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
    sms_log: Optional[List[str]] = Field(default=None, max_length=MAX_SMS_MESSAGES)
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

    @field_validator("sms_log")
    @classmethod
    def validate_sms_log(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        for message in value:
            if not isinstance(message, str):
                raise ValueError("sms_log entries must be strings")
            if len(message) > MAX_SMS_MESSAGE_LENGTH:
                raise ValueError("sms_log entry exceeds the maximum message length")
        return value


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


class AffordabilitySummary(BaseModel):
    foir_current: Optional[float]
    foir_with_proposed: Optional[float]
    foir_cap: float
    max_affordable_emi: Optional[float]


class RiskFactor(BaseModel):
    feature: str
    label: str
    direction: str
    relative_size: float
    log_odds_contribution: float


class RiskSignalSummary(BaseModel):
    available: bool
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
    model_version: str
    engine_version: str
    sms_ignored_reason: Optional[str] = None
    disclaimer: str = (
        "Decision support only. The lender makes the credit decision. "
        "ICVER does not set interest rates or loan limits."
    )
