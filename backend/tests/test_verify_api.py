"""Tests for the /verify pipeline, schemas, recommendation rules and API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core import risk_v2
from backend.core.recommendation import (
    INSUFFICIENT_EVIDENCE,
    MANUAL_REVIEW_HIGH_RISK,
    NEEDS_MORE_EVIDENCE,
    NOT_AFFORDABLE_AT_REQUESTED_EMI,
    PROCEED_TO_UNDERWRITING,
    recommend,
)
from backend.core.verification_pipeline import compute_affordability
from backend.main import app
from backend.models.database import (
    Base,
    FinancialRecord,
    WorkerConsent,
    WorkerMonthlyEvidence,
    WorkerRiskProfile,
    get_db,
)
from backend.scripts.demo_verify_pipeline import (
    HIGH_RISK_FEATURES,
    LOW_RISK_FEATURES,
)

PHONE = "+919800000001"
WORKER = "WRK-TEST-001"
CONSENT = "CNS-TEST-001"
INFLOWS = [32000.0, 31500.0, 32800.0, 31200.0, 32500.0, 31800.0]
SENDERS = [14, 13, 15, 14, 16, 15]
MONTHS = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"]
OUTGOINGS = {"food": 7000.0, "rent": 6000.0, "transport": 2000.0, "existing_emi": 1500.0}
FORBIDDEN_KEYS = {
    "interest_rate",
    "apr",
    "loan_limit",
    "max_loan",
    "approved",
    "rejected",
    "eligible",
    "ineligible",
}


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def add_consent(
    db,
    consent_id=CONSENT,
    worker_id=WORKER,
    phone_number=PHONE,
    *,
    revoked=False,
    expired=False,
):
    consent = WorkerConsent(
        id=consent_id,
        worker_id=worker_id,
        phone_number=phone_number,
        scope="Income verification test",
        granted_at=datetime.now(timezone.utc) - timedelta(days=1),
        revoked_at=datetime.now(timezone.utc) if revoked else None,
        expires_at=(
            datetime.now(timezone.utc) - timedelta(hours=1) if expired else None
        ),
    )
    db.add(consent)
    db.commit()
    return consent


def add_record(
    db,
    phone_number=PHONE,
    *,
    aggregate=32000.0,
    sender_count=14,
):
    record = FinancialRecord(
        mobile_number=phone_number,
        upi_monthly_inflow=aggregate,
        weekly_txn_frequency=15,
        recharge_regularity_index=0.9,
        days_since_last_txn=2,
        unique_sender_count=sender_count,
        utility_payment_streak=5,
        is_gig_worker=False,
        monthly_household_income=32000.0,
        monthly_business_expenses=0.0,
        monthly_household_expenses=0.0,
        existing_monthly_emi=1500.0,
        proposed_loan_emi=0.0,
    )
    db.add(record)
    db.commit()
    return record


def add_months(db, worker_id=WORKER, inflows=None):
    for year_month, inflow, senders in zip(
        MONTHS, inflows or INFLOWS, SENDERS
    ):
        db.add(
            WorkerMonthlyEvidence(
                worker_id=worker_id,
                year_month=year_month,
                upi_inflow=inflow,
                upi_unique_senders=senders,
            )
        )
    db.commit()


def add_profile(db, worker_id=WORKER, features=None):
    profile = WorkerRiskProfile(
        worker_id=worker_id,
        features=dict(features or LOW_RISK_FEATURES),
        source="test_profile",
    )
    db.add(profile)
    db.commit()
    return profile


def payload(**overrides):
    data = {
        "worker_id": WORKER,
        "consent_id": CONSENT,
        "phone_number": PHONE,
        "stated_monthly_income": 32000.0,
        "monthly_outgoings": OUTGOINGS,
        "household_size": 4,
        "occupation_type": "Test worker",
        "proposed_emi": 1000.0,
        "tenure_months": 24,
    }
    data.update(overrides)
    return data


def seed_full(db, *, risk_features=None, add_risk=True):
    add_consent(db)
    add_record(db)
    add_months(db)
    if add_risk:
        add_profile(db, features=risk_features)


def assert_no_forbidden_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            assert key.lower() not in FORBIDDEN_KEYS, f"forbidden response key: {key}"
            assert_no_forbidden_keys(nested)
    elif isinstance(value, list):
        for item in value:
            assert_no_forbidden_keys(item)


def fake_evidence(**overrides):
    data = {
        "flags": [],
        "evidence_confidence_level": "HIGH",
        "evidence_confidence_score": 95,
        "expenses_complete": True,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


# ---------------------------------------------------------------------------
# Recommendation rules (priority order)
# ---------------------------------------------------------------------------
def test_recommendation_no_evidence_wins_first():
    result = recommend(
        fake_evidence(flags=[{"code": "NO_EVIDENCE"}], evidence_confidence_level="LOW"),
        {"available": False},
        {"proposed_emi": 999999, "max_affordable_emi": 1},
    )
    assert result["code"] == INSUFFICIENT_EVIDENCE


def test_recommendation_low_confidence_needs_more_evidence():
    result = recommend(
        fake_evidence(evidence_confidence_level="LOW"),
        {"available": True, "band": "LOW"},
        {"proposed_emi": 1000, "max_affordable_emi": 5000},
    )
    assert result["code"] == NEEDS_MORE_EVIDENCE


def test_recommendation_stated_overstated_needs_more_evidence():
    result = recommend(
        fake_evidence(
            flags=[
                {
                    "code": "STATED_OVERSTATED",
                    "message": "Stated income exceeds evidence.",
                }
            ]
        ),
        {"available": True, "band": "LOW"},
        {"proposed_emi": 1000, "max_affordable_emi": 5000},
    )
    assert result["code"] == NEEDS_MORE_EVIDENCE
    assert result["reasons"] == ["Stated income exceeds evidence."]


def test_recommendation_unavailable_risk_needs_more_evidence():
    result = recommend(
        fake_evidence(),
        {"available": False, "reason": "No risk profile."},
        {"proposed_emi": 1000, "max_affordable_emi": 5000},
    )
    assert result["code"] == NEEDS_MORE_EVIDENCE
    assert result["reasons"] == ["No risk profile."]


def test_recommendation_unaffordable_emi_wins_before_high_band():
    result = recommend(
        fake_evidence(),
        {"available": True, "band": "HIGH"},
        {"proposed_emi": 5000, "max_affordable_emi": 4999.99},
    )
    assert result["code"] == NOT_AFFORDABLE_AT_REQUESTED_EMI


def test_recommendation_high_band_manual_review():
    result = recommend(
        fake_evidence(),
        {"available": True, "band": "HIGH"},
        {"proposed_emi": 1000, "max_affordable_emi": 5000},
    )
    assert result["code"] == MANUAL_REVIEW_HIGH_RISK


def test_recommendation_proceed_adds_caveats():
    result = recommend(
        fake_evidence(
            evidence_confidence_level="MEDIUM",
            expenses_complete=False,
            flags=[{"code": "SINGLE_SOURCE"}],
        ),
        {"available": True, "band": "LOW", "reliability": "LIMITED"},
        {
            "proposed_emi": 1000,
            "max_affordable_emi": 5000,
            "sms_provenance": "client_supplied_unverified",
        },
    )
    assert result["code"] == PROCEED_TO_UNDERWRITING
    assert len(result["caveats"]) == 5


# ---------------------------------------------------------------------------
# Affordability
# ---------------------------------------------------------------------------
def test_affordability_uses_conservative_income_and_takes_stricter_bound():
    evidence = SimpleNamespace(
        income_low=20000.0,
        monthly_surplus_conservative=4500.0,
    )
    result = compute_affordability(
        evidence, {"existing_emi": 1000.0, "food": 5000.0}, 1000.0, 0.5
    )
    assert result["max_affordable_emi"] == 4500.0
    assert result["foir_current"] == 0.05
    assert result["foir_with_proposed"] == 0.1


def test_affordability_none_when_no_verified_income():
    evidence = SimpleNamespace(income_low=None, monthly_surplus_conservative=None)
    result = compute_affordability(evidence, {}, 1000.0, 0.5)
    assert result["max_affordable_emi"] is None
    assert result["foir_current"] is None
    assert result["foir_with_proposed"] is None


# ---------------------------------------------------------------------------
# Request schema protections
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "field,value",
    [
        ("upi_monthly_inflows", [999999]),
        ("model_features", {"late_share": 0.0}),
        ("late_share", 0.0),
    ],
)
def test_request_rejects_client_evidence_and_model_overrides(client, field, value):
    response = client.post("/api/v1/verify", json=payload(**{field: value}))
    assert response.status_code == 422


def test_request_rejects_negative_outgoing(client, db_session):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify",
        json=payload(monthly_outgoings={"food": -1.0}),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Consent and lookup failures
# ---------------------------------------------------------------------------
def test_verify_missing_consent_returns_403(client, db_session):
    seed_full(db_session)
    body = payload()
    body.pop("consent_id")
    response = client.post("/api/v1/verify", json=body)
    assert response.status_code == 403
    assert "consent_id" in response.json()["detail"].lower()


def test_verify_unknown_consent_returns_403(client, db_session):
    seed_full(db_session)
    response = client.post("/api/v1/verify", json=payload(consent_id="CNS-NOT-REAL"))
    assert response.status_code == 403
    assert "unknown consent_id" in response.json()["detail"].lower()


def test_verify_revoked_consent_returns_403(client, db_session):
    add_consent(db_session, revoked=True)
    add_record(db_session)
    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 403
    assert "revoked" in response.json()["detail"].lower()


def test_verify_missing_worker_record_returns_404(client, db_session):
    add_consent(db_session)
    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 404


def test_verify_returns_503_when_risk_artifacts_unavailable(
    client, db_session, monkeypatch
):
    seed_full(db_session)
    monkeypatch.setattr(risk_v2, "is_loaded", lambda: False)
    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Successful pipeline behaviour
# ---------------------------------------------------------------------------
def test_verify_success_shape_and_safety(client, db_session):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify",
        json=payload(sms_log=["Rs.5,000 credited via UPI on 01-01-2025"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification_id"].startswith("VRF-")
    assert body["worker_id"] == WORKER
    assert body["consent_id"] == CONSENT
    assert body["evidence"]["months"] == 6
    assert body["risk_signal"]["available"] is True
    assert body["risk_signal"]["band"] in {"LOW", "MEDIUM", "HIGH"}
    assert body["recommendation"]["code"] == PROCEED_TO_UNDERWRITING
    assert "does not set interest rates" in body["disclaimer"]
    assert_no_forbidden_keys(body)


def test_verify_uses_stored_monthly_evidence_not_record_aggregate(client, db_session):
    add_consent(db_session)
    add_record(db_session, aggregate=900000.0)
    add_months(db_session, inflows=[20000.0] * 6)
    add_profile(db_session)
    response = client.post(
        "/api/v1/verify",
        json=payload(stated_monthly_income=20000.0),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["income"]["mid"] < 20000.0
    assert body["evidence"]["provenance"]["upi"] == "database"
    assert body["evidence"]["months"] == 6


def test_verify_sms_is_ignored_without_dates(client, db_session):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify",
        json=payload(
            sms_log=[
                "Rs.10,000 credited via UPI on 01-01-2025",
                "Rs.9,000 credited via UPI on 01-02-2025",
            ]
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"]["provenance"]["sms"] == "ignored_no_dates"
    assert "parser" in body["sms_ignored_reason"]
    assert body["evidence"]["months"] == 6


def test_verify_aggregate_fallback_is_labelled_and_triggers_short_history(
    client, db_session
):
    add_consent(db_session)
    add_record(db_session)
    add_profile(db_session)
    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"]["months"] == 1
    assert body["evidence"]["provenance"]["upi"] == "database"
    assert any("fallback" in reason.lower() for reason in body["evidence"]["reasons"])
    assert any(flag["code"] == "SHORT_HISTORY" for flag in body["evidence"]["flags"])


def test_verify_no_evidence_is_insufficient_with_no_affordability(
    client, db_session
):
    add_consent(db_session)
    add_record(db_session, aggregate=None, sender_count=None)
    add_profile(db_session)
    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"]["code"] == INSUFFICIENT_EVIDENCE
    assert body["income"]["low"] is None
    assert body["affordability"]["max_affordable_emi"] is None


def test_verify_no_risk_profile_returns_unavailable_signal(client, db_session):
    seed_full(db_session, add_risk=False)
    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["risk_signal"]["available"] is False
    assert body["risk_signal"]["reason"]
    assert body["recommendation"]["code"] == NEEDS_MORE_EVIDENCE


def test_verify_high_risk_profile_recommends_manual_review(client, db_session):
    seed_full(db_session, risk_features=HIGH_RISK_FEATURES)
    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["risk_signal"]["band"] == "HIGH"
    assert body["recommendation"]["code"] == MANUAL_REVIEW_HIGH_RISK


def test_verify_overstated_income_needs_more_evidence(client, db_session):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify",
        json=payload(stated_monthly_income=90000.0),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"]["confidence_level"] == "MEDIUM"
    assert body["recommendation"]["code"] == NEEDS_MORE_EVIDENCE


def test_verify_low_confidence_needs_more_evidence(client, db_session):
    add_consent(db_session)
    add_record(db_session, sender_count=None)
    add_profile(db_session)
    response = client.post(
        "/api/v1/verify",
        json=payload(stated_monthly_income=None),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"]["confidence_level"] == "LOW"
    assert body["recommendation"]["code"] == NEEDS_MORE_EVIDENCE


def test_verify_requested_emi_above_affordability(client, db_session):
    seed_full(db_session)
    response = client.post("/api/v1/verify", json=payload(proposed_emi=50000.0))
    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"]["code"] == NOT_AFFORDABLE_AT_REQUESTED_EMI


# ---------------------------------------------------------------------------
# Stored verification retrieval
# ---------------------------------------------------------------------------
def test_get_stored_verification_round_trip(client, db_session):
    seed_full(db_session)
    created = client.post("/api/v1/verify", json=payload()).json()
    response = client.get(
        f"/api/v1/verify/{created['verification_id']}",
        params={"consent_id": CONSENT},
    )
    assert response.status_code == 200
    assert response.json() == created


def test_get_stored_verification_requires_consent(client, db_session):
    seed_full(db_session)
    created = client.post("/api/v1/verify", json=payload()).json()
    response = client.get(f"/api/v1/verify/{created['verification_id']}")
    assert response.status_code == 403


def test_get_stored_verification_rejects_other_workers_consent(client, db_session):
    seed_full(db_session)
    add_consent(
        db_session,
        consent_id="CNS-OTHER",
        worker_id="WRK-OTHER",
        phone_number="+919800000002",
    )
    created = client.post("/api/v1/verify", json=payload()).json()
    response = client.get(
        f"/api/v1/verify/{created['verification_id']}",
        params={"consent_id": "CNS-OTHER"},
    )
    assert response.status_code == 403


def test_get_unknown_verification_returns_404(client, db_session):
    add_consent(db_session)
    response = client.get(
        "/api/v1/verify/VRF-DOES-NOT-EXIST",
        params={"consent_id": CONSENT},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
def test_health_reports_risk_v2_status(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["risk_v2"]["loaded"] is True
    assert "error" in body["risk_v2"]
