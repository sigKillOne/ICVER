"""
Demo script illustrating the Deterministic Income Verification Engine.

Runs 4 illustrative, clearly labeled made-up examples:
1. Consistent Vendor / Retail Merchant (Dual-source, high sender diversity, consistent stated income)
2. Overstated Claim (Stated income significantly exceeds empirical banking credits)
3. SMS-Only Evidence (Single data channel, no UPI records)
4. Few-Senders Case (High inflow volume but concentrated single-payer counterparty risk)
"""

from backend.core.income_verification import EvidenceInput, verify


def print_case_result(case_num: int, title: str, description: str, evidence: EvidenceInput):
    print("=" * 80)
    print(f"CASE {case_num}: {title.upper()}")
    print("=" * 80)
    print(f"[NOTE: This is a purely hypothetical, synthetic illustrative profile]")
    print(f"Profile: {description}\n")

    print("Inputs:")
    print(f" - Stated Monthly Income: ₹{evidence.stated_monthly_income:,.2f}" if evidence.stated_monthly_income else " - Stated Monthly Income: Not Provided")
    print(f" - UPI Inflows ({len(evidence.upi_monthly_inflows)} mos): {evidence.upi_monthly_inflows}")
    print(f" - UPI Senders ({len(evidence.upi_unique_senders_per_month)} mos): {evidence.upi_unique_senders_per_month}")
    print(f" - Bank SMS Credits ({len(evidence.sms_monthly_credits)} mos): {evidence.sms_monthly_credits}")
    print(f" - Monthly Outgoings: {evidence.monthly_outgoings}")

    result = verify(evidence)

    print("\nVerified Assessment:")
    print(f" - Verified Income Mid:        ₹{result.income_mid:,.2f}" if result.income_mid else " - Verified Income Mid:        None")
    print(f" - Verified Income Range:      ₹{result.income_low:,.2f} to ₹{result.income_high:,.2f}" if result.income_low else " - Verified Income Range:      None")
    print(f" - Estimated Expenses:         ₹{result.estimated_expenses:,.2f}" if result.estimated_expenses else " - Estimated Expenses:         None")
    print(f" - Conservative Surplus:       ₹{result.monthly_surplus_conservative:,.2f}" if result.monthly_surplus_conservative is not None else " - Conservative Surplus:       None")
    print(f" - Stated vs Evidence Ratio:   {result.stated_vs_evidence_ratio:.2f}x" if result.stated_vs_evidence_ratio else " - Stated vs Evidence Ratio:   N/A")
    print(f" - Confidence Score:           {result.evidence_confidence_score}/100 ({result.evidence_confidence_level})")
    print(f" - Confidence Capped:          {result.confidence_capped}")
    print(f" - Expenses Complete:          {result.expenses_complete}")

    print("\nScore Components:")
    for comp, data in result.confidence_components.items():
        print(f"   * {comp.capitalize():<10}: {data['points']:>2} / {data['max']} pts")

    print(f"\nFlags ({len(result.flags)}):")
    if result.flags:
        for f in result.flags:
            print(f"   [{f['severity']}] {f['code']}: {f['message']}")
    else:
        print("   None (Clean Profile)")

    print(f"\nPrimary Reasons ({len(result.reasons)}):")
    for r in result.reasons:
        print(f"   - {r}")
    print("\n")


def main():
    print("*" * 80)
    print("ICVER DETERMINISTIC INCOME VERIFICATION DEMONSTRATION")
    print("Demonstrating 4 synthetic, illustrative applicant profiles")
    print("*" * 80)
    print()

    # Case 1: Consistent Vendor
    case_1 = EvidenceInput(
        stated_monthly_income=38000.0,
        upi_monthly_inflows=[42000.0, 46000.0, 44000.0, 45000.0, 47000.0, 46000.0],
        upi_unique_senders_per_month=[24, 28, 26, 25, 30, 29],
        sms_monthly_credits=[41000.0, 45500.0, 43500.0, 44800.0, 46500.0, 45800.0],
        monthly_outgoings={"rent": 9000.0, "utilities": 2500.0, "existing_emi": 3500.0, "groceries": 8000.0},
        household_size=4,
        occupation_type="Small Merchant / Retail Vendor",
    )
    print_case_result(
        1,
        "Consistent Retail Merchant",
        "Established local shopkeeper with 6 months of active UPI sales, cross-verified with bank SMS, high customer diversity, and consistent stated earnings.",
        case_1,
    )

    # Case 2: Overstated Claim
    case_2 = EvidenceInput(
        stated_monthly_income=85000.0,
        upi_monthly_inflows=[26000.0, 31000.0, 27000.0, 29000.0],
        upi_unique_senders_per_month=[8, 10, 7, 9],
        sms_monthly_credits=[25000.0, 30000.0, 26500.0, 28500.0],
        monthly_outgoings={"rent": 12000.0, "existing_emi": 9000.0},
        household_size=2,
        occupation_type="Freelance Consultant",
    )
    print_case_result(
        2,
        "Overstated Income Claim",
        "Applicant reported ₹85,000 monthly income, but verifiable transactional credits only substantiate ~₹24,000 net monthly earnings.",
        case_2,
    )

    # Case 3: SMS-Only Evidence
    case_3 = EvidenceInput(
        stated_monthly_income=22000.0,
        upi_monthly_inflows=[],  # No digital UPI logs
        upi_unique_senders_per_month=[],
        sms_monthly_credits=[25000.0, 25000.0, 26000.0, 25500.0],
        monthly_outgoings={"rent": 6000.0, "utilities": 1200.0, "recharge": 499.0},
        household_size=3,
        occupation_type="Factory Floor Supervisor",
    )
    print_case_result(
        3,
        "Bank SMS-Only Evidence",
        "Salaried worker with no UPI transaction integration whose salary credits are verified exclusively through bank SMS alerts.",
        case_3,
    )

    # Case 4: Few-Senders Case
    case_4 = EvidenceInput(
        stated_monthly_income=42000.0,
        upi_monthly_inflows=[50000.0, 50000.0, 50000.0, 50000.0, 50000.0],
        upi_unique_senders_per_month=[1, 1, 1, 1, 1],  # Only 1 recurring sender
        sms_monthly_credits=[50000.0, 50000.0, 50000.0, 50000.0, 50000.0],
        monthly_outgoings={"rent": 11000.0, "existing_emi": 5000.0},
        household_size=2,
        occupation_type="Contract Subcontractor",
    )
    print_case_result(
        4,
        "High Payer Concentration (Few Senders)",
        "Contract worker with strong, regular monthly payments of ₹50,000, but 100% dependent on a single individual counterparty.",
        case_4,
    )


if __name__ == "__main__":
    main()
