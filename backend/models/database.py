from typing import Generator
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

try:
    from backend.core.config import settings
except ModuleNotFoundError:
    from core.config import settings

# Create SQLAlchemy engine with settings
engine_kwargs = {
    "echo": settings.DEBUG,
}
if "sqlite" in settings.DATABASE_URL:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 3600

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

# Create a configured "SessionLocal" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for SQLAlchemy ORM models
Base = declarative_base()

class FinancialRecord(Base):
    __tablename__ = "financial_records"

    id = Column(Integer, primary_key=True, index=True)
    mobile_number = Column(String(20), unique=True, index=True)
    upi_monthly_inflow = Column(Float)
    weekly_txn_frequency = Column(Integer)
    recharge_regularity_index = Column(Float)
    days_since_last_txn = Column(Integer)
    unique_sender_count = Column(Integer, default=0)
    utility_payment_streak = Column(Integer, default=0)
    is_gig_worker = Column(Boolean, default=False)
    gig_rating = Column(Float, nullable=True, default=None)
    gig_hours_per_week = Column(Integer, nullable=True, default=None)

    # Optional cashflow & gig platform earnings defaults
    monthly_cashflow_avg = Column(Float, nullable=True, default=None)
    gig_platform_earnings = Column(Float, nullable=True, default=None)

    # --- MFI Financial Underwriting Columns (RBI FOIR Compliance) ---
    monthly_household_income = Column(Float, default=20000.0)
    monthly_business_expenses = Column(Float, default=8000.0)
    monthly_household_expenses = Column(Float, default=5000.0)
    existing_monthly_emi = Column(Float, default=1000.0)
    proposed_loan_emi = Column(Float, default=1500.0)


class WorkerConsent(Base):
    __tablename__ = "worker_consents"

    id = Column(String(50), primary_key=True, index=True)
    worker_id = Column(String(50), index=True, nullable=False)
    phone_number = Column(String(20), index=True, nullable=False)
    scope = Column(String(255), default="Income verification for credit assessment")
    granted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class ScoreHistory(Base):
    __tablename__ = "score_history"

    id = Column(Integer, primary_key=True, index=True)
    mobile_number = Column(String(20), index=True)
    credit_score = Column(Integer)
    risk_tier = Column(String(50))
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WorkerMonthlyEvidence(Base):
    """Database-backed monthly UPI evidence for the /verify flow."""

    __tablename__ = "worker_monthly_evidence"
    __table_args__ = (
        UniqueConstraint("worker_id", "year_month", name="uq_worker_monthly_evidence"),
    )

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(String(50), index=True, nullable=False)
    year_month = Column(String(7), nullable=False)
    upi_inflow = Column(Float, nullable=False, default=0.0)
    upi_unique_senders = Column(Integer, nullable=True)


class WorkerRiskProfile(Base):
    """A worker's reference-population risk-model features."""

    __tablename__ = "worker_risk_profiles"

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(String(50), unique=True, index=True, nullable=False)
    features = Column(JSON, nullable=False, default=dict)
    source = Column(String(100), nullable=False, default="self_reported")
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class VerificationResultRecord(Base):
    """Persisted response from the /verify decision-support flow."""

    __tablename__ = "verification_results"

    id = Column(String(50), primary_key=True, index=True)
    worker_id = Column(String(50), index=True, nullable=False)
    consent_id = Column(String(50), index=True, nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session per request
    and ensures proper closing upon completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
