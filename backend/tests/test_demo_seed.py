"""Tests for deterministic demo persona selection and database seeding."""

from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.core.verification_pipeline import run_verification
from backend.models.database import (
    Base,
    FinancialRecord,
    VerificationResultRecord,
    WorkerRiskProfile,
)
from backend.schemas.verification import VerifyRequest
from backend.scripts.seed_demo_workers import (
    DEMO_RISK_SOURCE,
    FEATURES_PATH,
    HISTORY_FLAGS,
    PERSONA_HIGH_RISK_WITH_HISTORY,
    PERSONA_LOW_BAND_LIMITED,
    PERSONA_LOW_RISK_FULL,
    PERSONA_MEDIUM_RISK,
    PERSONA_NO_CREDIT_HISTORY,
    PERSONA_ORDER,
    PREDICTIONS_PATH,
    main,
    mask_database_url,
    select_personas,
)

REAL_DATA_AVAILABLE = PREDICTIONS_PATH.exists() and FEATURES_PATH.exists()
REAL_DATA_SKIP = pytest.mark.skipif(
    not REAL_DATA_AVAILABLE,
    reason=(
        "Local git-ignored Home Credit parquet files are absent; refusing to "
        "substitute real data."
    ),
)


def made_up_frame(*, include_target=False):
    rows = [
        {
            "SK_ID_CURR": 1,
            "band": "LOW",
            "calibrated_pd": 0.02,
            "has_installment_history": 1,
            "has_bureau_history": 1,
            "has_prev_application": 1,
            "credit_term_months": 12.0,
        },
        {
            "SK_ID_CURR": 2,
            "band": "LOW",
            "calibrated_pd": 0.04,
            "has_installment_history": 1,
            "has_bureau_history": 1,
            "has_prev_application": 1,
            "credit_term_months": 18.0,
        },
        {
            "SK_ID_CURR": 3,
            "band": "LOW",
            "calibrated_pd": 0.03,
            "has_installment_history": 1,
            "has_bureau_history": 0,
            "has_prev_application": 1,
            "credit_term_months": 24.0,
        },
        {
            "SK_ID_CURR": 4,
            "band": "LOW",
            "calibrated_pd": 0.05,
            "has_installment_history": 0,
            "has_bureau_history": 1,
            "has_prev_application": 1,
            "credit_term_months": 24.0,
        },
        {
            "SK_ID_CURR": 5,
            "band": "MEDIUM",
            "calibrated_pd": 0.10,
            "has_installment_history": 1,
            "has_bureau_history": 1,
            "has_prev_application": 1,
            "credit_term_months": 24.0,
        },
        {
            "SK_ID_CURR": 6,
            "band": "HIGH",
            "calibrated_pd": 0.20,
            "has_installment_history": 1,
            "has_bureau_history": 1,
            "has_prev_application": 1,
            "credit_term_months": 24.0,
        },
        {
            "SK_ID_CURR": 7,
            "band": "HIGH",
            "calibrated_pd": 0.15,
            "has_installment_history": 0,
            "has_bureau_history": 0,
            "has_prev_application": 0,
            "credit_term_months": 24.0,
        },
    ]
    frame = pd.DataFrame(rows)
    if include_target:
        frame["TARGET"] = [1, 0, 1, 0, 1, 0, 1]
    return frame


def test_persona_selection_is_deterministic_and_uses_all_five_personas():
    frame = made_up_frame()
    first = select_personas(frame)
    second = select_personas(frame)
    assert first == second
    assert set(first) == set(PERSONA_ORDER)
    assert first[PERSONA_LOW_RISK_FULL]["band"] == "LOW"
    assert first[PERSONA_LOW_RISK_FULL]["SK_ID_CURR"] == 2
    assert first[PERSONA_MEDIUM_RISK]["band"] == "MEDIUM"
    assert first[PERSONA_HIGH_RISK_WITH_HISTORY]["band"] == "HIGH"
    assert first[PERSONA_LOW_BAND_LIMITED]["band"] == "LOW"


def test_persona_selection_is_independent_of_target_column():
    base = select_personas(made_up_frame())
    with_target = select_personas(made_up_frame(include_target=True))
    assert base == with_target


def test_no_history_persona_has_all_home_credit_flags_zero():
    selected = select_personas(made_up_frame())[PERSONA_NO_CREDIT_HISTORY]
    assert all(selected[flag] == 0 for flag in HISTORY_FLAGS)


def test_limited_history_persona_is_low_band_with_a_missing_flag():
    selected = select_personas(made_up_frame())[PERSONA_LOW_BAND_LIMITED]
    assert selected["band"] == "LOW"
    assert 0 < sum(selected[flag] for flag in HISTORY_FLAGS) < len(HISTORY_FLAGS)


def test_password_masking_hides_the_password():
    masked = mask_database_url(
        "postgresql://icver:supersecret@db.example/icver_db"
    )
    assert "supersecret" not in masked
    assert "***" in masked
    assert "icver" in masked


def test_seed_refuses_a_production_looking_url_without_touching_the_file(
    tmp_path, capsys
):
    database_path = tmp_path / "production.db"
    code = main(
        [
            "--database-url",
            f"sqlite:///{database_path}",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "Refusing to run" in captured.out
    assert not database_path.exists()


def test_missing_parquet_files_exit_with_a_clear_message(monkeypatch, capsys):
    from backend.scripts import seed_demo_workers

    monkeypatch.setattr(
        seed_demo_workers,
        "PREDICTIONS_PATH",
        seed_demo_workers.PREDICTIONS_PATH.with_name("missing_predictions.parquet"),
    )
    code = main(["--dry-run"])
    captured = capsys.readouterr()
    assert code == 1
    assert "Missing local held-out data file" in captured.out


@REAL_DATA_SKIP
def test_seeding_twice_is_idempotent_and_preserves_non_demo_rows(tmp_path):
    database_path = tmp_path / "demo_seed.db"
    database_url = f"sqlite:///{database_path}"
    engine = create_engine(
        database_url, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(
        FinancialRecord(
            mobile_number="+919999999999",
            upi_monthly_inflow=12345.0,
            unique_sender_count=3,
        )
    )
    session.commit()
    session.close()
    engine.dispose()

    assert main(["--database-url", database_url]) == 0
    assert main(["--database-url", database_url]) == 0

    engine = create_engine(
        database_url, connect_args={"check_same_thread": False}
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        non_demo = (
            session.query(FinancialRecord)
            .filter(FinancialRecord.mobile_number == "+919999999999")
            .one()
        )
        assert non_demo.upi_monthly_inflow == 12345.0

        counts = {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }
        assert counts["financial_records"] == 6
        assert counts["worker_consents"] == 5
        assert counts["worker_risk_profiles"] == 5
        assert counts["verification_results"] == 0

        profile = (
            session.query(WorkerRiskProfile)
            .filter_by(worker_id="demo-low_risk_full_history")
            .one()
        )
        assert profile.source == DEMO_RISK_SOURCE
        response = run_verification(
            session,
            VerifyRequest(
                worker_id="demo-low_risk_full_history",
                consent_id="demo-consent-low_risk_full_history",
                phone_number="+919000000001",
            ),
            persist=False,
        )
        assert response.data_notice.startswith("Demonstration worker:")
        assert (
            session.query(VerificationResultRecord).count() == 0
        )
    finally:
        session.close()
        engine.dispose()
