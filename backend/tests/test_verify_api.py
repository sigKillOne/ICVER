"""Tests for the /verify pipeline, schemas, recommendation rules and API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core import risk_v2
from backend.core.verification_pipeline import _subtract_months
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
    VerificationResultRecord,
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


def add_months(
    db,
    worker_id=WORKER,
    inflows=None,
    *,
    months=None,
    senders=None,
):
    for year_month, inflow, sender_count in zip(
        months or MONTHS,
        inflows or INFLOWS,
        senders or SENDERS,
    ):
        db.add(
            WorkerMonthlyEvidence(
                worker_id=worker_id,
                year_month=year_month,
                upi_inflow=inflow,
                upi_unique_senders=sender_count,
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


IST = ZoneInfo("Asia/Kolkata")


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


def what_if_payload(**overrides):
    data = {
        "worker_id": WORKER,
        "consent_id": CONSENT,
        "phone_number": PHONE,
    }
    data.update(overrides)
    return data


def recent_month_keys(count=6):
    """Complete past months, excluding the current (possibly partial) month."""
    current_month = datetime.now(IST).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return [
        _subtract_months(current_month, offset).strftime("%Y-%m")
        for offset in reversed(range(1, count + 1))
    ]


def sms_item(text, when):
    return {"text": text, "received_at": when.isoformat()}


def seed_recent_upi(db, *, inflow=32000.0, senders=14):
    months = recent_month_keys(6)
    add_months(
        db,
        inflows=[inflow] * 6,
        months=months,
        senders=[senders] * 6,
    )
    return months


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


def test_recommendation_unavailable_risk_uses_evidence_and_affordability():
    result = recommend(
        fake_evidence(),
        {"available": False, "reason": "No risk profile."},
        {"proposed_emi": 1000, "max_affordable_emi": 5000},
    )
    assert result["code"] == PROCEED_TO_UNDERWRITING
    assert any(
        "No credit-history profile available" in caveat
        for caveat in result["caveats"]
    )


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
    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["verification_id"].startswith("VRF-")
    assert body["worker_id"] == WORKER
    assert body["consent_id"] == CONSENT
    assert body["evidence"]["months"] == 6
    assert body["risk_signal"]["available"] is True
    assert body["risk_signal"]["band"] in {"LOW", "MEDIUM", "HIGH"}
    assert body["risk_signal"]["display_priority"] == "primary"
    assert body["recommendation"]["code"] == PROCEED_TO_UNDERWRITING
    assert body["sms_summary"]["received"] == 0
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


def test_verify_sms_used_alongside_database_upi(client, db_session):
    add_consent(db_session)
    add_record(db_session)
    months = seed_recent_upi(db_session)
    add_profile(db_session)
    month = months[-1]
    received_at = datetime.strptime(month, "%Y-%m").replace(
        day=10, hour=12, tzinfo=IST
    )
    response = client.post(
        "/api/v1/verify",
        json=payload(
            sms_log=[sms_item("Rs.10,000 credited via UPI", received_at)]
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"]["provenance"]["sms"] == "client_supplied_unverified"
    assert body["sms_ignored_reason"] is None
    assert body["sms_summary"]["used"] == 1
    assert body["sms_summary"]["monthly_credits"][month] == 10000.0
    assert body["evidence"]["months"] == 6
    assert any(
        flag["code"] == "UNVERIFIED_SMS"
        for flag in body["evidence"]["flags"]
    )
    assert not any(
        flag["code"] == "SOURCES_DISAGREE"
        for flag in body["evidence"]["flags"]
    )


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


def test_verify_no_risk_profile_proceeds_with_caveat(client, db_session):
    seed_full(db_session, add_risk=False)
    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["risk_signal"]["available"] is False
    assert body["risk_signal"]["reason"]
    assert body["risk_signal"]["display_priority"] == "secondary"
    assert body["recommendation"]["code"] == PROCEED_TO_UNDERWRITING
    assert any(
        "No credit-history profile available" in caveat
        for caveat in body["recommendation"]["caveats"]
    )


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
# SMS evidence: request validation
# ---------------------------------------------------------------------------
def test_plain_string_sms_item_returns_clear_422(client, db_session):
    seed_full(db_session)
    sentinel = "RAW-ERROR-SENTINEL-9876543210"
    response = client.post(
        "/api/v1/verify",
        json=payload(sms_log=[f"{sentinel} Rs.500 credited via UPI"]),
    )
    assert response.status_code == 422
    detail = str(response.json())
    assert "object" in detail
    assert "received_at" in detail
    assert sentinel not in response.text


def test_sms_text_longer_than_500_chars_rejected(client, db_session):
    seed_full(db_session)
    sentinel = "RAW-ERROR-SENTINEL-123456789012"
    response = client.post(
        "/api/v1/verify",
        json=payload(
            sms_log=[
                sms_item(
                    sentinel + " Rs.500 credited " + ("x" * 500),
                    datetime.now(timezone.utc) - timedelta(days=1),
                )
            ]
        ),
    )
    assert response.status_code == 422
    assert sentinel not in response.text


def test_more_than_300_sms_messages_rejected(client, db_session):
    seed_full(db_session)
    when = datetime.now(timezone.utc) - timedelta(days=1)
    response = client.post(
        "/api/v1/verify",
        json=payload(sms_log=[sms_item("Rs.500 credited", when)] * 301),
    )
    assert response.status_code == 422
    assert "at most 300" in str(response.json())


# ---------------------------------------------------------------------------
# SMS evidence: dropping, deduplication and counting
# ---------------------------------------------------------------------------
def test_future_sms_is_dropped_and_counted(client, db_session):
    seed_full(db_session)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    response = client.post(
        "/api/v1/verify",
        json=payload(sms_log=[sms_item("Rs.500 credited via UPI", future)]),
    )
    assert response.status_code == 200
    summary = response.json()["sms_summary"]
    assert summary["received"] == 1
    assert summary["used"] == 0
    assert summary["dropped_by_reason"]["future_received_at"] == 1
    assert response.json()["sms_ignored_reason"]


def test_sms_older_than_12_months_is_dropped_and_counted(client, db_session):
    seed_full(db_session)
    old = _subtract_months(datetime.now(timezone.utc), 13)
    response = client.post(
        "/api/v1/verify",
        json=payload(sms_log=[sms_item("Rs.500 credited via UPI", old)]),
    )
    assert response.status_code == 200
    summary = response.json()["sms_summary"]
    assert summary["received"] == 1
    assert summary["used"] == 0
    assert summary["dropped_by_reason"]["older_than_12_months"] == 1


def test_debit_and_unparseable_sms_are_ignored_and_counted(client, db_session):
    seed_full(db_session)
    when = datetime.strptime(recent_month_keys(1)[0], "%Y-%m").replace(
        day=10, hour=12, tzinfo=IST
    )
    response = client.post(
        "/api/v1/verify",
        json=payload(
            sms_log=[
                sms_item("Rs.500 debited from A/c XX1234", when),
                sms_item("Your OTP is 123456", when),
            ]
        ),
    )
    assert response.status_code == 200
    body = response.json()
    summary = body["sms_summary"]
    assert summary["received"] == 2
    assert summary["used"] == 0
    assert summary["dropped_by_reason"]["debit"] == 1
    assert summary["dropped_by_reason"]["unparseable"] == 1
    assert body["sms_ignored_reason"]


def test_duplicate_sms_is_counted_once(client, db_session):
    add_consent(db_session)
    add_record(db_session)
    months = seed_recent_upi(db_session)
    add_profile(db_session)
    when = datetime.strptime(months[-1], "%Y-%m").replace(
        day=10, hour=12, tzinfo=IST
    )
    item = sms_item("Rs.12,000 credited via UPI", when)
    response = client.post("/api/v1/verify", json=payload(sms_log=[item, item]))
    assert response.status_code == 200
    summary = response.json()["sms_summary"]
    assert summary["received"] == 2
    assert summary["used"] == 1
    assert summary["dropped_by_reason"]["duplicate"] == 1
    assert summary["monthly_credits"][months[-1]] == 12000.0


def test_sms_summary_counts_add_up(client, db_session):
    add_consent(db_session)
    add_record(db_session)
    months = seed_recent_upi(db_session)
    add_profile(db_session)
    when = datetime.strptime(months[-1], "%Y-%m").replace(
        day=10, hour=12, tzinfo=IST
    )
    valid = sms_item("Rs.10,000 credited via UPI", when)
    response = client.post(
        "/api/v1/verify",
        json=payload(
            sms_log=[
                valid,
                valid,
                sms_item("Rs.500 debited from A/c", when),
                sms_item("No amount here", when),
                sms_item(
                    "Rs.1,000 credited via UPI",
                    datetime.now(timezone.utc) + timedelta(days=1),
                ),
                sms_item(
                    "Rs.1,000 credited via UPI",
                    _subtract_months(datetime.now(timezone.utc), 13),
                ),
            ]
        ),
    )
    assert response.status_code == 200
    summary = response.json()["sms_summary"]
    assert summary["received"] == 6
    assert summary["used"] == 1
    assert summary["dropped"] == 5
    assert sum(summary["dropped_by_reason"].values()) == summary["dropped"]
    assert (
        summary["received"]
        == summary["used"] + summary["dropped"]
    )


def test_sms_groups_by_ist_month_boundary(client, db_session):
    add_consent(db_session)
    add_record(db_session)
    months = recent_month_keys(6)
    older_key, previous_key = months[-2], months[-1]
    add_months(
        db_session,
        inflows=[100000.0, 100000.0],
        months=[older_key, previous_key],
        senders=[14, 14],
    )
    add_profile(db_session)
    previous_first = datetime.strptime(previous_key, "%Y-%m").replace(
        tzinfo=IST
    )
    older_month_end = previous_first - timedelta(minutes=30)
    previous_month_start = previous_first + timedelta(minutes=15)

    response = client.post(
        "/api/v1/verify",
        json=payload(
            sms_log=[
                sms_item("Rs.1,111 credited via UPI", older_month_end),
                sms_item("Rs.2,222 credited via UPI", previous_month_start),
            ]
        ),
    )
    assert response.status_code == 200
    credits = response.json()["sms_summary"]["monthly_credits"]
    assert credits[older_key] == 1111.0
    assert credits[previous_key] == 2222.0


# ---------------------------------------------------------------------------
# SMS evidence: anti-inflation rules
# ---------------------------------------------------------------------------
def test_sms_larger_than_upi_is_clipped(client, db_session):
    add_consent(db_session)
    add_record(db_session)
    months = seed_recent_upi(db_session)
    add_profile(db_session)
    when = datetime.strptime(months[-1], "%Y-%m").replace(
        day=10, hour=12, tzinfo=IST
    )
    response = client.post(
        "/api/v1/verify",
        json=payload(
            sms_log=[sms_item("Rs.999,999 credited via UPI", when)]
        ),
    )
    assert response.status_code == 200
    clipped = response.json()["sms_summary"]["clipped_months"]
    assert len(clipped) == 1
    assert clipped[0]["month"] == months[-1]
    assert clipped[0]["sms_total"] == 999999.0
    assert clipped[0]["upi_total"] == 32000.0
    assert clipped[0]["used_total"] == 32000.0


def test_sms_month_without_upi_evidence_passes_unclipped(client, db_session):
    add_consent(db_session)
    add_record(db_session)
    seed_recent_upi(db_session)
    add_profile(db_session)
    extra_month = recent_month_keys(7)[0]
    when = datetime.strptime(extra_month, "%Y-%m").replace(
        day=10, hour=12, tzinfo=IST
    )

    response = client.post(
        "/api/v1/verify",
        json=payload(
            sms_log=[sms_item("Rs.50,000 credited via UPI", when)]
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sms_summary"]["monthly_credits"][extra_month] == 50000.0
    assert body["sms_summary"]["clipped_months"] == []
    assert body["evidence"]["provenance"]["sms"] == "client_supplied_unverified"
    assert not any(
        flag["code"] == "SOURCES_DISAGREE"
        for flag in body["evidence"]["flags"]
    )


def test_fabricated_huge_sms_does_not_raise_income_or_recommendation(
    client, db_session
):
    add_consent(db_session)
    add_record(db_session)
    months = seed_recent_upi(db_session)
    add_profile(db_session)

    baseline = client.post("/api/v1/verify", json=payload()).json()
    sms_log = []
    for month in months:
        when = datetime.strptime(month, "%Y-%m").replace(
            day=10, hour=12, tzinfo=IST
        )
        sms_log.append(sms_item("Rs.999999 credited via UPI", when))
        sms_log.append(sms_item("Rs.9,99,999 credited via UPI", when))
    with_sms = client.post(
        "/api/v1/verify", json=payload(sms_log=sms_log)
    ).json()

    assert with_sms["income"] == baseline["income"]
    assert with_sms["recommendation"]["code"] == baseline["recommendation"]["code"]
    assert with_sms["income"]["low"] == baseline["income"]["low"]
    assert with_sms["income"]["mid"] == baseline["income"]["mid"]
    assert len(with_sms["sms_summary"]["clipped_months"]) == 6


def test_sms_only_worker_is_flagged_capped_and_needs_more_evidence(
    client, db_session
):
    add_consent(db_session)
    add_record(db_session, aggregate=None, sender_count=None)
    add_profile(db_session)
    sms_log = []
    for month in recent_month_keys(6):
        when = datetime.strptime(month, "%Y-%m").replace(
            day=10, hour=12, tzinfo=IST
        )
        sms_log.append(sms_item("Rs.32,000 credited via UPI", when))

    response = client.post("/api/v1/verify", json=payload(sms_log=sms_log))
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"]["provenance"] == {
        "upi": "none",
        "sms": "client_supplied_unverified",
    }
    assert any(
        flag["code"] == "UNVERIFIED_EVIDENCE_ONLY"
        for flag in body["evidence"]["flags"]
    )
    assert body["evidence"]["confidence_level"] == "MEDIUM"
    assert body["evidence"]["confidence_capped"] is True
    assert body["recommendation"]["code"] == NEEDS_MORE_EVIDENCE
    assert "income rests only on client-supplied, unverified SMS" in (
        body["recommendation"]["reasons"][0]
    )


def test_recommendation_sms_only_rule_runs_before_missing_risk():
    result = recommend(
        fake_evidence(flags=[{"code": "UNVERIFIED_EVIDENCE_ONLY"}]),
        {"available": False},
        {"proposed_emi": 1000, "max_affordable_emi": 5000},
    )
    assert result["code"] == NEEDS_MORE_EVIDENCE
    assert "income rests only on client-supplied, unverified SMS" in result[
        "reasons"
    ][0]


# ---------------------------------------------------------------------------
# SMS evidence: privacy, display priority and determinism
# ---------------------------------------------------------------------------
def test_raw_sms_text_never_stored(client, db_session):
    add_consent(db_session)
    add_record(db_session)
    months = seed_recent_upi(db_session)
    add_profile(db_session)
    sentinel = "RAW-SMS-SENTINEL-PHONE-9876543210"
    when = datetime.strptime(months[-1], "%Y-%m").replace(
        day=10, hour=12, tzinfo=IST
    )
    response = client.post(
        "/api/v1/verify",
        json=payload(sms_log=[sms_item(f"{sentinel} Rs.500 credited", when)]),
    )
    assert response.status_code == 200
    assert sentinel not in response.text

    stored = (
        db_session.query(VerificationResultRecord)
        .filter_by(id=response.json()["verification_id"])
        .one()
    )
    assert sentinel not in str(stored.result)


def test_display_priority_secondary_for_insufficient_evidence(client, db_session):
    add_consent(db_session)
    add_record(db_session, aggregate=None, sender_count=None)
    add_profile(db_session)
    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 200
    risk = response.json()["risk_signal"]
    assert risk["display_priority"] == "secondary"
    assert "insufficient" in risk["display_note"].lower()


def test_verification_is_deterministic_with_sms(client, db_session):
    add_consent(db_session)
    add_record(db_session)
    months = seed_recent_upi(db_session)
    add_profile(db_session)
    when = datetime.strptime(months[-1], "%Y-%m").replace(
        day=10, hour=12, tzinfo=IST
    )
    request_body = payload(
        sms_log=[sms_item("Rs.10,000 credited via UPI", when)]
    )
    first = client.post("/api/v1/verify", json=request_body).json()
    second = client.post("/api/v1/verify", json=request_body).json()

    for key in (
        "income",
        "expenses",
        "surplus_conservative",
        "evidence",
        "affordability",
        "risk_signal",
        "recommendation",
        "sms_summary",
        "model_version",
        "engine_version",
        "sms_ignored_reason",
    ):
        assert first[key] == second[key]


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


# ---------------------------------------------------------------------------
# What-if scenarios
# ---------------------------------------------------------------------------
def test_what_if_missing_consent_returns_403(client, db_session):
    seed_full(db_session)
    body = what_if_payload()
    body.pop("consent_id")
    response = client.post("/api/v1/verify/what-if", json=body)
    assert response.status_code == 403


def test_what_if_unknown_consent_returns_403(client, db_session):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify/what-if",
        json=what_if_payload(consent_id="CNS-NOT-REAL"),
    )
    assert response.status_code == 403
    assert "unknown consent_id" in response.json()["detail"].lower()


def test_what_if_revoked_consent_returns_403(client, db_session):
    add_consent(db_session, revoked=True)
    add_record(db_session)
    add_months(db_session)
    add_profile(db_session)
    response = client.post("/api/v1/verify/what-if", json=what_if_payload())
    assert response.status_code == 403
    assert "revoked" in response.json()["detail"].lower()


def test_what_if_expired_consent_returns_403(client, db_session):
    add_consent(db_session, expired=True)
    add_record(db_session)
    add_months(db_session)
    add_profile(db_session)
    response = client.post("/api/v1/verify/what-if", json=what_if_payload())
    assert response.status_code == 403
    assert "expired" in response.json()["detail"].lower()


def test_what_if_other_worker_consent_returns_403(client, db_session):
    add_consent(db_session, worker_id="WRK-OTHER")
    add_record(db_session)
    add_months(db_session)
    add_profile(db_session)
    response = client.post("/api/v1/verify/what-if", json=what_if_payload())
    assert response.status_code == 403
    assert "different worker" in response.json()["detail"].lower()


def test_what_if_other_phone_consent_returns_403(client, db_session):
    add_consent(db_session, phone_number="+919800000002")
    add_record(db_session)
    add_months(db_session)
    add_profile(db_session)
    response = client.post("/api/v1/verify/what-if", json=what_if_payload())
    assert response.status_code == 403
    assert "does not match" in response.json()["detail"].lower()


def test_what_if_never_persists_any_rows(client, db_session):
    seed_full(db_session)

    def row_counts():
        return {
            table.name: db_session.scalar(
                select(func.count()).select_from(table)
            )
            for table in Base.metadata.sorted_tables
        }

    before = row_counts()
    response = client.post(
        "/api/v1/verify/what-if",
        json=what_if_payload(
            hypothetical_upi_monthly_inflows=[30000.0] * 6,
            hypothetical_unique_senders=[12] * 6,
        ),
    )
    assert response.status_code == 200
    assert "verification_id" not in response.json()
    assert row_counts() == before


def test_what_if_deltas_are_zero_when_scenario_matches_baseline(client, db_session):
    seed_full(db_session)
    response = client.post("/api/v1/verify/what-if", json=what_if_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["hypothetical"] is True
    assert body["baseline"]["recommendation_code"] == PROCEED_TO_UNDERWRITING
    assert body["scenario"]["hypothetical_recommendation_code"] == PROCEED_TO_UNDERWRITING
    assert "recommendation" not in body["scenario"]
    assert body["deltas"] == {
        "income_low": 0.0,
        "surplus": 0.0,
        "max_affordable_emi": 0.0,
        "confidence_score": 0.0,
    }


def test_what_if_deltas_are_scenario_minus_baseline(client, db_session):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify/what-if",
        json=what_if_payload(
            hypothetical_upi_monthly_inflows=[40000.0] * 6,
            hypothetical_unique_senders=[20] * 6,
            stated_monthly_income=35000.0,
            monthly_outgoings=OUTGOINGS,
            proposed_emi=1000.0,
            tenure_months=24,
        ),
    )
    assert response.status_code == 200
    body = response.json()
    baseline = body["baseline"]
    scenario = body["scenario"]
    assert body["deltas"]["income_low"] == (
        scenario["income_low"] - baseline["income_low"]
    )
    assert body["deltas"]["surplus"] == (
        scenario["surplus_conservative"] - baseline["surplus_conservative"]
    )
    assert body["deltas"]["max_affordable_emi"] == (
        scenario["max_affordable_emi"] - baseline["max_affordable_emi"]
    )
    assert body["deltas"]["confidence_score"] == (
        scenario["confidence_score"] - baseline["confidence_score"]
    )


def test_what_if_hypothetical_inflows_change_income_and_confidence(
    client, db_session
):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify/what-if",
        json=what_if_payload(
            hypothetical_upi_monthly_inflows=[10000.0],
            hypothetical_unique_senders=[20],
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scenario"]["income_low"] < body["baseline"]["income_low"]
    assert body["scenario"]["confidence_score"] < body["baseline"]["confidence_score"]
    assert body["deltas"]["income_low"] < 0
    assert body["deltas"]["confidence_score"] < 0


def test_what_if_overstated_income_needs_more_evidence(client, db_session):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify/what-if",
        json=what_if_payload(stated_monthly_income=90000.0),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["baseline"]["recommendation_code"] == PROCEED_TO_UNDERWRITING
    assert (
        body["scenario"]["hypothetical_recommendation_code"]
        == NEEDS_MORE_EVIDENCE
    )
    assert any(
        flag["code"] == "STATED_OVERSTATED" for flag in body["scenario"]["flags"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_features", {"late_share": 0.0}),
        ("credit_term_months", 24),
        ("late_share", 0.1),
        ("unknown_field", True),
    ],
)
def test_what_if_rejects_extra_and_model_feature_fields(
    client, db_session, field, value
):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify/what-if",
        json=what_if_payload(**{field: value}),
    )
    assert response.status_code == 422


def test_what_if_rejects_mismatched_hypothetical_sender_lengths(
    client, db_session
):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify/what-if",
        json=what_if_payload(
            hypothetical_upi_monthly_inflows=[10000.0, 12000.0],
            hypothetical_unique_senders=[5],
        ),
    )
    assert response.status_code == 422


def test_what_if_response_has_no_forbidden_keys(client, db_session):
    seed_full(db_session)
    response = client.post(
        "/api/v1/verify/what-if",
        json=what_if_payload(hypothetical_upi_monthly_inflows=[30000.0] * 6),
    )
    assert response.status_code == 200
    assert_no_forbidden_keys(response.json())


def test_verify_response_matches_recorded_snapshot(client, db_session):
    seed_full(db_session)
    body = client.post("/api/v1/verify", json=payload()).json()
    expected = {
        "income": {
            "low": 26711.25,
            "mid": 27115.0,
            "high": 27688.75,
            "conservative": 26711.25,
            "stated": 32000.0,
            "stated_vs_evidence_ratio": 1.18,
        },
        "surplus_conservative": 10211.25,
        "confidence_score": 95,
        "confidence_level": "HIGH",
        "max_affordable_emi": 10211.25,
        "recommendation_code": PROCEED_TO_UNDERWRITING,
        "risk_band": "LOW",
        "data_notice": None,
    }
    actual = {
        "income": body["income"],
        "surplus_conservative": body["surplus_conservative"],
        "confidence_score": body["evidence"]["confidence_score"],
        "confidence_level": body["evidence"]["confidence_level"],
        "max_affordable_emi": body["affordability"]["max_affordable_emi"],
        "recommendation_code": body["recommendation"]["code"],
        "risk_band": body["risk_signal"]["band"],
        "data_notice": body["data_notice"],
    }
    assert actual == expected


def test_data_notice_appears_for_seeded_profiles_in_verify_and_what_if(
    client, db_session
):
    add_consent(db_session)
    add_record(db_session)
    add_months(db_session)
    profile = add_profile(db_session)
    profile.source = "home_credit_heldout_row"
    db_session.commit()

    verify_body = client.post("/api/v1/verify", json=payload()).json()
    what_if_body = client.post(
        "/api/v1/verify/what-if", json=what_if_payload()
    ).json()
    expected = (
        "Demonstration worker: risk features come from a held-out row of a public, "
        "non-Indian dataset; UPI evidence is simulated."
    )
    assert verify_body["data_notice"] == expected
    assert what_if_body["data_notice"] == expected


def test_data_notice_is_null_for_ordinary_profiles(client, db_session):
    seed_full(db_session)
    body = client.post("/api/v1/verify", json=payload()).json()
    assert body["data_notice"] is None



# ---------------------------------------------------------------------------
# Consistency checks integration
# ---------------------------------------------------------------------------
def test_verify_includes_consistency_flags_and_note(client, db_session):
    from backend.core.consistency_checks import CONSISTENCY_NOTE, EVIDENCE_GAP

    add_consent(db_session)
    add_record(db_session)
    months = recent_month_keys(6)
    gap_months = [months[0], months[1], months[3], months[4], months[5]]
    add_months(
        db_session,
        inflows=[30000.0] * 5,
        months=gap_months,
        senders=[12] * 5,
    )
    add_profile(db_session)

    response = client.post("/api/v1/verify", json=payload())
    assert response.status_code == 200
    body = response.json()
    flags = body["evidence"]["flags"]
    gap_flags = [flag for flag in flags if flag["code"] == EVIDENCE_GAP]
    assert len(gap_flags) == 1
    assert gap_flags[0]["source"] == "consistency_checks"
    assert all(
        flag.get("source") in {"income_engine", "consistency_checks"}
        for flag in flags
    )
    assert any(flag.get("source") == "income_engine" for flag in flags)
    assert body["evidence"]["consistency_note"] == CONSISTENCY_NOTE


def test_what_if_applies_consistency_checks_to_hypothetical_series(
    client, db_session
):
    from backend.core.consistency_checks import LATEST_MONTH_SPIKE

    seed_full(db_session)
    response = client.post(
        "/api/v1/verify/what-if",
        json=what_if_payload(
            hypothetical_upi_monthly_inflows=[
                32000.0,
                32000.0,
                32000.0,
                100000.0,
            ],
            hypothetical_unique_senders=[15, 15, 15, 15],
        ),
    )
    assert response.status_code == 200
    body = response.json()
    scenario_flags = body["scenario"]["flags"]
    spike_flags = [
        flag for flag in scenario_flags if flag["code"] == LATEST_MONTH_SPIKE
    ]
    assert len(spike_flags) == 1
    assert spike_flags[0]["source"] == "consistency_checks"
    assert LATEST_MONTH_SPIKE not in {
        flag["code"] for flag in body["baseline"]["flags"]
    }


def test_constant_inflow_caveat_only_for_vendor_occupation(client, db_session):
    from backend.core.consistency_checks import CONSTANT_INFLOW

    add_consent(db_session)
    add_record(db_session)
    months = recent_month_keys(4)
    add_months(
        db_session,
        inflows=[28000.0] * 4,
        months=months,
        senders=[12] * 4,
    )
    add_profile(db_session)

    vendor = client.post(
        "/api/v1/verify",
        json=payload(
            stated_monthly_income=None,
            occupation_type="Street vendor",
        ),
    ).json()
    driver = client.post(
        "/api/v1/verify",
        json=payload(
            stated_monthly_income=None,
            occupation_type="Driver",
        ),
    ).json()

    assert vendor["recommendation"]["code"] == driver["recommendation"]["code"]
    assert CONSTANT_INFLOW in {
        flag["code"] for flag in vendor["evidence"]["flags"]
    }
    assert CONSTANT_INFLOW in {
        flag["code"] for flag in driver["evidence"]["flags"]
    }
    assert any(
        "Consistency check" in caveat and "same monthly inflow" in caveat
        for caveat in vendor["recommendation"]["caveats"]
    )
    assert not any(
        "same monthly inflow" in caveat
        for caveat in driver["recommendation"]["caveats"]
    )


def test_new_responses_have_no_forbidden_keys_or_fraud_strings(
    client, db_session
):
    seed_full(db_session)

    def strings(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                yield str(key)
                yield from strings(nested)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, str):
            yield value

    responses = [
        client.post("/api/v1/verify", json=payload()).json(),
        client.post(
            "/api/v1/verify/what-if",
            json=what_if_payload(
                hypothetical_upi_monthly_inflows=[32000.0] * 4,
                hypothetical_unique_senders=[12] * 4,
            ),
        ).json(),
    ]
    for body in responses:
        assert_no_forbidden_keys(body)
        assert all("fraud" not in text.lower() for text in strings(body))
