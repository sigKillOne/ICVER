"""
Deterministic Income Verification Engine for ICVER.

Combines non-traditional alternative data sources (UPI transaction streams,
bank credit SMS logs) and stated application inputs into verified monthly income
bands (low, mid, high), estimated monthly expenses, conservative disposable surplus,
and a transparent evidence confidence score (0-100).

Strictly heuristic and deterministic: standard library only, no ML, no DB,
no external networks, no random states.
"""

from dataclasses import dataclass, field, asdict
import math
import statistics
from typing import Optional, List, Dict, Any, Tuple


# ==============================================================================
# NAMED CONSTANTS & LABELED ASSUMPTIONS (NO MAGIC NUMBERS)
# ==============================================================================

# --- Inflow Conversion & Uncertainty Discount Factors ---
# Assumption: Inflows to transaction accounts include non-income credits (transfers from
# family/self, refunds, informal loans). 85% is a conservative discount factor for net earned income.
INFLOW_TO_INCOME_FACTOR: float = 0.85

# Assumption: For short histories (< 3 months), downside and upside uncertainty are wider.
SHORT_HISTORY_LOW_FACTOR: float = 0.80
SHORT_HISTORY_HIGH_FACTOR: float = 1.20

# --- History Length Thresholds ---
# Threshold: At least 3 months are required for multi-month percentile and stability evaluation.
MIN_MONTHS_FULL_HISTORY: int = 3
# Threshold: 6 or more months represents extended, high-confidence longitudinal evidence.
MIN_MONTHS_EXTENDED_HISTORY: int = 6

# --- Volatility (Coefficient of Variation) Thresholds ---
# Threshold: CV <= 15% denotes stable, regular salary-like inflows.
VOLATILITY_LOW_THRESHOLD: float = 0.15
# Threshold: CV > 40% denotes elevated month-to-month volatility (seasonal, gig, or irregular).
VOLATILITY_HIGH_THRESHOLD: float = 0.40

# --- Counterparty Sender Diversity Thresholds ---
# Threshold: Fewer than 3 unique senders per month indicates single-employer or concentrated counterparty risk.
FEW_SENDERS_THRESHOLD: int = 3
# Threshold: 10 or more unique senders per month indicates diverse commercial customer flow.
MANY_SENDERS_THRESHOLD: int = 10

# --- Dual-Source Discrepancy Threshold ---
# Threshold: Monthly UPI vs bank SMS credits differing by > 30% in concurrent months indicates conflicting records.
SOURCES_DISAGREE_THRESHOLD: float = 0.30

# --- Stated vs Evidence Ratio Bands ---
# Threshold: Stated income exceeding evidence median by > 25% (ratio > 1.25) is flagged as overstated.
STATED_OVERSTATED_THRESHOLD: float = 1.25
# Band: Stated income between 85% and 120% of evidence median is deemed consistent with banking records.
STATED_CONSISTENT_MIN: float = 0.85
STATED_CONSISTENT_MAX: float = 1.20

# --- Confidence Score Component Maximums (Sum = 100) ---
MAX_COVERAGE_POINTS: int = 30
MAX_AGREEMENT_POINTS: int = 25
MAX_STABILITY_POINTS: int = 25
MAX_DIVERSITY_POINTS: int = 20

# Coverage scoring points breakdown
POINTS_COVERAGE_0_MONTHS: int = 0
POINTS_COVERAGE_1_MONTH: int = 10
POINTS_COVERAGE_2_MONTHS: int = 18
POINTS_COVERAGE_3_TO_5_MONTHS: int = 25
POINTS_COVERAGE_6_PLUS_MONTHS: int = 30

# Agreement scoring points breakdown
# (Stated Agreement max: 15, Sources Agreement max: 10 => 25 total)
POINTS_STATED_CONSISTENT: int = 15
POINTS_STATED_UNDERSTATED: int = 15
POINTS_STATED_MILD_OVERSTATED: int = 5
POINTS_STATED_SEVERE_OVERSTATED: int = 0
POINTS_STATED_MISSING: int = 0

POINTS_SOURCES_BOTH_AGREE: int = 10
POINTS_SOURCES_SINGLE: int = 5
POINTS_SOURCES_DISAGREE: int = 0
POINTS_SOURCES_NONE: int = 0

# Stability scoring points breakdown (based on CV)
POINTS_STABILITY_EXCELLENT: int = 25  # CV <= 0.15
POINTS_STABILITY_MODERATE: int = 18   # 0.15 < CV <= 0.30
POINTS_STABILITY_FAIR: int = 10       # 0.30 < CV <= 0.40
POINTS_STABILITY_POOR: int = 3        # CV > 0.40
POINTS_STABILITY_SINGLE_MONTH: int = 10
POINTS_STABILITY_NONE: int = 0

# Diversity scoring points breakdown (based on median senders)
POINTS_DIVERSITY_HIGH: int = 20       # >= 10 senders
POINTS_DIVERSITY_MEDIUM: int = 15     # 5 - 9 senders
POINTS_DIVERSITY_LOW: int = 10        # 3 - 4 senders
POINTS_DIVERSITY_MINIMAL: int = 5     # 1 - 2 senders
POINTS_DIVERSITY_NONE: int = 0        # 0 or missing senders

# --- Living Cost Expense Keys ---
# Defined tuple of accepted living expense keys (food, groceries, living).
LIVING_COST_KEYS: Tuple[str, ...] = ("food", "groceries", "living")

# --- Confidence Level Thresholds ---
CONFIDENCE_LOW_MAX: int = 39
CONFIDENCE_MEDIUM_MIN: int = 40
CONFIDENCE_MEDIUM_MAX: int = 69
CONFIDENCE_HIGH_MIN: int = 70


# ==============================================================================
# INPUT & OUTPUT DATACLASSES
# ==============================================================================

@dataclass
class EvidenceInput:
    """Alternative data inputs provided for income verification."""
    stated_monthly_income: Optional[float] = None
    upi_monthly_inflows: List[float] = field(default_factory=list)
    upi_unique_senders_per_month: List[int] = field(default_factory=list)
    sms_monthly_credits: List[float] = field(default_factory=list)
    monthly_outgoings: Dict[str, float] = field(default_factory=dict)
    household_size: Optional[int] = None
    occupation_type: Optional[str] = None  # Informational only, not used in score


@dataclass
class VerificationResult:
    """Deterministic output of the income verification engine."""
    income_low: Optional[float]
    income_mid: Optional[float]
    income_high: Optional[float]
    estimated_expenses: Optional[float]
    monthly_surplus_conservative: Optional[float]
    evidence_confidence_score: int
    evidence_confidence_level: str
    confidence_components: Dict[str, Dict[str, int]]
    stated_vs_evidence_ratio: Optional[float]
    flags: List[Dict[str, str]]
    reasons: List[str]
    months_of_evidence: int
    confidence_capped: bool = False
    expenses_complete: bool = True


# ==============================================================================
# INTERNAL SANITIZATION & HELPER FUNCTIONS
# ==============================================================================

def _sanitize_numeric_list(raw_list: Any) -> List[float]:
    """Sanitize and extract positive/non-negative floats, ignoring NaNs, Nones, and negatives."""
    if not isinstance(raw_list, list):
        return []
    cleaned: List[float] = []
    for val in raw_list:
        if val is None:
            continue
        if isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                continue
            if val >= 0:
                cleaned.append(float(val))
    return cleaned


def _sanitize_int_list(raw_list: Any) -> List[int]:
    """Sanitize integers, ignoring NaNs, Nones, and negatives."""
    if not isinstance(raw_list, list):
        return []
    cleaned: List[int] = []
    for val in raw_list:
        if val is None:
            continue
        if isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                continue
            if val >= 0:
                cleaned.append(int(val))
    return cleaned


def _combine_sources(
    clean_upi: List[float],
    clean_sms: List[float],
) -> Tuple[List[float], List[Tuple[float, float]], bool, bool]:
    """
    Combine UPI and SMS monthly series without double counting.
    For each overlapping month, uses max(UPI, SMS).
    Right-aligns both series (oldest to newest, latest month aligned).
    Returns (combined_series, concurrent_pairs, has_upi, has_sms).
    """
    has_upi = len(clean_upi) > 0 and any(v > 0 for v in clean_upi)
    has_sms = len(clean_sms) > 0 and any(v > 0 for v in clean_sms)

    n_months = max(len(clean_upi), len(clean_sms))
    if n_months == 0:
        return [], [], has_upi, has_sms

    # Pad shorter series from the left (older months) with None
    padded_upi: List[Optional[float]] = [None] * (n_months - len(clean_upi)) + clean_upi
    padded_sms: List[Optional[float]] = [None] * (n_months - len(clean_sms)) + clean_sms

    combined: List[float] = []
    concurrent_pairs: List[Tuple[float, float]] = []

    for u, s in zip(padded_upi, padded_sms):
        if u is not None and s is not None:
            combined.append(max(u, s))
            concurrent_pairs.append((u, s))
        elif u is not None:
            combined.append(u)
        elif s is not None:
            combined.append(s)

    return combined, concurrent_pairs, has_upi, has_sms


# ==============================================================================
# MAIN VERIFICATION ENGINE
# ==============================================================================

def verify(evidence: EvidenceInput) -> VerificationResult:
    """
    Execute deterministic income verification rules on the provided evidence.
    Returns a structured, JSON-serialisable VerificationResult.
    """
    flags: List[Dict[str, str]] = []
    reasons: List[str] = []

    # 1. Sanitize Inflows & Combine Sources (Rule 1: Never double count)
    clean_upi = _sanitize_numeric_list(evidence.upi_monthly_inflows)
    clean_sms = _sanitize_numeric_list(evidence.sms_monthly_credits)
    clean_senders = _sanitize_int_list(evidence.upi_unique_senders_per_month)

    combined_series, concurrent_pairs, has_upi, has_sms = _combine_sources(clean_upi, clean_sms)
    months_of_evidence = len(combined_series)

    # 2. Check for Single Source & Source Disagreements (Rule 6)
    has_source_disagreement = False
    if has_upi and has_sms and len(concurrent_pairs) > 0:
        disagreements = []
        for u_val, s_val in concurrent_pairs:
            denom = max(u_val, s_val)
            if denom > 0:
                diff_ratio = abs(u_val - s_val) / denom
                if diff_ratio > SOURCES_DISAGREE_THRESHOLD:
                    disagreements.append((u_val, s_val, diff_ratio))
        if len(disagreements) > 0:
            has_source_disagreement = True
            max_diff = max(d[2] for d in disagreements)
            flags.append({
                "code": "SOURCES_DISAGREE",
                "severity": "HIGH",
                "message": f"UPI and SMS monthly totals diverge by {max_diff:.1%} in overlapping periods.",
            })
            reasons.append(f"Discrepancy detected between UPI inflows and bank SMS credits (divergence up to {max_diff:.1%}).")
    elif (has_upi and not has_sms) or (has_sms and not has_upi):
        source_name = "UPI inflows" if has_upi else "Bank SMS credits"
        flags.append({
            "code": "SINGLE_SOURCE",
            "severity": "INFO",
            "message": f"Evidence derived exclusively from single source ({source_name}).",
        })
        reasons.append(f"Single data source available ({source_name}); cross-channel verification unavailable.")

    # 3. Check Expenses & Completeness (Rule 3)
    estimated_expenses: Optional[float] = None
    has_living_cost = False
    if isinstance(evidence.monthly_outgoings, dict) and len(evidence.monthly_outgoings) > 0:
        exp_sum = 0.0
        for exp_key, exp_val in evidence.monthly_outgoings.items():
            if isinstance(exp_val, (int, float)) and not math.isnan(exp_val) and exp_val > 0:
                exp_sum += float(exp_val)
                if str(exp_key).strip().lower() in LIVING_COST_KEYS:
                    has_living_cost = True
        estimated_expenses = round(exp_sum, 2)
    elif months_of_evidence > 0:
        estimated_expenses = 0.0

    expenses_complete = has_living_cost
    if not expenses_complete:
        flags.append({
            "code": "EXPENSES_INCOMPLETE",
            "severity": "MEDIUM",
            "message": "Monthly outgoings omit basic living or food costs; estimated surplus may be overstated.",
        })
        reasons.append("Expenses may be understated: no food or living costs were provided, so the surplus is likely overstated")

    # 4. Handle Case of Zero Evidence (Rule 4)
    if months_of_evidence == 0 or all(v == 0 for v in combined_series):
        flags.append({
            "code": "NO_EVIDENCE",
            "severity": "CRITICAL",
            "message": "No valid transactional banking or UPI inflows provided.",
        })
        reasons.append("No banking, UPI, or SMS evidence was submitted to verify income.")

        comp_dict = {
            "coverage": {"points": 0, "max": MAX_COVERAGE_POINTS},
            "agreement": {"points": 0, "max": MAX_AGREEMENT_POINTS},
            "stability": {"points": 0, "max": MAX_STABILITY_POINTS},
            "diversity": {"points": 0, "max": MAX_DIVERSITY_POINTS},
        }

        return VerificationResult(
            income_low=None,
            income_mid=None,
            income_high=None,
            estimated_expenses=estimated_expenses,
            monthly_surplus_conservative=None,
            evidence_confidence_score=0,
            evidence_confidence_level="LOW",
            confidence_components=comp_dict,
            stated_vs_evidence_ratio=None,
            flags=flags,
            reasons=reasons,
            months_of_evidence=0,
            confidence_capped=False,
            expenses_complete=expenses_complete,
        )

    # 5. Compute Evidence Income Bands (Rule 2)
    if months_of_evidence == 1:
        base_val = combined_series[0]
        income_mid = round(base_val * INFLOW_TO_INCOME_FACTOR, 2)
        income_low = round(base_val * INFLOW_TO_INCOME_FACTOR * SHORT_HISTORY_LOW_FACTOR, 2)
        income_high = round(base_val * INFLOW_TO_INCOME_FACTOR * SHORT_HISTORY_HIGH_FACTOR, 2)
    elif months_of_evidence == 2:
        med_val = statistics.median(combined_series)
        min_val = min(combined_series)
        max_val = max(combined_series)
        income_mid = round(med_val * INFLOW_TO_INCOME_FACTOR, 2)
        income_low = round(min_val * INFLOW_TO_INCOME_FACTOR * SHORT_HISTORY_LOW_FACTOR, 2)
        income_high = round(max_val * INFLOW_TO_INCOME_FACTOR * SHORT_HISTORY_HIGH_FACTOR, 2)
    else:
        # 3 or more months of data: compute 25th, median, 75th percentiles
        q_cuts = statistics.quantiles(combined_series, n=4)
        q25, q75 = q_cuts[0], q_cuts[2]
        med_val = statistics.median(combined_series)
        income_mid = round(med_val * INFLOW_TO_INCOME_FACTOR, 2)
        income_low = round(q25 * INFLOW_TO_INCOME_FACTOR, 2)
        income_high = round(q75 * INFLOW_TO_INCOME_FACTOR, 2)

    # Enforce invariant: income_low <= income_mid <= income_high
    income_low = min(income_low, income_mid)
    income_high = max(income_high, income_mid)

    # 6. Monthly Surplus Conservative (income_low minus expenses, floored at 0)
    surplus_raw = income_low - (estimated_expenses if estimated_expenses is not None else 0.0)
    monthly_surplus_conservative = round(max(0.0, surplus_raw), 2)

    # 7. Check History Length & Volatility (Rule 6)
    if months_of_evidence < MIN_MONTHS_FULL_HISTORY:
        flags.append({
            "code": "SHORT_HISTORY",
            "severity": "MEDIUM",
            "message": f"Only {months_of_evidence} month(s) of history available (recommended: {MIN_MONTHS_FULL_HISTORY}+).",
        })
        reasons.append(f"Short transaction history ({months_of_evidence} month(s)); uncertainty bounds widened.")

    cv = 0.0
    if months_of_evidence >= 2:
        mean_val = statistics.mean(combined_series)
        stdev_val = statistics.stdev(combined_series)
        cv = stdev_val / mean_val if mean_val > 0 else 0.0
        if cv > VOLATILITY_HIGH_THRESHOLD:
            flags.append({
                "code": "HIGH_VOLATILITY",
                "severity": "MEDIUM",
                "message": f"Inflow volatility is high (coefficient of variation: {cv:.1%}).",
            })
            reasons.append(f"High income volatility observed across months (CV: {cv:.1%}).")

    # 8. Check Counterparty Senders Diversity (Rule 6)
    med_senders: Optional[float] = None
    if len(clean_senders) > 0:
        med_senders = float(statistics.median(clean_senders))
        if med_senders < FEW_SENDERS_THRESHOLD:
            flags.append({
                "code": "FEW_SENDERS",
                "severity": "MEDIUM",
                "message": f"Median unique senders per month is {med_senders:.1f} (< {FEW_SENDERS_THRESHOLD}), indicating payer concentration.",
            })
            reasons.append(f"Income originates from few counterparties (median {med_senders:.0f} senders/month).")

    # 9. Stated vs Evidence Ratio & Flags (Rule 5)
    stated_vs_evidence_ratio: Optional[float] = None
    clean_stated: Optional[float] = None
    if isinstance(evidence.stated_monthly_income, (int, float)) and not math.isnan(evidence.stated_monthly_income):
        if evidence.stated_monthly_income > 0:
            clean_stated = float(evidence.stated_monthly_income)

    stated_agreement_points = POINTS_STATED_MISSING

    if clean_stated is not None and income_mid > 0:
        stated_vs_evidence_ratio = round(clean_stated / income_mid, 3)
        if stated_vs_evidence_ratio > STATED_OVERSTATED_THRESHOLD:
            flags.append({
                "code": "STATED_OVERSTATED",
                "severity": "HIGH",
                "message": f"Stated income ({clean_stated:,.0f}) exceeds verified evidence ({income_mid:,.0f}) by {(stated_vs_evidence_ratio - 1.0):.1%}.",
            })
            reasons.append(f"Stated income of ₹{clean_stated:,.0f} exceeds verified monthly evidence (₹{income_mid:,.0f}) by {(stated_vs_evidence_ratio - 1.0):.1%}.")
            if stated_vs_evidence_ratio <= 1.50:
                stated_agreement_points = POINTS_STATED_MILD_OVERSTATED
            else:
                stated_agreement_points = POINTS_STATED_SEVERE_OVERSTATED
        elif STATED_CONSISTENT_MIN <= stated_vs_evidence_ratio <= STATED_CONSISTENT_MAX:
            flags.append({
                "code": "STATED_CONSISTENT",
                "severity": "INFO",
                "message": f"Stated income ({clean_stated:,.0f}) aligns with verified evidence ({income_mid:,.0f}).",
            })
            reasons.append(f"Stated income aligns closely with verified monthly banking evidence.")
            stated_agreement_points = POINTS_STATED_CONSISTENT
        elif stated_vs_evidence_ratio < STATED_CONSISTENT_MIN:
            flags.append({
                "code": "STATED_UNDERSTATED",
                "severity": "INFO",
                "message": f"Stated income ({clean_stated:,.0f}) is conservative relative to verified evidence ({income_mid:,.0f}).",
            })
            reasons.append(f"Stated income is conservative relative to verified transaction volume.")
            stated_agreement_points = POINTS_STATED_UNDERSTATED
    else:
        stated_agreement_points = POINTS_STATED_MISSING

    # 10. Compute 4 Confidence Components (Rule 7, Max = 100)
    # Component A: Coverage (Max 30)
    if months_of_evidence >= MIN_MONTHS_EXTENDED_HISTORY:
        coverage_points = POINTS_COVERAGE_6_PLUS_MONTHS
    elif months_of_evidence >= MIN_MONTHS_FULL_HISTORY:
        coverage_points = POINTS_COVERAGE_3_TO_5_MONTHS
    elif months_of_evidence == 2:
        coverage_points = POINTS_COVERAGE_2_MONTHS
    elif months_of_evidence == 1:
        coverage_points = POINTS_COVERAGE_1_MONTH
    else:
        coverage_points = POINTS_COVERAGE_0_MONTHS

    # Component B: Agreement (Max 25 = Stated max 15 + Sources max 10)
    if has_upi and has_sms:
        sources_points = POINTS_SOURCES_DISAGREE if has_source_disagreement else POINTS_SOURCES_BOTH_AGREE
    elif has_upi or has_sms:
        sources_points = POINTS_SOURCES_SINGLE
    else:
        sources_points = POINTS_SOURCES_NONE

    agreement_points = stated_agreement_points + sources_points

    # Component C: Stability (Max 25)
    if months_of_evidence >= 2:
        if cv <= VOLATILITY_LOW_THRESHOLD:
            stability_points = POINTS_STABILITY_EXCELLENT
        elif cv <= 0.30:
            stability_points = POINTS_STABILITY_MODERATE
        elif cv <= VOLATILITY_HIGH_THRESHOLD:
            stability_points = POINTS_STABILITY_FAIR
        else:
            stability_points = POINTS_STABILITY_POOR
    elif months_of_evidence == 1:
        stability_points = POINTS_STABILITY_SINGLE_MONTH
    else:
        stability_points = POINTS_STABILITY_NONE

    # Component D: Diversity (Max 20)
    if med_senders is not None:
        if med_senders >= MANY_SENDERS_THRESHOLD:
            diversity_points = POINTS_DIVERSITY_HIGH
        elif med_senders >= 5:
            diversity_points = POINTS_DIVERSITY_MEDIUM
        elif med_senders >= FEW_SENDERS_THRESHOLD:
            diversity_points = POINTS_DIVERSITY_LOW
        elif med_senders >= 1:
            diversity_points = POINTS_DIVERSITY_MINIMAL
        else:
            diversity_points = POINTS_DIVERSITY_NONE
    else:
        # Missing inputs earn zero for that component
        diversity_points = POINTS_DIVERSITY_NONE

    total_score = coverage_points + agreement_points + stability_points + diversity_points
    total_score = max(0, min(100, int(total_score)))

    # Determine confidence level with Level Cap rule
    has_high_severity_flag = any(f.get("severity") == "HIGH" for f in flags)
    confidence_capped = False

    if total_score >= CONFIDENCE_HIGH_MIN:
        if has_high_severity_flag:
            confidence_level = "MEDIUM"
            confidence_capped = True
            reasons.insert(0, "Confidence capped at MEDIUM because the stated income is not supported by the evidence")
        else:
            confidence_level = "HIGH"
    elif total_score >= CONFIDENCE_MEDIUM_MIN:
        confidence_level = "MEDIUM"
    else:
        confidence_level = "LOW"

    # Add primary positive reasons if no critical flags
    if len(reasons) == 0 or all(f["severity"] == "INFO" for f in flags):
        if months_of_evidence >= MIN_MONTHS_FULL_HISTORY:
            reasons.insert(0, f"Verified across {months_of_evidence} months of sustained banking records.")
        if cv <= VOLATILITY_LOW_THRESHOLD and months_of_evidence >= 2:
            reasons.append("Highly stable recurring inflow patterns observed.")
        if med_senders is not None and med_senders >= MANY_SENDERS_THRESHOLD:
            reasons.append(f"Strong sender diversity (median {med_senders:.0f} counterparties/month).")

    confidence_components = {
        "coverage": {"points": coverage_points, "max": MAX_COVERAGE_POINTS},
        "agreement": {"points": agreement_points, "max": MAX_AGREEMENT_POINTS},
        "stability": {"points": stability_points, "max": MAX_STABILITY_POINTS},
        "diversity": {"points": diversity_points, "max": MAX_DIVERSITY_POINTS},
    }

    return VerificationResult(
        income_low=income_low,
        income_mid=income_mid,
        income_high=income_high,
        estimated_expenses=estimated_expenses,
        monthly_surplus_conservative=monthly_surplus_conservative,
        evidence_confidence_score=total_score,
        evidence_confidence_level=confidence_level,
        confidence_components=confidence_components,
        stated_vs_evidence_ratio=stated_vs_evidence_ratio,
        flags=flags,
        reasons=reasons,
        months_of_evidence=months_of_evidence,
        confidence_capped=confidence_capped,
        expenses_complete=expenses_complete,
    )


def to_dict(result: VerificationResult) -> Dict[str, Any]:
    """Convert VerificationResult dataclass into a JSON-serialisable dictionary."""
    return asdict(result)
