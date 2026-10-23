"""Demo the /verify pipeline directly against an in-memory SQLite database.

All five workers and their evidence are clearly labelled, made-up illustrative data.
No HTTP server is started.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.verification_pipeline import run_verification
from backend.models.database import (
    Base,
    FinancialRecord,
    WorkerConsent,
    WorkerMonthlyEvidence,
    WorkerRiskProfile,
)
from backend.schemas.verification import VerifyRequest

LOW_RISK_FEATURES = {
    "credit_term_months": 24,
    "years_employed": 8,
    "days_employed_anomaly": 0,
    "days_since_phone_change": 500,
    "years_since_id_published": 10,
    "years_registered": 10,
    "cnt_children": 2,
    "cnt_fam_members": 4,
    "n_prev_loans": 2,
    "n_installments": 24,
    "late_share": 0.0,
    "underpaid_share": 0.0,
    "mean_days_late": 0.0,
    "max_days_late": 0.0,
    "missing_payment_share": 0.0,
    "recent_late_share": 0.0,
    "has_installment_history": 1,
    "bureau_n_credits": 4,
    "bureau_n_active": 1,
    "bureau_max_days_overdue": 0,
    "has_bureau_history": 1,
    "prev_n_apps": 2,
    "prev_refused_share": 0.0,
    "has_prev_application": 1,
}

HIGH_RISK_FEATURES = {
    "credit_term_months": 12,
    "years_employed": 0.5,
    "days_employed_anomaly": 1,
    "days_since_phone_change": 5,
    "years_since_id_published": 0.2,
    "years_registered": 0.2,
    "cnt_children": 4,
    "cnt_fam_members": 7,
    "n_prev_loans": 10,
    "n_installments": 10,
    "late_share": 0.7,
    "underpaid_share": 0.8,
    "mean_days_late": 45.0,
    "max_days_late": 400.0,
    "missing_payment_share": 0.4,
    "recent_late_share": 0.9,
    "has_installment_history": 1,
    "bureau_n_credits": 10,
    "bureau_n_active": 8,
    "bureau_max_days_overdue": 180,
    "has_bureau_history": 1,
    "prev_n_apps": 15,
    "prev_refused_share": 0.9,
    "has_prev_application": 1,
}

MONTHS = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"]
CONSISTENT_INFLOWS = [32000.0, 31500.0, 32800.0, 31200.0, 32500.0, 31800.0]
CONSISTENT_SENDERS = [14, 13, 15, 14, 16, 15]
OUTGOINGS = {
    "food": 7000.0,
    "rent": 6000.0,
    "transport": 2000.0,
    "existing_emi": 1500.0,
}


def _seed_worker(
    db,
    worker_id: str,
    consent_id: str,
    phone: str,
    *,
    monthly_evidence: bool,
    risk_features: dict | None,
    stated_income: float | None = 32000.0,
):
    db.add(
        WorkerConsent(
            id=consent_id,
            worker_id=worker_id,
            phone_number=phone,
            scope="Income verification for demonstration",
            granted_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        FinancialRecord(
            mobile_number=phone,
            upi_monthly_inflow=sum(CONSISTENT_INFLOWS) / len(CONSISTENT_INFLOWS)
            if monthly_evidence
            else None,
            weekly_txn_frequency=15 if monthly_evidence else 0,
            recharge_regularity_index=0.9 if monthly_evidence else 0.0,
            days_since_last_txn=2,
            unique_sender_count=14 if monthly_evidence else 0,
            utility_payment_streak=5,
            is_gig_worker=False,
            monthly_household_income=stated_income,
            monthly_business_expenses=0.0,
            monthly_household_expenses=0.0,
            existing_monthly_emi=OUTGOINGS["existing_emi"],
            proposed_loan_emi=0.0,
        )
    )
    if monthly_evidence:
        for year_month, inflow, senders in zip(
            MONTHS, CONSISTENT_INFLOWS, CONSISTENT_SENDERS
        ):
            db.add(
                WorkerMonthlyEvidence(
                    worker_id=worker_id,
                    year_month=year_month,
                    upi_inflow=inflow,
                    upi_unique_senders=senders,
                )
            )
    if risk_features is not None:
        db.add(
            WorkerRiskProfile(
                worker_id=worker_id,
                features=dict(risk_features),
                source="demo_illustrative_profile",
            )
        )
    db.commit()


def main() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    scenarios = [
        (
            "1. Consistent evidence + good risk profile",
            "WRK-DEMO-GOOD",
            "CNS-DEMO-GOOD",
            "+919000000001",
            True,
            LOW_RISK_FEATURES,
            32000.0,
            2000.0,
        ),
        (
            "2. Overstated stated income",
            "WRK-DEMO-OVERSTATED",
            "CNS-DEMO-OVERSTATED",
            "+919000000002",
            True,
            LOW_RISK_FEATURES,
            90000.0,
            1000.0,
        ),
        (
            "3. No evidence",
            "WRK-DEMO-NO-EVIDENCE",
            "CNS-DEMO-NO-EVIDENCE",
            "+919000000003",
            False,
            LOW_RISK_FEATURES,
            30000.0,
            1000.0,
        ),
        (
            "4. High-risk profile",
            "WRK-DEMO-HIGH-RISK",
            "CNS-DEMO-HIGH-RISK",
            "+919000000004",
            True,
            HIGH_RISK_FEATURES,
            32000.0,
            1000.0,
        ),
        (
            "5. Worker with no risk profile",
            "WRK-DEMO-NO-RISK",
            "CNS-DEMO-NO-RISK",
            "+919000000005",
            True,
            None,
            32000.0,
            1000.0,
        ),
    ]

    rows = []
    try:
        for label, worker_id, consent_id, phone, has_evidence, risk, stated, emi in scenarios:
            _seed_worker(
                db,
                worker_id,
                consent_id,
                phone,
                monthly_evidence=has_evidence,
                risk_features=risk,
                stated_income=stated,
            )
            request = VerifyRequest(
                worker_id=worker_id,
                consent_id=consent_id,
                phone_number=phone,
                stated_monthly_income=stated,
                monthly_outgoings=OUTGOINGS,
                household_size=4,
                occupation_type="Made-up demo worker",
                proposed_emi=emi,
                tenure_months=24,
            )
            result = run_verification(db, request)
            max_emi = result.affordability.max_affordable_emi
            rows.append(
                (
                    label,
                    result.recommendation.code,
                    result.evidence.confidence_level,
                    result.risk_signal.band or "n/a",
                    result.risk_signal.reliability or "n/a",
                    f"{max_emi:,.2f}" if max_emi is not None else "n/a",
                )
            )
    finally:
        db.close()

    headers = (
        "scenario",
        "recommendation",
        "confidence",
        "risk band",
        "reliability",
        "max affordable EMI",
    )
    widths = [max(len(str(row[i])) for row in [headers, *rows]) for i in range(5)]
    print(
        f"{headers[0]:<{widths[0]}}  {headers[1]:<32}  {headers[2]:<10}  "
        f"{headers[3]:<9}  {headers[4]:<11}  {headers[5]}"
    )
    print("-" * (sum(widths) + 75))
    for row in rows:
        print(
            f"{row[0]:<{widths[0]}}  {row[1]:<32}  {row[2]:<10}  "
            f"{row[3]:<9}  {row[4]:<11}  {row[5]}"
        )
    print("\nAll workers, amounts and profiles above are made-up demonstration data.")


if __name__ == "__main__":
    main()
