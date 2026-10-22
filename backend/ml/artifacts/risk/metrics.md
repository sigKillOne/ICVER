# ICVER Repayment Risk Model - Training & Evaluation Metrics

**Training Timestamp:** 2026-10-22 09:49:37  
**Runtime:** 85.66 seconds  
**Target Dataset:** Home Credit Default Risk (`backend/data/processed/features_train.parquet`)

## 1. Dataset & Split Architecture
- **Total Population:** 307,511 applicants across 30 non-demographic features
- **Train Split (60%):** 184,506 rows (Default Rate: 8.0729%)
- **Validation Split (20%):** 61,502 rows (Default Rate: 8.0729%)
- **Test Split (20%):** 61,503 rows (Default Rate: 8.0728%)
- **Stratification:** Strict stratified sampling on `TARGET` with random seed 42

## 2. Model Performance Summary (Unseen Test Set)
| Metric | XGBoost (Calibrated) | Logistic Regression Baseline | Benchmark (with EXT_SOURCE) |
| :--- | :---: | :---: | :---: |
| **ROC AUC** | **0.72074** | 0.67837 | **0.76733** |
| **PR AUC** | **0.19441** | - | - |
| **KS Statistic** | **32.69%** (0.3269) | - | - |
| **Brier Score** | **0.06992** | 0.07165 | - |
| **Log Loss** | **0.25617** | 0.26521 | - |
| **Top Decile Lift** | **2.91x** | - | - |

## 3. Cross-Validation & Baseline Comparisons
- **5-Fold Stratified CV on Train Split:** Mean AUC = **0.71393** (std: **0.00357**)
- **Logistic Regression Baseline Test AUC:** **0.67837** (XGBoost improvement: **+4.24%** AUC)
- **External Source Lift (`features_train_with_ext.parquet`):** Test AUC = **0.76733** (adds **+4.66%** AUC over alternative-data features alone)

## 4. Probability Calibration (Isotonic Regression)
- **Calibration Method:** Isotonic regression fitted strictly on validation-set predictions.
- **Brier Score:** 0.06986 (raw) -> **0.06992** (calibrated)
- **Log Loss:** 0.25589 (raw) -> **0.25617** (calibrated)

### 10-Bin Calibration Table (Test Set)
| Bin | Count | Defaults | Mean Predicted PD | Observed Default Rate | Diff |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 6,151 | 108 | 1.59% | 1.76% | +0.0016 |
| 2 | 6,150 | 172 | 2.82% | 2.80% | -0.0002 |
| 3 | 6,150 | 217 | 4.00% | 3.53% | -0.0047 |
| 4 | 6,150 | 259 | 4.65% | 4.21% | -0.0044 |
| 5 | 6,151 | 348 | 5.03% | 5.66% | +0.0063 |
| 6 | 6,150 | 393 | 6.84% | 6.39% | -0.0045 |
| 7 | 6,150 | 532 | 8.22% | 8.65% | +0.0043 |
| 8 | 6,150 | 636 | 10.84% | 10.34% | -0.0050 |
| 9 | 6,150 | 853 | 13.24% | 13.87% | +0.0063 |
| 10 | 6,151 | 1,447 | 22.89% | 23.52% | +0.0064 |

## 5. Predicted Risk Deciles & Top-Decile Lift
| Decile | Applicants | Defaults | Default Rate | Lift vs Average | Mean Predicted PD |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 6,151 | 108 | **1.76%** | 0.22x | 1.59% |
| 2 | 6,150 | 172 | **2.80%** | 0.35x | 2.82% |
| 3 | 6,150 | 217 | **3.53%** | 0.44x | 4.00% |
| 4 | 6,150 | 259 | **4.21%** | 0.52x | 4.65% |
| 5 | 6,151 | 348 | **5.66%** | 0.70x | 5.03% |
| 6 | 6,150 | 393 | **6.39%** | 0.79x | 6.84% |
| 7 | 6,150 | 532 | **8.65%** | 1.07x | 8.22% |
| 8 | 6,150 | 636 | **10.34%** | 1.28x | 10.84% |
| 9 | 6,150 | 853 | **13.87%** | 1.72x | 13.24% |
| 10 | 6,151 | 1,447 | **23.52%** | 2.91x | 22.89% |

## 6. Risk Score & Policy Risk Bands
- **Score Formula:** `risk_score_0_100 = 100 - population_percentile(calibrated_PD)` (Higher score = Safer)
- **Policy Cutoffs (from Validation Quantiles):**
  - **LOW Risk:** Calibrated PD <= 5.03% (Lowest 40% of risk)
  - **MEDIUM Risk:** 5.03% < Calibrated PD <= 12.71% (Middle 40%)
  - **HIGH Risk:** Calibrated PD > 12.71% (Top 20% highest risk)
  > *Note: These cutoffs are a credit policy choice and can be tailored to the lender's risk tolerance and capital reserves.*

### Observed Default Rates by Risk Band (Test Set)
| Band | Applicants | Defaults | Observed Default Rate | Mean Predicted PD |
| :--- | :---: | :---: | :---: | :---: |
| **LOW** | 25,127 | 793 | **3.16%** | 3.30% |
| **MEDIUM** | 25,983 | 2,106 | **8.11%** | 8.15% |
| **HIGH** | 10,393 | 2,066 | **19.88%** | 19.05% |

## 7. Feature Importance (Top 15 by Gain)
| Rank | Feature Name | Total Gain |
| :---: | :--- | :---: |
| 1 | `prev_refused_share` | 26.75 |
| 2 | `years_employed` | 22.52 |
| 3 | `recent_late_share` | 21.54 |
| 4 | `credit_term_months` | 20.35 |
| 5 | `bureau_n_active` | 18.39 |
| 6 | `days_since_phone_change` | 16.66 |
| 7 | `has_prev_application` | 16.12 |
| 8 | `late_share` | 15.39 |
| 9 | `bureau_max_days_overdue` | 14.94 |
| 10 | `bureau_total_debt` | 12.39 |
| 11 | `n_prev_loans` | 11.93 |
| 12 | `mean_days_late` | 11.84 |
| 13 | `bureau_n_credits` | 11.12 |
| 14 | `income_total` | 10.14 |
| 15 | `log_income` | 9.73 |

## 8. SHAP Additivity Verification
- **Explainer:** `shap.TreeExplainer` on saved model
- **Sample Size:** 1,000 test observations
- **Verification:** `base_value + sum(shap_values) == margin_prediction` within `1e-3`
- **Maximum Observed Error:** `1.23977661e-05` (PASS)

## 9. Environment & Package Versions
- `python`: 3.14.8
- `xgboost`: 3.4.1
- `shap`: 0.52.0
- `sklearn`: 1.9.1
- `pandas`: 3.0.6
- `numpy`: 2.5.3
- `scipy`: 1.18.1
