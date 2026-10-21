from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# --- Worker Consent Schemas ---

class ConsentRequest(BaseModel):
    worker_id: str = Field(..., example="WRK-10024", description="Unique identifier of the informal worker")
    phone_number: str = Field(..., example="+919876543210", description="Worker registered mobile number")
    consent_given: bool = Field(..., description="Explicit worker consent flag")
    consent_purpose: str = Field(
        default="Income verification for credit assessment",
        description="Purpose for requesting financial data access"
    )


class ConsentResponse(BaseModel):
    consent_id: str = Field(..., example="CNS-89472-2026", description="Unique reference ID for recorded consent")
    worker_id: str
    phone_number: str
    status: str = Field(..., example="ACTIVE", description="Status of consent (ACTIVE, REVOKED, EXPIRED)")
    message: str
    created_at: datetime


# --- Income Scoring Input & Output Schemas ---

class UPITransaction(BaseModel):
    transaction_id: Optional[str] = Field(default=None, example="TXN-90123")
    amount: float = Field(..., example=450.0, description="Transaction amount in INR")
    type: str = Field(default="CREDIT", example="CREDIT", description="CREDIT or DEBIT")
    timestamp: Optional[datetime] = Field(default=None)


class MobileRechargeLog(BaseModel):
    recharge_id: Optional[str] = Field(default=None, example="RCH-44102")
    amount: float = Field(..., example=299.0, description="Recharge plan amount in INR")
    plan_type: str = Field(default="MONTHLY_DATA", example="MONTHLY_DATA")
    recharge_date: Optional[datetime] = Field(default=None)


class ScoringRequest(BaseModel):
    worker_id: str = Field(..., example="WRK-10024")
    consent_id: str = Field(..., example="CNS-89472-2026")
    phone_number: Optional[str] = Field(default=None, example="9876543210")
    sms_log: Optional[str] = Field(
        default=None,
        example="Credited Rs. 500 on 24-Sep by UPI. Received INR 1050.50.",
        description="Raw SMS transaction dump for unstructured inflow extraction"
    )
    upi_transaction_history: List[UPITransaction] = Field(
        default=[],
        description="List of UPI credit/debit transaction logs"
    )
    mobile_recharge_logs: List[MobileRechargeLog] = Field(
        default=[],
        description="List of worker mobile recharge logs"
    )
    monthly_cashflow_avg: Optional[float] = Field(default=28500.0, ge=0)
    gig_platform_earnings: Optional[float] = Field(default=15000.0, ge=0)
    # Simulator feature overrides
    upi_monthly_inflow: Optional[float] = Field(default=None)
    weekly_txn_frequency: Optional[int] = Field(default=None)
    recharge_regularity_index: Optional[float] = Field(default=None)
    days_since_last_txn: Optional[int] = Field(default=None)
    unique_sender_count: Optional[int] = Field(default=None)
    utility_payment_streak: Optional[int] = Field(default=None)
    gig_rating: Optional[float] = Field(default=None)
    gig_hours_per_week: Optional[int] = Field(default=None)


class IncomeBreakdown(BaseModel):
    base_estimated_income: float
    gig_income_weight: float
    cashflow_stability_index: float
    risk_factor: float


class ScoringResponse(BaseModel):
    worker_id: str
    consent_id: str
    creditworthiness_score: int = Field(default=78, example=78, description="Hardcoded/evaluated creditworthiness score (0-100)")
    decision_tier: str = Field(default="Eligible", example="Eligible", description="Credit decision tier (e.g. Eligible, Review, Ineligible)")
    shap_reasons: List[str] = Field(
        default=[
            "+18 for consistent weekly inflow",
            "+12 for regular mobile recharge top-ups",
            "+8 for low volatility in UPI deposits"
        ],
        description="Static SHAP-based feature importance explainability reasons"
    )
    verified_income_estimate: float = Field(..., description="Calculated monthly verified income")
    confidence_score: float = Field(..., ge=0.0, le=1.0, example=0.87)
    risk_category: str = Field(..., example="LOW")
    synthetic_volume_flag: bool = Field(default=False, description="Flag indicating if cyclic synthetic transaction inflation was detected")
    is_gig_worker: bool = Field(default=False)
    unique_sender_count: int = Field(default=0)
    utility_payment_streak: int = Field(default=0)
    gig_rating: Optional[float] = Field(default=None)
    gig_hours_per_week: Optional[int] = Field(default=None)
    breakdown: IncomeBreakdown
    scored_at: datetime

    # --- RBI FOIR Compliance Fields ---
    foir_percentage: float = Field(
        ...,
        example=12.0,
        description="Fixed Obligation to Income Ratio: (existing_emi + proposed_emi) / household_income × 100"
    )
    available_surplus: float = Field(
        ...,
        example=7000.0,
        description="Monthly surplus after all obligations: income − (biz expenses + household expenses + existing EMI + proposed EMI)"
    )
    rbi_compliant: bool = Field(
        ...,
        description="True if FOIR ≤ 50% (RBI Guardrail). False triggers High Risk override."
    )
    rbi_max_cap: float = Field(
        default=50.0,
        description="RBI mandated maximum FOIR cap for MFI lending (fixed at 50%)"
    )

    # --- Dynamic Risk-Based Pricing Engine Fields ---
    interest_rate_apr: float = Field(
        default=0.0,
        example=12.5,
        description="Approved risk-based Annual Percentage Rate (%)"
    )
    max_loan_limit: float = Field(
        default=0.0,
        example=84000.0,
        description="Maximum sanction limit based on 12-month available surplus capacity"
    )
    estimated_emi: float = Field(
        default=0.0,
        example=4454.89,
        description="Estimated monthly EMI for baseline ₹50,000 loan over 12 months"
    )
