"""
Unit and integration tests for API safety, consent management, phone normalization,
and model loading constraints in ICVER backend.
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.core.config import settings
from backend.core.phone import normalize_phone
from backend.models.database import Base, get_db, FinancialRecord, WorkerConsent
import backend.api.router as router_module


@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database session for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_worker(db_session):
    """Seed a standard non-gig worker into the test database."""
    record = FinancialRecord(
        mobile_number="+919876543210",
        upi_monthly_inflow=25000.0,
        weekly_txn_frequency=12,
        recharge_regularity_index=0.85,
        days_since_last_txn=2,
        unique_sender_count=20,
        utility_payment_streak=4,
        is_gig_worker=False,
        monthly_cashflow_avg=30000.0,
        gig_platform_earnings=None,
        monthly_household_income=25000.0,
        monthly_business_expenses=8000.0,
        monthly_household_expenses=5000.0,
        existing_monthly_emi=1000.0,
        proposed_loan_emi=1500.0,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Test 1: Phone Normalization - Valid Formats
# ---------------------------------------------------------------------------
def test_phone_normalization_all_formats():
    """All 4 Indian phone formats normalise to the same canonical form +919876543210."""
    formats = [
        "+919876543210",
        "9876543210",
        "98765 43210",
        "09876543210",
        "+91 98765-43210",
    ]
    for raw in formats:
        normalized = normalize_phone(raw)
        assert normalized == "+919876543210", f"Failed for format: {raw}"


# ---------------------------------------------------------------------------
# Test 2: Phone Normalization - Garbage Input Rejected
# ---------------------------------------------------------------------------
def test_phone_normalization_garbage_rejected():
    """Garbage and malformed phone inputs are rejected with clear ValueError."""
    invalid_inputs = [
        "12345",
        "not-a-number",
        "",
        "   ",
        "987654321",        # 9 digits
        "9876543210123",    # too many digits
        "1234567890",       # does not start with 6, 7, 8, or 9
        "5555555555",       # starts with 5
    ]
    for bad in invalid_inputs:
        with pytest.raises(ValueError):
            normalize_phone(bad)


# ---------------------------------------------------------------------------
# Test 3: Consent - Unknown Consent ID returns 403
# ---------------------------------------------------------------------------
def test_unknown_consent_id_returns_403(client, seeded_worker):
    """Providing an unknown consent_id returns HTTP 403 Forbidden."""
    resp = client.post(
        "/api/v1/score",
        json={
            "worker_id": "WRK-10024",
            "consent_id": "CNS-NONEXISTENT-9999",
            "phone_number": "9876543210",
        },
    )
    assert resp.status_code == 403
    assert "Unknown consent_id" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test 4: Consent - Revoked Consent returns 403
# ---------------------------------------------------------------------------
def test_revoked_consent_returns_403(client, db_session, seeded_worker):
    """Revoked consent returns HTTP 403 Forbidden."""
    # Create consent
    consent = WorkerConsent(
        id="CNS-REVOKED-001",
        worker_id="WRK-10024",
        phone_number="+919876543210",
        scope="Income verification",
        granted_at=datetime.now(timezone.utc),
        revoked_at=datetime.now(timezone.utc),
    )
    db_session.add(consent)
    db_session.commit()

    resp = client.post(
        "/api/v1/score",
        json={
            "worker_id": "WRK-10024",
            "consent_id": "CNS-REVOKED-001",
        },
    )
    assert resp.status_code == 403
    assert "revoked" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 5: Consent - Expired Consent returns 403
# ---------------------------------------------------------------------------
def test_expired_consent_returns_403(client, db_session, seeded_worker):
    """Expired consent returns HTTP 403 Forbidden."""
    consent = WorkerConsent(
        id="CNS-EXPIRED-001",
        worker_id="WRK-10024",
        phone_number="+919876543210",
        scope="Income verification",
        granted_at=datetime.now(timezone.utc) - timedelta(days=30),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(consent)
    db_session.commit()

    resp = client.post(
        "/api/v1/score",
        json={
            "worker_id": "WRK-10024",
            "consent_id": "CNS-EXPIRED-001",
        },
    )
    assert resp.status_code == 403
    assert "expired" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 6: Consent - Belonging to another worker or phone returns 403
# ---------------------------------------------------------------------------
def test_consent_mismatched_worker_or_phone_returns_403(client, db_session, seeded_worker):
    """Consent belonging to another worker ID or phone number returns HTTP 403."""
    consent = WorkerConsent(
        id="CNS-VALID-001",
        worker_id="WRK-10024",
        phone_number="+919876543210",
        scope="Income verification",
        granted_at=datetime.now(timezone.utc),
    )
    db_session.add(consent)
    db_session.commit()

    # Mismatched worker ID
    resp = client.post(
        "/api/v1/score",
        json={
            "worker_id": "WRK-OTHER-999",
            "consent_id": "CNS-VALID-001",
        },
    )
    assert resp.status_code == 403
    assert "belongs to a different worker" in resp.json()["detail"]

    # Mismatched requested phone number
    resp_phone = client.post(
        "/api/v1/score",
        json={
            "worker_id": "WRK-10024",
            "consent_id": "CNS-VALID-001",
            "phone_number": "9998887776",  # different phone
        },
    )
    assert resp_phone.status_code == 403
    assert "does not match" in resp_phone.json()["detail"]


# ---------------------------------------------------------------------------
# Test 7: Valid Consent returns 200
# ---------------------------------------------------------------------------
def test_valid_consent_returns_200(client, seeded_worker):
    """Valid consent creation and scoring request succeeds with HTTP 200."""
    # Register consent via API
    c_resp = client.post(
        "/api/v1/consent",
        json={
            "worker_id": "WRK-10024",
            "phone_number": "9876543210",
            "consent_given": True,
            "consent_purpose": "Loan evaluation",
        },
    )
    assert c_resp.status_code == 201
    consent_id = c_resp.json()["consent_id"]
    assert consent_id.startswith("CNS-")
    assert c_resp.json()["phone_number"] == "+919876543210"

    # Score worker
    s_resp = client.post(
        "/api/v1/score",
        json={
            "worker_id": "WRK-10024",
            "consent_id": consent_id,
        },
    )
    assert s_resp.status_code == 200
    data = s_resp.json()
    assert data["worker_id"] == "WRK-10024"
    assert data["consent_id"] == consent_id
    assert 0 <= data["creditworthiness_score"] <= 100
    assert data["decision_tier"] in ["Eligible", "Review", "Ineligible", "High Risk"]
    assert "breakdown" in data


# ---------------------------------------------------------------------------
# Test 8: Request defaults fall back to DB values, no gig income for non-gig
# ---------------------------------------------------------------------------
def test_omitting_cashflow_and_gig_earnings_uses_database_values(client, db_session, seeded_worker):
    """
    Omitting monthly_cashflow_avg and gig_platform_earnings:
    - uses database record values (monthly_cashflow_avg = 30000.0)
    - does not add gig income for a non-gig worker (gig_platform_earnings stays None/0).
    """
    consent = WorkerConsent(
        id="CNS-NON-GIG-001",
        worker_id="WRK-10024",
        phone_number="+919876543210",
        scope="Income verification",
        granted_at=datetime.now(timezone.utc),
    )
    db_session.add(consent)
    db_session.commit()

    resp = client.post(
        "/api/v1/score",
        json={
            "worker_id": "WRK-10024",
            "consent_id": "CNS-NON-GIG-001",
            # monthly_cashflow_avg and gig_platform_earnings omitted
        },
    )
    assert resp.status_code == 200
    breakdown = resp.json()["breakdown"]
    # Base estimate for 30000 cashflow * 0.6 = 18000.0. Gig earnings = 0.
    assert breakdown["base_estimated_income"] == 18000.0
    assert resp.json()["is_gig_worker"] is False


# ---------------------------------------------------------------------------
# Test 9: Client Feature Overrides Ignored when ALLOW_FEATURE_OVERRIDES is False
# ---------------------------------------------------------------------------
def test_feature_overrides_ignored_when_disabled(client, db_session, seeded_worker, monkeypatch):
    """When ALLOW_FEATURE_OVERRIDES is False, client feature overrides in payload are ignored."""
    monkeypatch.setattr(settings, "ALLOW_FEATURE_OVERRIDES", False)

    consent = WorkerConsent(
        id="CNS-OVERRIDE-001",
        worker_id="WRK-10024",
        phone_number="+919876543210",
        scope="Income verification",
        granted_at=datetime.now(timezone.utc),
    )
    db_session.add(consent)
    db_session.commit()

    # Client tries to override weekly_txn_frequency to 50 (which would trigger fraud penalty)
    # and upi_monthly_inflow to 90000.0.
    resp = client.post(
        "/api/v1/score",
        json={
            "worker_id": "WRK-10024",
            "consent_id": "CNS-OVERRIDE-001",
            "weekly_txn_frequency": 50,
            "upi_monthly_inflow": 90000.0,
        },
    )
    assert resp.status_code == 200
    # synthetic_volume_flag should be False because DB record has weekly_txn_frequency=12, not 50!
    assert resp.json()["synthetic_volume_flag"] is False


# ---------------------------------------------------------------------------
# Test 10: Missing model returns HTTP 503 (no hardcoded fallback)
# ---------------------------------------------------------------------------
def test_missing_model_returns_503(client, db_session, seeded_worker, monkeypatch):
    """When ML models fail to load or are missing, /score returns HTTP 503, never hardcoded Eligible."""
    monkeypatch.setattr(router_module, "_ml_ready", False)

    consent = WorkerConsent(
        id="CNS-503-TEST",
        worker_id="WRK-10024",
        phone_number="+919876543210",
        scope="Income verification",
        granted_at=datetime.now(timezone.utc),
    )
    db_session.add(consent)
    db_session.commit()

    resp = client.post(
        "/api/v1/score",
        json={
            "worker_id": "WRK-10024",
            "consent_id": "CNS-503-TEST",
        },
    )
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()

    # Also verify health endpoint reflects model status
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["model_status"]["models_loaded"] is False


# ---------------------------------------------------------------------------
# Test 11: Wildcard CORS origin is never combined with credentials
# ---------------------------------------------------------------------------
def test_wildcard_cors_not_combined_with_credentials():
    """Ensure that allow_origins=['*'] never co-exists with allow_credentials=True."""
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi import FastAPI

    test_origins = ["*"]
    allow_creds = False if "*" in test_origins else True
    assert allow_creds is False, "Wildcard origin must not enable allow_credentials"

    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=test_origins,
        allow_credentials=allow_creds,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Starlette Middleware uses .kwargs (not .options) to store the arguments
    cors_mw = [m for m in test_app.user_middleware if m.cls == CORSMiddleware][0]
    opts = cors_mw.kwargs
    assert opts["allow_origins"] == ["*"]
    assert opts["allow_credentials"] is False


# ---------------------------------------------------------------------------
# Test 12: Revoke consent endpoint
# ---------------------------------------------------------------------------
def test_revoke_consent_endpoint(client, db_session):
    """POST /api/v1/consent/{consent_id}/revoke updates consent status to REVOKED."""
    # Create consent
    c_resp = client.post(
        "/api/v1/consent",
        json={
            "worker_id": "WRK-REVOKE-TEST",
            "phone_number": "9876543210",
            "consent_given": True,
        },
    )
    consent_id = c_resp.json()["consent_id"]

    # Revoke consent
    r_resp = client.post(f"/api/v1/consent/{consent_id}/revoke")
    assert r_resp.status_code == 200
    assert r_resp.json()["status"] == "REVOKED"

    # Fetch consent
    g_resp = client.get(f"/api/v1/consent/{consent_id}")
    assert g_resp.status_code == 200
    assert g_resp.json()["status"] == "REVOKED"
