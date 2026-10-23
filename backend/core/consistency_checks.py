"""Simple, deterministic consistency checks on monthly aggregate evidence.

These checks look only at month-level UPI totals and monthly unique-sender counts. They
are consistency heuristics, not fraud detection, and they cannot detect circular transfers
or round-tripping; that needs per-transaction data such as account-aggregator data. The
thresholds below are product assumptions, not values learned from data.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Sequence, Tuple

EVIDENCE_GAP = "EVIDENCE_GAP"
EVIDENCE_MALFORMED = "EVIDENCE_MALFORMED"
LATEST_MONTH_SPIKE = "LATEST_MONTH_SPIKE"
CONSTANT_INFLOW = "CONSTANT_INFLOW"
SENDER_DROP = "SENDER_DROP"

SEVERITY_INFO = "INFO"
SEVERITY_MEDIUM = "MEDIUM"

# Assumption: a month-to-month jump above 2x the earlier median is worth a second look.
SPIKE_RATIO = 2.0
# Assumption: spike checks need at least four months so the earlier median is meaningful.
MIN_MONTHS_FOR_SPIKE = 4
# Assumption: four identical monthly totals are enough to mention as a pattern.
MIN_MONTHS_FOR_CONSTANT = 4
# Assumption: a latest-month sender count at or below half the earlier median is a drop.
SENDER_DROP_RATIO = 0.5
# Assumption: sender checks need at least four months of sender data.
MIN_MONTHS_FOR_SENDERS = 4

CONSISTENCY_NOTE = (
    "These are simple consistency checks on monthly aggregates; they cannot detect "
    "circular transfers or round-tripping, which needs per-transaction data such as "
    "account-aggregator data. They are assumptions, not learned from data."
)

_YEAR_MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _field(record: Any, name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(name)
    if isinstance(record, (tuple, list)):
        positions = {"year_month": 0, "inflow": 1, "unique_senders": 2}
        position = positions.get(name)
        if position is not None and position < len(record):
            return record[position]
        return None
    return getattr(record, name, None)


def _month_index(value: Any) -> Optional[int]:
    if not isinstance(value, str):
        return None
    match = _YEAR_MONTH_PATTERN.fullmatch(value)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    return year * 12 + (month - 1)


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return numeric


def _valid_inflow(value: Any) -> Optional[float]:
    numeric = _finite_number(value)
    if numeric is None or numeric < 0.0:
        return None
    return numeric


def _valid_senders(value: Any) -> Optional[int]:
    numeric = _finite_number(value)
    if numeric is None or numeric < 0.0:
        return None
    return int(numeric)


def _flag(code: str, severity: str, message: str) -> Dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def check_evidence_consistency(months: Sequence[Any]) -> List[Dict[str, str]]:
    """Return non-blocking consistency flags for sorted monthly evidence records.

    Each record may be a mapping or an object with ``year_month``, ``inflow`` and
    ``unique_senders`` fields. Malformed months and bad numeric values are ignored rather
    than raising. Empty input returns an empty list.
    """
    if not months:
        return []

    malformed_count = 0
    by_month: Dict[int, Tuple[float, Optional[int]]] = {}
    for record in months:
        month_index = _month_index(_field(record, "year_month"))
        if month_index is None:
            malformed_count += 1
            continue
        inflow = _valid_inflow(_field(record, "inflow"))
        if inflow is None:
            continue
        senders = _valid_senders(_field(record, "unique_senders"))
        by_month[month_index] = (inflow, senders)

    flags: List[Dict[str, str]] = []
    if malformed_count:
        flags.append(
            _flag(
                EVIDENCE_MALFORMED,
                SEVERITY_INFO,
                f"{malformed_count} evidence month value(s) had an invalid YYYY-MM "
                "format and were ignored.",
            )
        )

    if not by_month:
        return flags

    ordered_months = sorted(by_month)
    missing_months = (
        ordered_months[-1] - ordered_months[0] + 1 - len(ordered_months)
    )
    if missing_months > 0:
        flags.append(
            _flag(
                EVIDENCE_GAP,
                SEVERITY_MEDIUM,
                f"Evidence is missing for {missing_months} calendar month(s) between "
                "the first and last month; the lender may want to confirm the history "
                "is complete.",
            )
        )

    inflows = [by_month[month][0] for month in ordered_months]
    if len(inflows) >= MIN_MONTHS_FOR_SPIKE:
        earlier = inflows[:-1]
        earlier_median = float(statistics.median(earlier))
        latest = inflows[-1]
        if earlier_median > 0.0 and latest > SPIKE_RATIO * earlier_median:
            flags.append(
                _flag(
                    LATEST_MONTH_SPIKE,
                    SEVERITY_MEDIUM,
                    f"The latest month's inflow is {latest / earlier_median:.1f}x the "
                    "median of earlier months; this can indicate a one-off deposit "
                    "shortly before an application, so the lender may want to confirm "
                    "the source.",
                )
            )

    positive_inflows = [value for value in inflows if value > 0.0]
    if len(positive_inflows) >= MIN_MONTHS_FOR_CONSTANT:
        repeated_inflow, repeated_count = Counter(positive_inflows).most_common(1)[0]
        if repeated_count >= MIN_MONTHS_FOR_CONSTANT:
            flags.append(
                _flag(
                    CONSTANT_INFLOW,
                    SEVERITY_INFO,
                    f"The same monthly inflow of \u20b9{repeated_inflow:,.2f} appears "
                    f"in {repeated_count} months; this is common for salaried or "
                    "contract income but unusual for vendor income, so the lender may "
                    "want to confirm the source.",
                )
            )

    sender_records = [
        by_month[month][1]
        for month in ordered_months
        if by_month[month][1] is not None
    ]
    latest_senders = by_month[ordered_months[-1]][1]
    if (
        latest_senders is not None
        and len(sender_records) >= MIN_MONTHS_FOR_SENDERS
        and len(ordered_months) >= 2
    ):
        earlier_senders = [
            senders
            for _, senders in (by_month[month] for month in ordered_months[:-1])
            if senders is not None
        ]
        if earlier_senders:
            sender_median = float(statistics.median(earlier_senders))
            if (
                sender_median > 0.0
                and latest_senders <= SENDER_DROP_RATIO * sender_median
            ):
                flags.append(
                    _flag(
                        SENDER_DROP,
                        SEVERITY_INFO,
                        f"The latest month has {latest_senders} unique senders, versus "
                        f"a median of {sender_median:.1f} in earlier months; this can "
                        "indicate a narrower counterparty base.",
                    )
                )

    return flags
