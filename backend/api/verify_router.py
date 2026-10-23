"""Endpoints for the new income-verification and decision-support flow."""

from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

try:
    from backend.core.verification_pipeline import (
        get_stored_verification,
        run_verification,
    )
    from backend.models.database import get_db
    from backend.schemas.verification import VerifyRequest, VerifyResponse
except ModuleNotFoundError:  # pragma: no cover - flat module execution fallback
    from core.verification_pipeline import (
        get_stored_verification,
        run_verification,
    )
    from models.database import get_db
    from schemas.verification import VerifyRequest, VerifyResponse

router = APIRouter()


@router.post(
    "/verify",
    response_model=VerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify income and obtain decision support",
    description=(
        "Combines database UPI evidence, deterministic income verification, conservative "
        "affordability and a reference-population repayment-risk signal. ICVER does not "
        "approve or reject credit."
    ),
)
def verify_worker(
    payload: VerifyRequest,
    db: Session = Depends(get_db),
) -> VerifyResponse:
    return run_verification(db, payload)


@router.get(
    "/verify/{verification_id}",
    response_model=VerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a stored verification result",
    description=(
        "Returns a previously stored verification only when the supplied consent is valid "
        "and belongs to the same worker."
    ),
)
def get_verification(
    verification_id: str,
    consent_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> VerifyResponse:
    return get_stored_verification(db, verification_id, consent_id)
