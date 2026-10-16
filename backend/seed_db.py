from backend.models.database import engine, Base, SessionLocal, FinancialRecord, ScoreHistory

def seed_db():
    print("Dropping existing tables to apply schema changes...")
    Base.metadata.drop_all(bind=engine)
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)

    print("Seeding demo personas...")
    db = SessionLocal()
    
    personas = [
        # Good Vendor — FOIR = (1000+2000)/25000 = 12% (Compliant)
        FinancialRecord(
            mobile_number="9876543210",
            upi_monthly_inflow=50000.0,
            weekly_txn_frequency=15,
            recharge_regularity_index=0.9,
            days_since_last_txn=1,
            unique_sender_count=45,
            utility_payment_streak=6,
            is_gig_worker=False,
            monthly_household_income=25000.0,
            monthly_business_expenses=10000.0,
            monthly_household_expenses=5000.0,
            existing_monthly_emi=1000.0,
            proposed_loan_emi=2000.0,
        ),
        # Over-Indebted / High Risk — FOIR = (6500+2000)/15000 = 56.6% (EXCEEDS 50% RBI FOIR CAP)
        FinancialRecord(
            mobile_number="9998887776",
            upi_monthly_inflow=10000.0,
            weekly_txn_frequency=2,
            recharge_regularity_index=0.2,
            days_since_last_txn=14,
            unique_sender_count=3,
            utility_payment_streak=0,
            is_gig_worker=False,
            monthly_household_income=15000.0,
            monthly_business_expenses=6000.0,
            monthly_household_expenses=4000.0,
            existing_monthly_emi=6500.0,
            proposed_loan_emi=2000.0,
        ),
        # Fraudster — FOIR = (1500+2000)/22000 = 15.9% (Compliant on FOIR, flagged by graph layer)
        FinancialRecord(
            mobile_number="1112223334",
            upi_monthly_inflow=80000.0,
            weekly_txn_frequency=50,  # High volume, designed to trigger the fraud penalty
            recharge_regularity_index=1.0,
            days_since_last_txn=0,
            unique_sender_count=2,
            utility_payment_streak=1,
            is_gig_worker=False,
            monthly_household_income=22000.0,
            monthly_business_expenses=9000.0,
            monthly_household_expenses=5000.0,
            existing_monthly_emi=1500.0,
            proposed_loan_emi=2000.0,
        ),
        # Reliable Gig Driver — FOIR = (2000+3000)/30000 = 16.6% (Compliant)
        FinancialRecord(
            mobile_number="5556667777",
            upi_monthly_inflow=45000.0,
            weekly_txn_frequency=25,
            recharge_regularity_index=0.8,
            days_since_last_txn=2,
            unique_sender_count=15,
            utility_payment_streak=12,
            is_gig_worker=True,
            gig_rating=4.8,
            gig_hours_per_week=50,
            monthly_household_income=30000.0,
            monthly_business_expenses=8000.0,
            monthly_household_expenses=8000.0,
            existing_monthly_emi=2000.0,
            proposed_loan_emi=3000.0,
        ),
    ]
    
    db.add_all(personas)
    db.commit()
    db.close()
    
    print("Database seeded successfully.")

if __name__ == "__main__":
    seed_db()
