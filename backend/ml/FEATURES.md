# ICVER Feature Store Documentation: Home Credit Default Risk

## 1. Overview & Context

This document outlines the feature engineering architecture and feature definitions for the **ICVER (Intelligent Credit Verification & Explainable Risk)** modeling pipeline, migrated from synthetic training data to the real-world **Home Credit Default Risk** dataset.

The core training table is stored at `backend/data/processed/features_train.parquet` (307,511 rows, 32 columns: `SK_ID_CURR`, `TARGET`, and 30 model features).

> [!NOTE]
> **Proxy Nature & Dataset Limitations**:
> The Home Credit Default Risk dataset represents global retail lending data (predominantly Eastern European / Central Asian consumer loan portfolios). In the production ICVER vision for the Indian financial ecosystem, features will be derived directly from Account Aggregator frameworks, UPI transaction flows, and bank SMS parsing (e.g. `backend/core/parser.py`). 
> 
> Because this Kaggle dataset does not contain UPI handles, P2P/P2M transaction timestamps, or Indian bank SMS text alerts, the engineered features here act as **macro-behavioral proxies** for income stability, debt service capacity, and repayment discipline.

---

## 2. Core Feature Catalog

| Feature Name | Source File | Raw Column / Formula | ICVER Concept | Definition & Meaning | Proxy Quality & Limitations |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `income_total` | `application_train.csv` | `AMT_INCOME_TOTAL.clip(upper=p99_9)` | Income & Affordability | Total annual declared income of the client, capped at the 99.9th percentile (900,000) to trim extreme outliers. | **Fair proxy** for earning capacity, but self-reported/declared without GSTN/ITR or Account Aggregator bank statement verification. |
| `log_income` | `application_train.csv` | `np.log1p(income_total)` | Income & Affordability | Natural logarithm of capped income to compress heavy right skew. | **Good proxy** for relative income scale; stabilizes variance across income tiers. |
| `annuity_to_income` | `application_train.csv` | `AMT_ANNUITY / AMT_INCOME_TOTAL` | Income & Affordability | Ratio of scheduled loan annuity payment to total annual income (Debt-to-Income / DTI proxy). | **Strong proxy** for immediate repayment burden; clients in Q5 (highest ratio) default at 8.52% vs 7.20% in Q1. |
| `credit_to_income` | `application_train.csv` | `AMT_CREDIT / AMT_INCOME_TOTAL` | Income & Affordability | Total loan credit amount requested divided by annual income. | **Fair proxy** for leverage ratio relative to borrower size. |
| `credit_term_months` | `application_train.csv` | `AMT_CREDIT / AMT_ANNUITY` | Income & Affordability | Approximate loan amortization term in payment periods (credit amount divided by annuity). | **Good proxy** for requested loan duration. Longer terms show slightly lower default rates due to lower installment strain. |
| `income_per_family_member` | `application_train.csv` | `AMT_INCOME_TOTAL / CNT_FAM_MEMBERS` | Income & Affordability | Per-capita disposable household income adjusted for family size. | **Strong proxy** for net disposable surplus after basic household subsistence. |
| `years_employed` | `application_train.csv` | `-DAYS_EMPLOYED / 365.0` (with `365243 -> NaN`) | Stability | Length of continuous employment in years prior to application. Sentinel value `365243` (~1000 yrs, pensioners/unemployed) replaced with `NaN`. | **High-predictive proxy** for job tenure and income stability. Q1 (least tenure) has 11.24% default rate vs 5.19% in Q5. |
| `days_employed_anomaly` | `application_train.csv` | `(DAYS_EMPLOYED == 365243).astype(int)` | Stability | Binary indicator (1 if client had the `365243` sentinel code, 0 otherwise). | **Clean indicator** for pensioners or individuals outside formal workforce. |
| `days_since_phone_change` | `application_train.csv` | `-DAYS_LAST_PHONE_CHANGE` | Stability | Number of days since the applicant last changed their contact phone number. | **Excellent stability proxy** for contact stability and fraud avoidance. Q1 (changed phone <161 days ago) default rate: 9.43% vs 5.74% in Q5. |
| `years_since_id_published` | `application_train.csv` | `-DAYS_ID_PUBLISH / 365.0` | Stability | Number of years since applicant's national identity document was issued/renewed. | **Proxy for adult identity vintage**; newly issued IDs correlate with higher default (9.99% in Q1 vs 6.06% in Q5). |
| `years_registered` | `application_train.csv` | `-DAYS_REGISTRATION / 365.0` | Stability | Number of years since applicant's residential registration change. | **Proxy for residential stability**; frequent relocations correlate with higher risk (9.37% in Q1 vs 6.12% in Q5). |
| `cnt_children` | `application_train.csv` | `CNT_CHILDREN` | Stability | Number of dependent children in applicant's custody. | **Direct demographic attribute** reflecting dependent burden. |
| `cnt_fam_members` | `application_train.csv` | `CNT_FAM_MEMBERS` | Stability | Total household family member count. | **Direct demographic attribute** capturing total household size. |
| `has_installment_history` | `installments_payments.csv` | `(n_installments > 0).astype(int)` | Repayment Discipline | Binary indicator showing whether applicant has prior loan payment history in Home Credit. | **History flag**; separates unbanked/first-time borrowers from repeat borrowers. |
| `n_prev_loans` | `installments_payments.csv` | `SK_ID_PREV.nunique()` | Repayment Discipline | Number of distinct historical loans serviced by applicant. | **Borrowing experience proxy**; repeat successful borrowers default at lower rates (6.79% in Q5 vs 8.98% in Q1). |
| `n_installments` | `installments_payments.csv` | Count of installment records | Repayment Discipline | Total volume of historical scheduled installment events. | **Repayment activity proxy**; measures depth of credit track record. |
| `late_share` | `installments_payments.csv` | Mean of `(DAYS_ENTRY_PAYMENT > DAYS_INSTALMENT)` | Repayment Discipline | Share of historical payments made after the scheduled due date (ignoring zero-amount installments). | **High-predictive proxy** for repayment punctuality. Q5 (frequent late payers) default at 11.33% vs 6.88% in Q1 (1.65x risk). |
| `underpaid_share` | `installments_payments.csv` | Mean of `(AMT_PAYMENT < AMT_INSTALMENT)` | Repayment Discipline | Share of historical installments where amount deposited was strictly less than scheduled installment. | **High-predictive proxy** for cash-flow shortfalls. Q5 default rate: 11.28% vs 7.16% in Q1 (1.58x risk). |
| `mean_days_late` | `installments_payments.csv` | Mean of `(DAYS_ENTRY - DAYS_INSTAL).clip(0)` | Repayment Discipline | Average delinquency delay in days across all historical installments. | **Severity proxy** for payment delays; distinguishes minor 1-day slips from multi-month arrears. |
| `max_days_late` | `installments_payments.csv` | Max of `(DAYS_ENTRY - DAYS_INSTAL).clip(0)` | Repayment Discipline | Maximum single historical delinquency delay in days experienced by client. | **Stress event proxy**; captures worst historical default/delinquency event. |
| `missing_payment_share` | `installments_payments.csv` | Mean of `DAYS_ENTRY_PAYMENT.isna()` | Repayment Discipline | Proportion of scheduled installments with no recorded entry payment. | **Non-payment proxy**; captures missed payments. |
| `recent_late_share` | `installments_payments.csv` | Late share on installments with `DAYS_INSTALMENT >= -365` | Repayment Discipline | Share of installments entered late in the 12 months immediately preceding application. | **Top-tier predictive signal**; recent delinquency strongly forecasts default: 12.55% in Q5 vs 6.74% in Q1 (1.86x risk). |
| `has_bureau_history` | `bureau.csv` | `(bureau_n_credits > 0).astype(int)` | Existing Debt | Binary flag indicating presence in external Credit Bureau registry. | **Formal credit file indicator**; unbanked borrowers (no bureau file) have 9.41% default rate vs 7.61% with history. |
| `bureau_n_credits` | `bureau.csv` | Total count of bureau credits | Existing Debt | Total number of formal loans reported by other institutions to Credit Bureau. | **External credit exposure proxy**; captures credit market activity. |
| `bureau_n_active` | `bureau.csv` | Count where `CREDIT_ACTIVE == 'Active'` | Existing Debt | Count of currently ongoing, active external loans at application time. | **Active debt burden proxy**; applicants with 3+ active external loans show 10.07% default rate vs 7.86% in Q1. |
| `bureau_total_debt` | `bureau.csv` | Sum of `AMT_CREDIT_SUM_DEBT` across bureau loans | Existing Debt | Aggregate outstanding debt balances owed to other financial institutions. | **High-value leverage proxy**; Q5 (heaviest debt) default rate: 9.07% vs 5.56% in Q1 (1.63x risk). |
| `bureau_max_days_overdue` | `bureau.csv` | Max of `CREDIT_DAY_OVERDUE` | Existing Debt | Maximum days past due currently reported across all external bureau credit lines. | **External delinquency proxy**; tracks delinquency with outside institutions. |
| `has_prev_application` | `previous_application.csv` | `(prev_n_apps > 0).astype(int)` | Prior Inquiries | Binary flag indicating prior loan applications submitted to Home Credit. | **Relationship vintage flag**. |
| `prev_n_apps` | `previous_application.csv` | Total count of prior applications | Prior Inquiries | Total number of loan applications previously submitted. | **Credit appetite proxy**; frequent applications (8+ apps) increase default risk to 9.17% vs 7.80% in Q1. |
| `prev_refused_share` | `previous_application.csv` | Share where `NAME_CONTRACT_STATUS == 'Refused'` | Prior Inquiries | Percentage of past loan requests that were rejected by underwriting. | **High-predictive underwriting proxy**; Q5 (heavy prior rejections) defaults at 12.05% vs 7.13% in Q1 (1.69x risk). |

---

## 3. Fair Lending, Protected Attributes & Bias Audit

In compliance with anti-discrimination and fair lending principles, protected demographic attributes are strictly segregated:

1. **Excluded from Model Features**:
   - `CODE_GENDER` (Biological sex / gender identity)
   - `DAYS_BIRTH` / `age_years` (Applicant age)
   
   These variables are **NOT** present in `features_train.parquet` or `features_train_with_ext.parquet`. The model cannot form direct decision trees or linear weights on gender or age.

2. **Fairness Audit Parquet (`backend/data/processed/audit_columns.parquet`)**:
   - Saved with exact columns: `SK_ID_CURR`, `CODE_GENDER`, `age_years`.
   - Used downstream for post-hoc fairness audits (evaluating Equal Opportunity, Disparate Impact Ratio, and Calibration across gender and age cohorts) to verify that model decisions maintain parity.

---

## 4. External Credit Scoring Ratings (`EXT_SOURCE_1/2/3`)

- **Definition**: `EXT_SOURCE_1`, `EXT_SOURCE_2`, and `EXT_SOURCE_3` are normalized risk scores derived from third-party credit rating agencies (external bureaus analogous to CIBIL or Experian in India).
- **Partitioning Strategy**:
  - `backend/data/processed/features_train.parquet`: Ommits `EXT_SOURCE` features. This enforces models to evaluate creditworthiness purely on alternative data, internal repayment behavior, and borrower stability.
  - `backend/data/processed/features_train_with_ext.parquet`: Generated via `python -m backend.ml.features_home_credit --include-ext-sources`. Includes `ext_source_1`, `ext_source_2`, and `ext_source_3` as benchmark features to contrast alternative data performance against established credit bureau ratings.

---

## 5. v2 exclusions

v1 of the repayment-risk model (`backend/ml/train_risk_model.py`, 30 features) includes several columns whose **units cannot be mapped onto Indian informal workers' monthly rupee figures**. The Home Credit Default Risk dataset does not document the currency of amount fields or whether income is monthly, annual, or something else. ICVER's production path estimates income in INR from UPI/SMS evidence with a separate rule-based engine, so the risk model must not depend on those incommensurable amounts.

v2 (`backend/ml/train_risk_model_v2.py`) therefore **excludes these 6 features** and trains on the remaining **24**:

| Excluded feature | Why it is dropped |
| :--- | :--- |
| `income_total` | Declared income amount; currency and income period are undocumented, so it cannot be mapped to monthly INR. |
| `log_income` | Transform of `income_total`; same unit problem. |
| `income_per_family_member` | `income_total / CNT_FAM_MEMBERS`; still an undocumented-currency income amount. |
| `annuity_to_income` | Mixes loan annuity with undocumented income; not a portable affordability ratio for India. |
| `credit_to_income` | Mixes credit amount with undocumented income; same mapping failure. |
| `bureau_total_debt` | Sum of bureau `AMT_CREDIT_SUM_DEBT` in undocumented currency; cannot be mapped to INR outstanding debt. |

**Kept on purpose:** `credit_term_months` (`AMT_CREDIT / AMT_ANNUITY`). Both sides of the ratio are amounts in the **same** (unknown) currency, so the unit cancels and the feature is a duration-like term, not a rupee figure.

Income, debt-service, and affordability for Indian workers remain **rule-based** (FOIR, surplus, verified-income engine), not inputs to this classifier.

v2 uses the same stratified 60/20/20 split, seed 42, XGBoost hyperparameters, early stopping, and isotonic calibration as v1 so the two models can be compared on the same test `SK_ID_CURR` set. Artifacts live in `backend/ml/artifacts/risk_v2/`.
