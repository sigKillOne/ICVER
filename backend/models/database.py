from typing import Generator
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session

try:
    from backend.core.config import settings
except ModuleNotFoundError:
    from core.config import settings

# Create SQLAlchemy engine for MariaDB/MySQL using PyMySQL
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

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

    # --- MFI Financial Underwriting Columns (RBI FOIR Compliance) ---
    monthly_household_income = Column(Float, default=20000.0)
    monthly_business_expenses = Column(Float, default=8000.0)
    monthly_household_expenses = Column(Float, default=5000.0)
    existing_monthly_emi = Column(Float, default=1000.0)
    proposed_loan_emi = Column(Float, default=1500.0)


class ScoreHistory(Base):
    __tablename__ = "score_history"

    id = Column(Integer, primary_key=True, index=True)
    mobile_number = Column(String(20), index=True)
    credit_score = Column(Integer)
    risk_tier = Column(String(50))
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


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
