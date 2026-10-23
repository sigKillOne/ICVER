"""Reusable consent validation for the new /verify flow.

The legacy /score endpoint in backend/api/router.py validates consent inline. That
endpoint is intentionally left unchanged, so this module duplicates its validation
rules (missing, unknown, revoked, expired, worker/phone mismatch) for reuse by the new
pipeline and GET endpoint.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

try:
    from backend.core.phone import normalize_phone
    from backend.models.database import WorkerConsent
except ModuleNotFoundError:  # pragma: no cover - flat module execution fallback
    from core.phone import normalize_phone
    from models.database import WorkerConsent


def validate_consent(
    db: Session,
    consent_id: str | None,
    worker_id: str,
    phone_number: str | None = None,
) -> WorkerConsent:
    """Return a valid consent or raise HTTP 403/400 following the legacy rules."""
    if not consent_id or not consent_id.strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing consent_id. Valid active worker consent is required for verification.",
        )

    consent = db.query(WorkerConsent).filter(WorkerConsent.id == consent_id).first()
    if not consent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown consent_id '{consent_id}'. Consent record not found.",
        )

    if consent.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Consent has been revoked.",
        )

    now_utc = datetime.now(timezone.utc)
    if consent.expires_at is not None:
        expires_at = (
            consent.expires_at
            if consent.expires_at.tzinfo
            else consent.expires_at.replace(tzinfo=timezone.utc)
        )
        if expires_at < now_utc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Consent has expired.",
            )

    if consent.worker_id != worker_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Consent record belongs to a different worker ID.",
        )

    if phone_number:
        try:
            requested_phone = normalize_phone(phone_number)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid phone_number in request: {exc}",
            )
        if requested_phone != consent.phone_number:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Consent phone number does not match requested phone number.",
            )

    return consent
