"""
Unit tests for the Deterministic Income Verification Engine.

Tests cover all 9 core rules, determinism, de-duplication, percentile invariants,
flag triggering, confidence scoring monotonicity, and robust handling of malformed inputs.
"""

import math
import json
import pytest
from backend.core.income_verification import (
    EvidenceInput,
    VerificationResult,
    verify,
    to_dict,
    INFLOW_TO_INCOME_FACTOR,
    SHORT_HISTORY_LOW_FACTOR,
    SHORT_HISTORY_HIGH_FACTOR,
    MIN_MONTHS_FULL_HISTORY,
    VOLATILITY_HIGH_THRESHOLD,
    FEW_SENDERS_THRESHOLD,
    SOURCES_DISAGREE_THRESHOLD,
    STATED_OVERSTATED_THRESHOLD,
)


def test_determinism_identical_runs():
    """Verify that running verify() multiple times on the same input produces identical output."""
    inp = EvidenceInput(
        stated_monthly_income=35000.0,
        upi_monthly_inflows=[30000.0, 32000.0, 31000.0, 33000.0],
        upi_unique_senders_per_month=[12, 15, 14, 16],
        sms_monthly_credits=[29000.0, 31000.0, 30500.0, 32500.0],
        monthly_outgoings={"rent": 8000.0, "utilities": 2500.0, "existing_emi": 4000.0},
        household_size=3,
        occupation_type="Self-Employed",
    )

    res1 = verify(inp)
    res2 = verify(inp)

    assert to_dict(res1) == to_dict(res2)
    assert res1.income_mid == res2.income_mid
    assert res1.evidence_confidence_score == res2.evidence_confidence_score
    assert res1.monthly_surplus_conservative == res2.monthly_surplus_conservative


def test_no_double_counting():
    """Verify that concurrent UPI and SMS credits for the same month use max(), never sum()."""
    # 1 month where UPI = 10,000 and SMS = 10,000
    inp = EvidenceInput(
        upi_monthly_inflows=[10000.0],
        sms_monthly_credits=[10000.0],
    )
    res = verify(inp)

    # Combined inflow must be 10,000, NOT 20,000.
    # income_mid = 10000 * 0.85 = 8500.0
    expected_mid = round(10000.0 * INFLOW_TO_INCOME_FACTOR, 2)
    assert res.income_mid == expected_mid
    assert res.income_mid != round(20000.0 * INFLOW_TO_INCOME_FACTOR, 2)

    # Overlapping 3 months with different maxes
    inp3 = EvidenceInput(
        upi_monthly_inflows=[10000.0, 25000.0, 30000.0],
        sms_monthly_credits=[12000.0, 20000.0, 30000.0],
    )
    # Combined series: [max(10k, 12k), max(25k, 20k), max(30k, 30k)] = [12000, 25000, 30000]
    res3 = verify(inp3)
    expected_mid3 = round(25000.0 * INFLOW_TO_INCOME_FACTOR, 2)  # median is 25000
    assert res3.income_mid == expected_mid3


def test_income_bounds_monotonicity():
    """Ensure income_low <= income_mid <= income_high across all history lengths."""
    test_cases = [
        # Single month
        [15000.0],
        # 2 months
        [12000.0, 18000.0],
        # 3 months identical
        [20000.0, 20000.0, 20000.0],
        # 4 months ascending
        [10000.0, 15000.0, 20000.0, 25000.0],
        # Volatile series
        [5000.0, 45000.0, 12000.0, 60000.0, 8000.0],
    ]

    for inflows in test_cases:
        inp = EvidenceInput(upi_monthly_inflows=inflows)
        res = verify(inp)
        assert res.income_low is not None
        assert res.income_mid is not None
        assert res.income_high is not None
        assert res.income_low <= res.income_mid, f"Failed for inflows {inflows}: low={res.income_low} > mid={res.income_mid}"
        assert res.income_mid <= res.income_high, f"Failed for inflows {inflows}: mid={res.income_mid} > high={res.income_high}"


def test_overstated_stated_income_lowers_score():
    """Verify that an applicant with an overstated stated income earns a lower confidence score."""
    inflows = [30000.0, 31000.0, 30000.0, 32000.0]
    # Verified median is ~30500 * 0.85 = ~25925

    # Applicant A: Consistent stated income
    inp_consistent = EvidenceInput(
        stated_monthly_income=26000.0,
        upi_monthly_inflows=inflows,
        upi_unique_senders_per_month=[10, 10, 10, 10],
    )
    res_consistent = verify(inp_consistent)

    # Applicant B: Grossly overstated stated income (₹75,000 vs ~₹26,000 evidence)
    inp_overstated = EvidenceInput(
        stated_monthly_income=75000.0,
        upi_monthly_inflows=inflows,
        upi_unique_senders_per_month=[10, 10, 10, 10],
    )
    res_overstated = verify(inp_overstated)

    assert res_overstated.evidence_confidence_score < res_consistent.evidence_confidence_score
    flag_codes = [f["code"] for f in res_overstated.flags]
    assert "STATED_OVERSTATED" in flag_codes


def test_more_months_never_lowers_score():
    """Verify that increasing the history length of consistent, stable data never decreases the score."""
    inp_1m = EvidenceInput(
        stated_monthly_income=25000.0,
        upi_monthly_inflows=[30000.0],
    )
    inp_3m = EvidenceInput(
        stated_monthly_income=25000.0,
        upi_monthly_inflows=[30000.0, 30000.0, 30000.0],
    )
    inp_6m = EvidenceInput(
        stated_monthly_income=25000.0,
        upi_monthly_inflows=[30000.0] * 6,
    )

    res_1m = verify(inp_1m)
    res_3m = verify(inp_3m)
    res_6m = verify(inp_6m)

    assert res_3m.evidence_confidence_score >= res_1m.evidence_confidence_score
    assert res_6m.evidence_confidence_score >= res_3m.evidence_confidence_score


def test_score_range_and_level_consistency():
    """Verify that confidence score is strictly bounded in [0, 100] and maps to correct level."""
    # Test varying configurations
    configs = [
        EvidenceInput(),  # empty
        EvidenceInput(upi_monthly_inflows=[1000.0]),  # minimal
        EvidenceInput(
            stated_monthly_income=42000.0,
            upi_monthly_inflows=[50000.0] * 6,
            sms_monthly_credits=[50000.0] * 6,
            upi_unique_senders_per_month=[15] * 6,
        ),  # ideal
    ]

    for cfg in configs:
        res = verify(cfg)
        assert 0 <= res.evidence_confidence_score <= 100
        if res.evidence_confidence_score >= 70:
            assert res.evidence_confidence_level == "HIGH"
        elif res.evidence_confidence_score >= 40:
            assert res.evidence_confidence_level == "MEDIUM"
        else:
            assert res.evidence_confidence_level == "LOW"


def test_empty_input_no_evidence_score_zero():
    """Verify that completely empty evidence returns score 0, LOW level, and NO_EVIDENCE flag without error."""
    empty_inp = EvidenceInput()
    res = verify(empty_inp)

    assert res.evidence_confidence_score == 0
    assert res.evidence_confidence_level == "LOW"
    assert res.income_low is None
    assert res.income_mid is None
    assert res.income_high is None
    assert res.monthly_surplus_conservative is None
    assert res.months_of_evidence == 0

    flag_codes = [f["code"] for f in res.flags]
    assert "NO_EVIDENCE" in flag_codes


def test_nan_none_negative_ignored_safely():
    """Verify that NaN, None, and negative numbers in input lists are safely filtered without exception."""
    inp = EvidenceInput(
        stated_monthly_income=-20000.0,  # invalid negative
        upi_monthly_inflows=[None, float("nan"), -10000.0, 25000.0, 30000.0],
        upi_unique_senders_per_month=[None, -5, 12, 14],
        monthly_outgoings={"rent": 8000.0, "bad_val": float("nan"), "neg": -500.0},
    )

    res = verify(inp)

    # Only 2 valid positive months: 25000.0 and 30000.0
    assert res.months_of_evidence == 2
    assert res.income_mid is not None
    # Expenses must safely ignore NaN and negatives: only 8000.0
    assert res.estimated_expenses == 8000.0


def test_stated_income_never_elevates_conservative_income():
    """Verify that stated income is never used to inflate conservative income above verified evidence."""
    # Stated income is huge (₹1,000,000) but evidence is modest (₹10,000/month)
    inp = EvidenceInput(
        stated_monthly_income=1000000.0,
        upi_monthly_inflows=[10000.0, 10000.0, 10000.0],
        monthly_outgoings={"rent": 3000.0},
    )
    res = verify(inp)

    # Conservative income is strictly derived from evidence, not stated income
    expected_low = round(10000.0 * INFLOW_TO_INCOME_FACTOR, 2)
    assert res.income_low == expected_low
    assert res.monthly_surplus_conservative == round(expected_low - 3000.0, 2)
    assert res.monthly_surplus_conservative < 100000.0


def test_single_source_evidence_raises_single_source_flag():
    """Verify that evidence with only UPI (or only SMS) raises the SINGLE_SOURCE flag."""
    inp_upi_only = EvidenceInput(
        upi_monthly_inflows=[20000.0, 22000.0, 21000.0],
        sms_monthly_credits=[],
    )
    res = verify(inp_upi_only)
    flag_codes = [f["code"] for f in res.flags]
    assert "SINGLE_SOURCE" in flag_codes

    inp_sms_only = EvidenceInput(
        upi_monthly_inflows=[],
        sms_monthly_credits=[18000.0, 19000.0],
    )
    res_sms = verify(inp_sms_only)
    assert "SINGLE_SOURCE" in [f["code"] for f in res_sms.flags]


def test_very_volatile_inflows_raise_high_volatility():
    """Verify that inflows with high month-to-month variation trigger the HIGH_VOLATILITY flag."""
    # Series with massive swing (CV well above 40%)
    inp_volatile = EvidenceInput(
        upi_monthly_inflows=[5000.0, 80000.0, 4000.0, 75000.0],
    )
    res = verify(inp_volatile)
    flag_codes = [f["code"] for f in res.flags]
    assert "HIGH_VOLATILITY" in flag_codes


def test_few_senders_raises_few_senders_flag():
    """Verify that low counterparty diversity (median senders < 3) triggers FEW_SENDERS flag."""
    inp = EvidenceInput(
        upi_monthly_inflows=[25000.0, 25000.0, 25000.0],
        upi_unique_senders_per_month=[1, 2, 1],  # median = 1 < 3
    )
    res = verify(inp)
    flag_codes = [f["code"] for f in res.flags]
    assert "FEW_SENDERS" in flag_codes


def test_sources_disagree_triggers_flag():
    """Verify that when overlapping UPI and SMS diverge by > 30%, SOURCES_DISAGREE is triggered."""
    inp = EvidenceInput(
        upi_monthly_inflows=[50000.0, 55000.0],
        sms_monthly_credits=[10000.0, 12000.0],  # > 70% divergence
    )
    res = verify(inp)
    flag_codes = [f["code"] for f in res.flags]
    assert "SOURCES_DISAGREE" in flag_codes
    assert res.confidence_components["agreement"]["points"] < 25


def test_understated_stated_income_not_penalized():
    """Verify that an understated stated income earns the STATED_UNDERSTATED flag and full consistency points."""
    # Verified median is ~30,000 * 0.85 = 25,500
    # Applicant conservatively stated 15,000
    inp = EvidenceInput(
        stated_monthly_income=15000.0,
        upi_monthly_inflows=[30000.0, 30000.0, 30000.0],
        upi_unique_senders_per_month=[8, 8, 8],
    )
    res = verify(inp)
    flag_codes = [f["code"] for f in res.flags]
    assert "STATED_UNDERSTATED" in flag_codes
    # Should not be penalised: stated agreement points are 15
    assert res.confidence_components["agreement"]["points"] >= 15


def test_expenses_surplus_floored_at_zero():
    """Verify that if monthly expenses exceed income_low, the conservative surplus is floored at 0.0."""
    inp = EvidenceInput(
        upi_monthly_inflows=[20000.0, 20000.0, 20000.0],  # income_low ~ 17,000
        monthly_outgoings={"rent": 15000.0, "loan_emi": 10000.0},  # total 25,000
    )
    res = verify(inp)
    assert res.estimated_expenses == 25000.0
    assert res.monthly_surplus_conservative == 0.0


def test_to_dict_json_serialisable():
    """Verify that to_dict(result) returns a valid JSON-serialisable dictionary."""
    inp = EvidenceInput(
        stated_monthly_income=28000.0,
        upi_monthly_inflows=[30000.0, 32000.0, 31000.0],
        upi_unique_senders_per_month=[10, 12, 11],
        sms_monthly_credits=[29000.0, 31000.0, 30000.0],
        monthly_outgoings={"rent": 6000.0, "utilities": 1500.0, "groceries": 5000.0},
    )
    res = verify(inp)
    res_dict = to_dict(res)

    # Must serialize to JSON without throwing TypeError
    json_str = json.dumps(res_dict)
    assert isinstance(json_str, str)
    reloaded = json.loads(json_str)
    assert reloaded["evidence_confidence_score"] == res.evidence_confidence_score
    assert "confidence_capped" in reloaded
    assert "expenses_complete" in reloaded
    assert reloaded["expenses_complete"] is True


def test_overstated_claim_never_gets_level_high_even_with_score_70_plus():
    """Verify that an applicant with STATED_OVERSTATED is capped at MEDIUM even with score >= 70."""
    # 4 months stable data, 8-10 senders, stated income ₹85,000 vs ~₹24,000 evidence
    # Score: coverage 25 + agreement 10 + stability 25 + diversity 15 = 75 (>= 70)
    inp = EvidenceInput(
        stated_monthly_income=85000.0,
        upi_monthly_inflows=[26000.0, 31000.0, 27000.0, 29000.0],
        upi_unique_senders_per_month=[8, 10, 7, 9],
        sms_monthly_credits=[25000.0, 30000.0, 26500.0, 28500.0],
        monthly_outgoings={"rent": 12000.0, "groceries": 5000.0},
    )
    res = verify(inp)

    # Numeric score must remain unchanged and >= 70
    assert res.evidence_confidence_score >= 70
    # Level must be capped at MEDIUM (never HIGH)
    assert res.evidence_confidence_level == "MEDIUM"
    assert res.confidence_capped is True
    # Reason must explain the cap in plain language
    assert "Confidence capped at MEDIUM because the stated income is not supported by the evidence" in res.reasons


def test_confidence_capped_is_false_for_consistent_case():
    """Verify that confidence_capped is False for a consistent applicant with score >= 70."""
    inp = EvidenceInput(
        stated_monthly_income=38000.0,
        upi_monthly_inflows=[42000.0, 46000.0, 44000.0, 45000.0, 47000.0, 46000.0],
        upi_unique_senders_per_month=[24, 28, 26, 25, 30, 29],
        sms_monthly_credits=[41000.0, 45500.0, 43500.0, 44800.0, 46500.0, 45800.0],
        monthly_outgoings={"rent": 9000.0, "groceries": 8000.0},
    )
    res = verify(inp)

    assert res.evidence_confidence_score >= 70
    assert res.evidence_confidence_level == "HIGH"
    assert res.confidence_capped is False
    assert not any("Confidence capped" in r for r in res.reasons)


def test_expenses_incomplete_when_no_living_cost_provided():
    """Verify that EXPENSES_INCOMPLETE flag is raised when outgoings omit food/groceries/living."""
    inp = EvidenceInput(
        upi_monthly_inflows=[30000.0, 30000.0, 30000.0],
        monthly_outgoings={"rent": 10000.0, "utilities": 2000.0, "existing_emi": 4000.0},
    )
    res = verify(inp)

    assert res.expenses_complete is False
    flag_codes = [f["code"] for f in res.flags]
    assert "EXPENSES_INCOMPLETE" in flag_codes
    # Downstream consumers still receive monthly_surplus_conservative
    assert res.monthly_surplus_conservative is not None
    assert any("Expenses may be understated: no food or living costs were provided" in r for r in res.reasons)


def test_expenses_complete_when_groceries_provided():
    """Verify that expenses_complete is True and EXPENSES_INCOMPLETE flag is absent when groceries is given."""
    inp = EvidenceInput(
        upi_monthly_inflows=[30000.0, 30000.0, 30000.0],
        monthly_outgoings={"rent": 10000.0, "groceries": 6000.0},
    )
    res = verify(inp)

    assert res.expenses_complete is True
    flag_codes = [f["code"] for f in res.flags]
    assert "EXPENSES_INCOMPLETE" not in flag_codes


def test_living_cost_keys_accepted_tuple_and_case_insensitivity():
    """Verify all keys in LIVING_COST_KEYS ('food', 'groceries', 'living') are accepted case-insensitively."""
    from backend.core.income_verification import LIVING_COST_KEYS
    assert "food" in LIVING_COST_KEYS
    assert "groceries" in LIVING_COST_KEYS
    assert "living" in LIVING_COST_KEYS

    for key_name in ["FOOD", " Food ", "Living", "Groceries", " living "]:
        inp = EvidenceInput(
            upi_monthly_inflows=[25000.0, 25000.0, 25000.0],
            monthly_outgoings={"rent": 8000.0, key_name: 4000.0},
        )
        res = verify(inp)
        assert res.expenses_complete is True, f"Failed for key '{key_name}'"
        assert "EXPENSES_INCOMPLETE" not in [f["code"] for f in res.flags]

