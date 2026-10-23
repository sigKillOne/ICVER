"""Unit tests for the pure monthly evidence consistency checks."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core.consistency_checks import (
    CONSTANT_INFLOW,
    EVIDENCE_GAP,
    EVIDENCE_MALFORMED,
    LATEST_MONTH_SPIKE,
    SENDER_DROP,
    check_evidence_consistency,
)
from backend.core.recommendation import PROCEED_TO_UNDERWRITING, recommend


def record(month, inflow, senders=None):
    return {"year_month": month, "inflow": inflow, "unique_senders": senders}


def codes(flags):
    return {flag["code"] for flag in flags}


def test_gap_of_exactly_one_month_is_medium():
    flags = check_evidence_consistency(
        [
            record("2025-01", 10000.0, 10),
            record("2025-02", 10000.0, 10),
            record("2025-04", 10000.0, 10),
        ]
    )
    gap = next(flag for flag in flags if flag["code"] == EVIDENCE_GAP)
    assert gap["severity"] == "MEDIUM"
    assert "1" in gap["message"]


def test_contiguous_months_have_no_gap():
    flags = check_evidence_consistency(
        [
            record("2025-01", 10000.0, 10),
            record("2025-02", 10000.0, 10),
            record("2025-03", 10000.0, 10),
        ]
    )
    assert EVIDENCE_GAP not in codes(flags)


def test_spike_just_above_threshold_is_flagged():
    flags = check_evidence_consistency(
        [
            record("2025-01", 10000.0, 10),
            record("2025-02", 10000.0, 10),
            record("2025-03", 10000.0, 10),
            record("2025-04", 20000.01, 10),
        ]
    )
    assert LATEST_MONTH_SPIKE in codes(flags)


def test_spike_just_below_threshold_is_not_flagged():
    flags = check_evidence_consistency(
        [
            record("2025-01", 10000.0, 10),
            record("2025-02", 10000.0, 10),
            record("2025-03", 10000.0, 10),
            record("2025-04", 19999.99, 10),
        ]
    )
    assert LATEST_MONTH_SPIKE not in codes(flags)


def test_spike_not_evaluated_under_minimum_months():
    flags = check_evidence_consistency(
        [
            record("2025-01", 10000.0, 10),
            record("2025-02", 10000.0, 10),
            record("2025-03", 100000.0, 10),
        ]
    )
    assert LATEST_MONTH_SPIKE not in codes(flags)


def test_constant_inflow_at_four_identical_months():
    flags = check_evidence_consistency(
        [
            record("2025-01", 25000.0, 10),
            record("2025-02", 25000.0, 10),
            record("2025-03", 25000.0, 10),
            record("2025-04", 25000.0, 10),
        ]
    )
    assert CONSTANT_INFLOW in codes(flags)


def test_constant_inflow_not_flagged_for_three_months():
    flags = check_evidence_consistency(
        [
            record("2025-01", 25000.0, 10),
            record("2025-02", 25000.0, 10),
            record("2025-03", 25000.0, 10),
        ]
    )
    assert CONSTANT_INFLOW not in codes(flags)


def test_sender_drop_at_threshold_is_flagged():
    flags = check_evidence_consistency(
        [
            record("2025-01", 25000.0, 20),
            record("2025-02", 25000.0, 20),
            record("2025-03", 25000.0, 20),
            record("2025-04", 25000.0, 10),
        ]
    )
    assert SENDER_DROP in codes(flags)


def test_sender_drop_above_threshold_is_not_flagged():
    flags = check_evidence_consistency(
        [
            record("2025-01", 25000.0, 20),
            record("2025-02", 25000.0, 20),
            record("2025-03", 25000.0, 20),
            record("2025-04", 25000.0, 11),
        ]
    )
    assert SENDER_DROP not in codes(flags)


def test_malformed_year_month_is_ignored_with_flag():
    flags = check_evidence_consistency(
        [
            record("2025-13", 10000.0, 10),
            record("not-a-month", None, None),
            record("2025-01", 10000.0, 10),
        ]
    )
    assert codes(flags) == {EVIDENCE_MALFORMED}
    malformed = flags[0]
    assert malformed["severity"] == "INFO"
    assert "2" in malformed["message"]


def test_empty_and_bad_values_never_raise_or_divide():
    assert check_evidence_consistency([]) == []
    assert check_evidence_consistency(None) == []

    flags = check_evidence_consistency(
        [
            record("2025-01", None, None),
            record("2025-02", float("nan"), None),
            record("2025-03", -5000.0, -2),
            record("2025-04", 0.0, 0),
            record("2025-05", float("inf"), None),
        ]
    )
    assert all(flag["severity"] in {"INFO", "MEDIUM"} for flag in flags)
    assert LATEST_MONTH_SPIKE not in codes(flags)
    assert SENDER_DROP not in codes(flags)


def test_checks_are_deterministic():
    months = [
        record("2025-01", 25000.0, 20),
        record("2025-02", 25000.0, 20),
        record("2025-03", 25000.0, 20),
        record("2025-05", 90000.0, 3),
    ]
    assert check_evidence_consistency(months) == check_evidence_consistency(months)


def test_flags_never_have_high_severity():
    flags = check_evidence_consistency(
        [
            record("2025-01", 25000.0, 20),
            record("2025-02", 25000.0, 20),
            record("bad-month", 25000.0, 20),
            record("2025-04", 90000.0, 2),
        ]
    )
    assert flags
    assert all(flag["severity"] in {"INFO", "MEDIUM"} for flag in flags)


def test_messages_do_not_use_fraud_wording():
    flags = check_evidence_consistency(
        [
            record("2025-01", 25000.0, 20),
            record("2025-02", 25000.0, 20),
            record("2025-04", 90000.0, 2),
        ]
    )
    assert all("fraud" not in flag["message"].lower() for flag in flags)


def fake_evidence(flags):
    return SimpleNamespace(
        flags=flags,
        evidence_confidence_level="HIGH",
        evidence_confidence_score=95,
        expenses_complete=True,
    )


def test_consistency_flags_do_not_change_code_but_add_caveat():
    risk = {"available": True, "band": "LOW", "reliability": "NORMAL"}
    affordability = {"proposed_emi": 1000, "max_affordable_emi": 5000}
    baseline = recommend(fake_evidence([]), risk, affordability)
    with_spike = recommend(
        fake_evidence(
            [
                {
                    "code": LATEST_MONTH_SPIKE,
                    "severity": "MEDIUM",
                    "message": "Latest month stands out.",
                    "source": "consistency_checks",
                }
            ]
        ),
        risk,
        affordability,
    )
    assert baseline["code"] == PROCEED_TO_UNDERWRITING
    assert with_spike["code"] == baseline["code"]
    assert len(with_spike["caveats"]) == len(baseline["caveats"]) + 1
    assert "Consistency check" in with_spike["caveats"][-1]


@pytest.mark.parametrize(
    "occupation,expected_caveat",
    [("Street vendor", True), ("Driver", False)],
)
def test_constant_inflow_caveat_only_for_vendor(occupation, expected_caveat):
    result = recommend(
        fake_evidence(
            [
                {
                    "code": CONSTANT_INFLOW,
                    "severity": "INFO",
                    "message": "The same monthly inflow appears in four months.",
                    "source": "consistency_checks",
                }
            ]
        ),
        {"available": True, "band": "LOW", "reliability": "NORMAL"},
        {"proposed_emi": 1000, "max_affordable_emi": 5000},
        occupation_type=occupation,
    )
    has_constant_caveat = any(
        "same monthly inflow" in caveat for caveat in result["caveats"]
    )
    assert has_constant_caveat is expected_caveat
