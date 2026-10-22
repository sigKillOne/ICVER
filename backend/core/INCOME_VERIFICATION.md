# ICVER Income Verification Engine Specification

## 1. Overview & Architectural Principles

The ICVER Income Verification Engine is a **fully deterministic, rules-based engine** designed to evaluate alternative financial data sources (UPI monthly inflows and bank credit SMS logs) alongside self-reported application details to verify applicant income, estimate monthly obligations, and establish conservative repayment surplus.

### Key Governance Principles
- **Heuristic, Not Machine Learning:** Every rule, threshold, factor, and point allocation is an explicit, human-interpretable domain assumption. It is **not** a machine learning model and does not perform statistical regression or black-box inference.
- **No Ground-Truth Income Dataset Required:** In retail alternative-data underwriting, verified ground-truth earned income is often unavailable. This engine evaluates transaction presence, consistency, longitudinal persistence, and counterparty diversity rather than fitting to historical labels.
- **Strictly Deterministic & Reproducible:** The engine operates exclusively via the Python standard library. It utilizes zero pseudo-random number generators, databases, external network requests, or global mutable state. Identical input records will invariably yield identical output values.
- **Conservative Downside Protection:** Self-stated income is never used to inflate or establish conservative income bounds. The engine computes verified earnings from empirical transaction streams and discounts gross inflows to account for non-earnings noise.

---

## 2. Inflow Processing & Non-Duplication Rules

### Rule 1: Multi-Channel De-duplication (`max(UPI, SMS)`)
Because bank account SMS alerts and UPI transaction ledgers often capture identical underlying payment events, simply summing the two data streams leads to severe double-counting.
- For each concurrent monthly period, the engine evaluates:
  $$\text{Combined Inflow}_m = \max(\text{UPI Inflow}_m, \text{SMS Inflow}_m)$$
- Older months present in only one channel are preserved without artificial padding distortions.

### Rule 2: Inflow-to-Earned-Income Conversion (`INFLOW_TO_INCOME_FACTOR = 0.85`)
Gross credits into savings accounts frequently include non-earned cash flows, such as transfers between an applicant's own accounts, peer-to-peer debt reimbursements, refunds, and informal family loans.
- The engine applies a baseline factor of `0.85`, assuming that 85% of verified banking inflows represent net recurring earned income.
- With $\ge 3$ months of history, the engine computes:
  - $\text{income\_mid} = \text{Median}(\text{Inflows}) \times 0.85$
  - $\text{income\_low} = \text{Percentile}_{25}(\text{Inflows}) \times 0.85$
  - $\text{income\_high} = \text{Percentile}_{75}(\text{Inflows}) \times 0.85$
- Invariant: $\text{income\_low} \le \text{income\_mid} \le \text{income\_high}$ is strictly enforced.

### Rule 3: Short History Downside Widening
When fewer than 3 months of history exist:
- $\text{income\_low} = \min(\text{Inflows}) \times 0.85 \times \text{SHORT\_HISTORY\_LOW\_FACTOR}$ (`0.80`)
- $\text{income\_high} = \max(\text{Inflows}) \times 0.85 \times \text{SHORT\_HISTORY\_HIGH\_FACTOR}$ (`1.20`)
- This widens the confidence envelope to reflect elevated uncertainty rather than assuming tight distributional percentiles.

### Rule 4: Conservative Surplus & Outgoings Completeness
- Outgoings ($\text{monthly\_outgoings}$) are summed across rent, utilities, existing loan EMIs, mobile recharge, and miscellaneous expenses. Negatives and non-numeric values are safely ignored.
- **Living Cost Verification (`expenses_complete`):** Outgoings are checked for household living expenses against `LIVING_COST_KEYS` (`('food', 'groceries', 'living')`). If no recognized living cost key is provided, the `EXPENSES_INCOMPLETE` flag (severity `MEDIUM`) is raised and `expenses_complete = False`.
- Conservative monthly surplus is still calculated against the 25th percentile downside income, but downstream systems are alerted that surplus may be overstated:
  $$\text{monthly\_surplus\_conservative} = \max(0, \text{income\_low} - \text{estimated\_expenses})$$

---

## 3. Named Constants, Thresholds & Labeled Assumptions

Every parameter in the engine is a named constant declared at the top of `backend/core/income_verification.py`:

| Constant Name | Value | Type | Domain Rationale / Labeled Assumption |
| :--- | :---: | :---: | :--- |
| `INFLOW_TO_INCOME_FACTOR` | `0.85` | Float | 15% discount for intra-family transfers, refunds, and non-income credits. |
| `SHORT_HISTORY_LOW_FACTOR` | `0.80` | Float | Downside uncertainty discount for series with $< 3$ months of data. |
| `SHORT_HISTORY_HIGH_FACTOR` | `1.20` | Float | Upside uncertainty expansion for series with $< 3$ months of data. |
| `LIVING_COST_KEYS` | `('food', 'groceries', 'living')` | Tuple[str] | Recognized living-cost keys in outgoings to ensure complete living expense reporting. |
| `MIN_MONTHS_FULL_HISTORY` | `3` | Integer | Minimum longitudinal duration required for reliable quarterly percentile estimation. |
| `MIN_MONTHS_EXTENDED_HISTORY` | `6` | Integer | Threshold demonstrating long-term operational resilience and season-spanning stability. |
| `VOLATILITY_LOW_THRESHOLD` | `0.15` | Float | Coefficient of Variation (CV) $\le 15\%$ represents salaried, highly stable cash flow. |
| `VOLATILITY_HIGH_THRESHOLD` | `0.40` | Float | CV $> 40\%$ represents volatile gig, informal, or irregular earning patterns. |
| `FEW_SENDERS_THRESHOLD` | `3` | Integer | Median unique senders $< 3$/month indicates high client or employer concentration risk. |
| `MANY_SENDERS_THRESHOLD` | `10` | Integer | Median unique senders $\ge 10$/month indicates diverse retail customer counterparties. |
| `SOURCES_DISAGREE_THRESHOLD` | `0.30` | Float | Discrepancy $> 30\%$ between UPI and SMS in overlapping months triggers a disagreement flag. |
| `STATED_OVERSTATED_THRESHOLD` | `1.25` | Float | Stated income $> 125\%$ of verified median is flagged as overstated. |
| `STATED_CONSISTENT_MIN` | `0.85` | Float | Lower bound of consistent stated income ratio ($85\%$ of verified median). |
| `STATED_CONSISTENT_MAX` | `1.20` | Float | Upper bound of consistent stated income ratio ($120\%$ of verified median). |
| `CONFIDENCE_LOW_MAX` | `39` | Integer | Scores $\le 39$ classify as `LOW` confidence. |
| `CONFIDENCE_MEDIUM_MIN` | `40` | Integer | Scores $40 - 69$ classify as `MEDIUM` confidence. |
| `CONFIDENCE_HIGH_MIN` | `70` | Integer | Scores $\ge 70$ classify as `HIGH` confidence. |

---

## 4. Evidence Confidence Scoring System (0-100)

The confidence score is an additive composite across four independent underwriting dimensions:

$$\text{Confidence Score} = \text{Coverage} + \text{Agreement} + \text{Stability} + \text{Diversity}$$

### Dimension 1: Coverage (Max 30 Points)
Measures the duration and depth of empirical transaction history:
- **0 months:** 0 pts
- **1 month:** 10 pts
- **2 months:** 18 pts
- **3 to 5 months:** 25 pts
- **6+ months:** 30 pts

### Dimension 2: Agreement (Max 25 Points)
Measures consistency between self-reported income and empirical evidence, as well as cross-source agreement:
- **Stated vs Evidence Alignment (Max 15 pts):**
  - Stated income consistent (`STATED_CONSISTENT`, $0.85 - 1.20$): 15 pts
  - Stated income conservative / understated (`STATED_UNDERSTATED`, $< 0.85$): 15 pts (unpenalized)
  - Stated income mildly overstated ($1.25 < \text{ratio} \le 1.50$): 5 pts
  - Stated income severely overstated ($\text{ratio} > 1.50$): 0 pts
  - Stated income missing/omitted: 0 pts
- **Cross-Source Agreement (Max 10 pts):**
  - Both UPI and bank SMS present and agree ($\le 30\%$ discrepancy): 10 pts
  - Single data source provided (UPI only or SMS only): 5 pts
  - Both sources present but conflicting ($> 30\%$ discrepancy): 0 pts
  - Zero sources present: 0 pts

### Dimension 3: Stability (Max 25 Points)
Measures earning consistency via the Coefficient of Variation ($CV = \frac{\sigma}{\mu}$):
- **$CV \le 15\%$ (Salaried consistency):** 25 pts
- **$15\% < CV \le 30\%$ (Moderate variability):** 18 pts
- **$30\% < CV \le 40\%$ (Elevated variability):** 10 pts
- **$CV > 40\%$ (High volatility):** 3 pts
- **Single month baseline:** 10 pts
- **No data:** 0 pts

### Dimension 4: Counterparty Diversity (Max 20 Points)
Evaluates payer diversification to identify single-client or concentrated counterparty risk:
- **$\ge 10$ median monthly unique senders:** 20 pts
- **$5 - 9$ median senders:** 15 pts
- **$3 - 4$ median senders:** 10 pts
- **$1 - 2$ median senders:** 5 pts
- **Missing or 0 senders:** 0 pts

### Level Cap Policy (`confidence_capped`)
If any flag with severity `HIGH` is active on the applicant (such as `STATED_OVERSTATED` or `SOURCES_DISAGREE`):
- The `evidence_confidence_level` is capped at **`MEDIUM`**, even when the composite numeric score is $\ge 70$.
- The numeric score remains unaltered.
- The reason `"Confidence capped at MEDIUM because the stated income is not supported by the evidence"` is prioritized in the reason list.
- The output field `confidence_capped` is set to `True` (otherwise `False`).

---

## 5. Audit Flags & Categorization

The engine generates structured advisory flags (`{code, severity, message}`) to signal underwriting risks:

| Flag Code | Severity | Trigger Condition | Underwriting Implications |
| :--- | :---: | :--- | :--- |
| `NO_EVIDENCE` | `CRITICAL` | No valid inflows found in UPI or SMS. | Total lack of verification; income cannot be validated. |
| `STATED_OVERSTATED` | `HIGH` | Stated income $> 1.25 \times \text{income\_mid}$. | Potential applicant misrepresentation or exaggeration. Triggers confidence level cap. |
| `SOURCES_DISAGREE` | `HIGH` | $> 30\%$ discrepancy between concurrent UPI and SMS. | Discrepancy between stated banking and digital payment logs. Triggers confidence level cap. |
| `EXPENSES_INCOMPLETE` | `MEDIUM` | `monthly_outgoings` contains no living-cost key (`food`, `groceries`, `living`). | Monthly obligations understated; conservative surplus likely overstated. |
| `SHORT_HISTORY` | `MEDIUM` | $< 3$ months of inflow records. | High longitudinal uncertainty; bounds widened. |
| `HIGH_VOLATILITY` | `MEDIUM` | $CV > 40\%$ across monthly series. | Erratic income; requires wider cash buffers. |
| `FEW_SENDERS` | `MEDIUM` | Median monthly senders $< 3$. | Single-employer or counterparty concentration. |
| `SINGLE_SOURCE` | `INFO` | Only one data channel (UPI or SMS) provided. | Informational notice that cross-verification was unfeasible. |
| `STATED_CONSISTENT` | `INFO` | Stated income within $85\% - 120\%$ of evidence. | Favorable alignment between stated and actual credits. |
| `STATED_UNDERSTATED` | `INFO` | Stated income $< 85\%$ of evidence median. | Favorable conservatism by applicant. |

