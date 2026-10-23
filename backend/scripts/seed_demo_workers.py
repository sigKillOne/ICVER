"""Seed deterministic demonstration workers from locally held-out model data.

The Home Credit Default Risk dataset is public but cannot be redistributed here. This
script reads the local, git-ignored parquet files and writes only to a database. No
Home Credit feature value is written into a committed file. Every UPI amount and sender
count below is simulated, made-up demonstration data.

Run:
    python -m backend.scripts.seed_demo_workers [--database-url URL] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.core.verification_pipeline import _subtract_months, run_verification
from backend.models.database import (
    Base,
    FinancialRecord,
    WorkerConsent,
    WorkerMonthlyEvidence,
    WorkerRiskProfile,
)
from backend.schemas.verification import VerifyRequest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "backend" / "data" / "processed"
PREDICTIONS_PATH = DATA_DIR / "test_predictions_v2.parquet"
FEATURES_PATH = DATA_DIR / "features_train.parquet"
RISK_META_PATH = REPO_ROOT / "backend" / "ml" / "artifacts" / "risk_v2" / "risk_meta_v2.json"

SELECTION_SEED = 42  # Fixed seed requested for reproducible persona selection.
DEMO_WORKER_PREFIX = "demo-"
DEMO_CONSENT_PREFIX = "demo-consent-"
DEMO_RISK_SOURCE = "home_credit_heldout_row"
DEMO_PHONE_PREFIX = "+91900000000"  # Fake +91 900000000N; final digit identifies persona.
PASSWORD_MASK = "***"
PASSWORD_PLACEHOLDER = "ICVER_PASSWORD_PLACEHOLDER"
# Assumption: these substrings identify production-like database hosts or names.
PRODUCTION_URL_SUBSTRINGS = ("prod", "production")

INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")

HISTORY_FLAGS = (
    "has_installment_history",
    "has_bureau_history",
    "has_prev_application",
)

PERSONA_LOW_RISK_FULL = "low_risk_full_history"
PERSONA_MEDIUM_RISK = "medium_risk"
PERSONA_HIGH_RISK_WITH_HISTORY = "high_risk_with_history"
PERSONA_NO_CREDIT_HISTORY = "no_credit_history"
PERSONA_LOW_BAND_LIMITED = "low_band_limited_history"
PERSONA_ORDER = (
    PERSONA_LOW_RISK_FULL,
    PERSONA_MEDIUM_RISK,
    PERSONA_HIGH_RISK_WITH_HISTORY,
    PERSONA_NO_CREDIT_HISTORY,
    PERSONA_LOW_BAND_LIMITED,
)

PERSONA_LABELS = {
    PERSONA_LOW_RISK_FULL: "Low-risk, full history",
    PERSONA_MEDIUM_RISK: "Medium-risk",
    PERSONA_HIGH_RISK_WITH_HISTORY: "High-risk with history",
    PERSONA_NO_CREDIT_HISTORY: "No credit history",
    PERSONA_LOW_BAND_LIMITED: "LOW band, limited history",
}

# Made-up simulation recipes. Amounts are INR per month; senders are counterparties.
PERSONA_RECIPES = {
    PERSONA_LOW_RISK_FULL: {
        "months": 6,
        "min_amount": 38_000,
        "max_amount": 46_000,
        "min_senders": 20,
        "max_senders": 30,
    },
    PERSONA_MEDIUM_RISK: {
        "months": 6,
        "min_amount": 30_000,
        "max_amount": 38_000,
        "min_senders": 10,
        "max_senders": 16,
    },
    PERSONA_HIGH_RISK_WITH_HISTORY: {
        "months": 6,
        "min_amount": 20_000,
        "max_amount": 32_000,
        "min_senders": 4,
        "max_senders": 10,
    },
    PERSONA_NO_CREDIT_HISTORY: {
        "months": 4,
        "min_amount": 12_000,
        "max_amount": 20_000,
        "min_senders": 3,
        "max_senders": 6,
    },
    PERSONA_LOW_BAND_LIMITED: {
        "months": 3,
        "min_amount": 25_000,
        "max_amount": 33_000,
        "min_senders": 6,
        "max_senders": 10,
    },
}


def mask_database_url(database_url: str) -> str:
    """Render a database URL with its password replaced by literal ``***``."""
    try:
        url = make_url(database_url)
    except Exception:
        return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", database_url)

    if not url.password:
        return url.render_as_string(hide_password=False)
    rendered = url.set(password=PASSWORD_PLACEHOLDER).render_as_string(
        hide_password=False
    )
    return rendered.replace(PASSWORD_PLACEHOLDER, PASSWORD_MASK)


def looks_like_production_url(database_url: str) -> bool:
    """Return True when the URL host or database name contains a production marker."""
    try:
        url = make_url(database_url)
    except Exception:
        lowered = database_url.lower()
        return any(marker in lowered for marker in PRODUCTION_URL_SUBSTRINGS)

    values = [url.host or "", url.database or ""]
    return any(
        marker in value.lower()
        for value in values
        for marker in PRODUCTION_URL_SUBSTRINGS
    )


def load_feature_names() -> List[str]:
    """Read the 24 v2 model feature names from protected artifact metadata."""
    with open(RISK_META_PATH, "r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    return list(metadata["features"])


def load_heldout_rows(feature_names: Sequence[str]) -> pd.DataFrame:
    """Read the local held-out predictions and selected feature columns."""
    for path in (PREDICTIONS_PATH, FEATURES_PATH):
        if not path.exists():
            raise FileNotFoundError(
                f"Missing local held-out data file: {path}. This script needs the "
                "git-ignored Home Credit parquet files; they cannot be redistributed."
            )

    features = pd.read_parquet(FEATURES_PATH)
    available_columns = ["SK_ID_CURR"] + [
        name for name in feature_names if name in features.columns
    ]
    predictions = pd.read_parquet(PREDICTIONS_PATH)
    return predictions.merge(
        features[available_columns],
        on="SK_ID_CURR",
        how="inner",
    )


def _require_selection_columns(frame: pd.DataFrame) -> None:
    required = {"SK_ID_CURR", "band", "calibrated_pd", *HISTORY_FLAGS}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Persona selection frame is missing columns: {missing}")


def _closest_to_median(frame: pd.DataFrame, target_pd: float) -> pd.Series:
    if frame.empty:
        raise ValueError("No eligible rows for a demo persona")
    ranked = frame.copy()
    ranked["_distance"] = (
        ranked["calibrated_pd"].astype(float) - float(target_pd)
    ).abs()
    ranked = ranked.sort_values(
        ["_distance", "SK_ID_CURR"], ascending=[True, True], kind="stable"
    )
    return ranked.iloc[0].drop(labels=["_distance"])


def _persona_record(persona: str, row: pd.Series, target_pd: float) -> Dict[str, Any]:
    record = {column: row[column] for column in row.index if column != "TARGET"}
    record.update(
        {
            "persona": persona,
            "SK_ID_CURR": int(row["SK_ID_CURR"]),
            "band": str(row["band"]),
            "calibrated_pd": float(row["calibrated_pd"]),
            "target_median_pd": float(target_pd),
            "distance_to_median": abs(float(row["calibrated_pd"]) - float(target_pd)),
        }
    )
    for flag in HISTORY_FLAGS:
        record[flag] = int(row[flag])
    return record


def select_personas(
    frame: pd.DataFrame, seed: int = SELECTION_SEED
) -> Dict[str, Dict[str, Any]]:
    """Select the five deterministic demo personas from a prediction frame.

    The function is pure and works on a tiny made-up DataFrame in tests. Selection uses
    band, history flags and distance to the relevant band median; TARGET is never read.
    The seed argument is retained for API stability; sorted SK_ID_CURR values provide the
    deterministic tie-break.
    """
    _ = seed
    _require_selection_columns(frame)
    frame = frame.copy()
    frame["band"] = frame["band"].astype(str).str.upper()
    for flag in HISTORY_FLAGS:
        frame[flag] = pd.to_numeric(frame[flag], errors="coerce").fillna(0).astype(int)
    frame["calibrated_pd"] = pd.to_numeric(frame["calibrated_pd"], errors="coerce")
    frame = frame.dropna(subset=["calibrated_pd", "SK_ID_CURR"])

    flag_sum = frame[list(HISTORY_FLAGS)].sum(axis=1)
    band_medians = frame.groupby("band")["calibrated_pd"].median().to_dict()
    overall_median = float(frame["calibrated_pd"].median())

    filters = {
        PERSONA_LOW_RISK_FULL: (
            (frame["band"] == "LOW") & (flag_sum == len(HISTORY_FLAGS))
        ),
        PERSONA_MEDIUM_RISK: frame["band"] == "MEDIUM",
        PERSONA_HIGH_RISK_WITH_HISTORY: (frame["band"] == "HIGH") & (flag_sum > 0),
        PERSONA_NO_CREDIT_HISTORY: flag_sum == 0,
        PERSONA_LOW_BAND_LIMITED: (
            (frame["band"] == "LOW") & (flag_sum > 0) & (flag_sum < len(HISTORY_FLAGS))
        ),
    }

    selected: Dict[str, Dict[str, Any]] = {}
    for persona in PERSONA_ORDER:
        eligible = frame[filters[persona]]
        if eligible.empty:
            raise ValueError(f"No eligible held-out row for demo persona '{persona}'")
        target = (
            overall_median
            if persona == PERSONA_NO_CREDIT_HISTORY
            else float(band_medians.get(str(eligible["band"].iloc[0]), overall_median))
        )
        selected[persona] = _persona_record(
            persona, _closest_to_median(eligible, target), target
        )
    return selected


# Alias kept for callers that prefer the more explicit name.
select_demo_personas = select_personas


def _simulated_months(persona: str) -> List[tuple[str, float, int]]:
    recipe = PERSONA_RECIPES[persona]
    rng = random.Random(SELECTION_SEED + PERSONA_ORDER.index(persona))
    current_month = datetime.now(timezone.utc).astimezone(INDIA_TIMEZONE).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    months = [
        _subtract_months(current_month, offset).strftime("%Y-%m")
        for offset in reversed(range(1, recipe["months"] + 1))
    ]
    amount_range = recipe["max_amount"] - recipe["min_amount"]
    monthly = []
    for month in months:
        amount = recipe["min_amount"] + rng.randint(0, amount_range // 500) * 500
        senders = rng.randint(recipe["min_senders"], recipe["max_senders"])
        monthly.append((month, float(amount), int(senders)))
    return monthly


def _extract_features(
    selected_record: Dict[str, Any], feature_names: Sequence[str]
) -> Dict[str, float]:
    features: Dict[str, float] = {}
    for name in feature_names:
        value = selected_record.get(name)
        if value is None or pd.isna(value):
            continue
        if hasattr(value, "item"):
            value = value.item()
        numeric = float(value)
        if math.isnan(numeric):
            continue
        features[name] = numeric
    return features


def _upsert_financial_record(
    session: Session,
    phone: str,
    monthly: Sequence[tuple[str, float, int]],
) -> None:
    amounts = [amount for _, amount, _ in monthly]
    senders = [senders for _, _, senders in monthly]
    average = round(sum(amounts) / len(amounts), 2)
    median_senders = int(sorted(senders)[len(senders) // 2])

    record = (
        session.query(FinancialRecord)
        .filter(FinancialRecord.mobile_number == phone)
        .first()
    )
    if record is None:
        record = FinancialRecord(mobile_number=phone)
        session.add(record)

    record.upi_monthly_inflow = average
    record.weekly_txn_frequency = 12
    record.recharge_regularity_index = 0.9
    record.days_since_last_txn = 2
    record.unique_sender_count = median_senders
    record.utility_payment_streak = 5
    record.is_gig_worker = False
    record.gig_rating = None
    record.gig_hours_per_week = None
    record.monthly_cashflow_avg = average
    record.gig_platform_earnings = None
    record.monthly_household_income = average
    record.monthly_business_expenses = 0.0
    record.monthly_household_expenses = 0.0
    record.existing_monthly_emi = 0.0
    record.proposed_loan_emi = 0.0


def _upsert_consent(
    session: Session,
    consent_id: str,
    worker_id: str,
    phone: str,
    persona: str,
    now_utc: datetime,
) -> None:
    consent = session.get(WorkerConsent, consent_id)
    if consent is None:
        consent = WorkerConsent(id=consent_id)
        session.add(consent)
    consent.worker_id = worker_id
    consent.phone_number = phone
    consent.scope = (
        f"Demo worker: {persona} | income verification demonstration"
    )
    consent.granted_at = consent.granted_at or now_utc
    consent.expires_at = None
    consent.revoked_at = None


def _upsert_risk_profile(
    session: Session,
    worker_id: str,
    features: Dict[str, float],
    now_utc: datetime,
) -> None:
    profile = (
        session.query(WorkerRiskProfile)
        .filter(WorkerRiskProfile.worker_id == worker_id)
        .first()
    )
    if profile is None:
        profile = WorkerRiskProfile(worker_id=worker_id)
        session.add(profile)
        profile.updated_at = now_utc
    if profile.features != features:
        profile.features = features
    profile.source = DEMO_RISK_SOURCE


def _upsert_monthly_evidence(
    session: Session,
    worker_id: str,
    monthly: Sequence[tuple[str, float, int]],
) -> None:
    existing = {
        row.year_month: row
        for row in session.query(WorkerMonthlyEvidence)
        .filter(WorkerMonthlyEvidence.worker_id == worker_id)
        .all()
    }
    wanted = {month for month, _, _ in monthly}
    for month, amount, senders in monthly:
        row = existing.get(month)
        if row is None:
            row = WorkerMonthlyEvidence(worker_id=worker_id, year_month=month)
            session.add(row)
        row.upi_inflow = amount
        row.upi_unique_senders = senders
    for month, row in existing.items():
        if month not in wanted:
            session.delete(row)


def seed_demo_workers(
    session: Session,
    selected: Dict[str, Dict[str, Any]],
    feature_names: Sequence[str],
    *,
    now_utc: Optional[datetime] = None,
) -> None:
    """Upsert the five owned demo personas; callers commit the transaction."""
    now_utc = now_utc or datetime.now(timezone.utc)
    for index, persona in enumerate(PERSONA_ORDER, start=1):
        selected_record = selected[persona]
        worker_id = f"{DEMO_WORKER_PREFIX}{persona}"
        consent_id = f"{DEMO_CONSENT_PREFIX}{persona}"
        phone = f"{DEMO_PHONE_PREFIX}{index}"
        monthly = _simulated_months(persona)

        _upsert_financial_record(session, phone, monthly)
        _upsert_consent(session, consent_id, worker_id, phone, persona, now_utc)
        _upsert_risk_profile(
            session,
            worker_id,
            _extract_features(selected_record, feature_names),
            now_utc,
        )
        _upsert_monthly_evidence(session, worker_id, monthly)


def _table_rows(
    session: Session, selected: Dict[str, Dict[str, Any]]
) -> List[List[str]]:
    rows: List[List[str]] = []
    for index, persona in enumerate(PERSONA_ORDER, start=1):
        worker_id = f"{DEMO_WORKER_PREFIX}{persona}"
        consent_id = f"{DEMO_CONSENT_PREFIX}{persona}"
        phone = f"{DEMO_PHONE_PREFIX}{index}"
        selected_record = selected[persona]
        try:
            response = run_verification(
                session,
                VerifyRequest(
                    worker_id=worker_id,
                    consent_id=consent_id,
                    phone_number=phone,
                ),
                persist=False,
            )
            recommendation = response.recommendation.code
            reliability = str(response.risk_signal.reliability or "n/a")
        except Exception as exc:  # noqa: BLE001 - table should still print
            recommendation = f"unavailable: {type(exc).__name__}"
            reliability = "n/a"

        flags = "".join(str(int(selected_record[flag])) for flag in HISTORY_FLAGS)
        rows.append(
            [
                PERSONA_LABELS[persona],
                worker_id,
                consent_id,
                str(selected_record["band"]),
                f"{float(selected_record['calibrated_pd']):.6f}",
                flags,
                reliability,
                recommendation,
            ]
        )
    return rows


def print_seed_table(session: Session, selected: Dict[str, Dict[str, Any]]) -> None:
    headers = [
        "persona",
        "worker_id",
        "consent_id",
        "risk band",
        "calibrated PD",
        "history flags",
        "risk reliability",
        "recommendation",
    ]
    rows = _table_rows(session, selected)
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]
    print(" | ".join(header.ljust(widths[i]) for i, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(value.ljust(widths[i]) for i, value in enumerate(row)))


def _create_engine(database_url: str, *, memory: bool = False):
    kwargs: Dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if memory:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(database_url, **kwargs)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed deterministic demo workers from local held-out data."
    )
    parser.add_argument(
        "--database-url",
        default=settings.DATABASE_URL,
        help="SQLAlchemy database URL (default: settings.DATABASE_URL).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the preview in an in-memory database without touching the target.",
    )
    parser.add_argument(
        "--allow-nonlocal",
        action="store_true",
        help="Allow a database URL whose host or name contains a production marker.",
    )
    args = parser.parse_args(argv)

    print(f"Database URL: {mask_database_url(args.database_url)}")
    if looks_like_production_url(args.database_url) and not args.allow_nonlocal:
        print(
            "Refusing to run: the database host or name looks like production. "
            "Pass --allow-nonlocal only if this is intentional."
        )
        return 2

    try:
        feature_names = load_feature_names()
        rows = load_heldout_rows(feature_names)
        selected = select_personas(rows)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Could not prepare demo personas: {exc}")
        return 1

    database_url = "sqlite:///:memory:" if args.dry_run else args.database_url
    engine = _create_engine(database_url, memory=args.dry_run)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        now_utc = datetime.now(timezone.utc)
        seed_demo_workers(session, selected, feature_names, now_utc=now_utc)
        session.commit()

        if args.dry_run:
            print("DRY RUN: preview uses an in-memory database; target was not written.")
        print_seed_table(session, selected)
        print(
            "UPI monthly amounts and sender counts are simulated, made-up "
            "demonstration values. Risk features come from local held-out rows of a "
            "public, non-Indian dataset that cannot be redistributed."
        )
    finally:
        session.close()
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
