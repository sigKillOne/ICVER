# ICVER Repayment Risk Model v2 — Training & Evaluation Metrics

**Training Timestamp:** 2026-10-23 12:03:04  
**Runtime:** 91.25 seconds  
**Target Dataset:** Home Credit Default Risk (`backend/data/processed/features_train.parquet`)

## 1. Why v2 exists
v1 used six features whose units cannot be mapped to Indian workers' monthly rupee figures because the Home Credit currency and income period are undocumented. v2 drops those six features and retrains with the same split, seed, XGBoost hyperparameters, early stopping, and isotonic calibration as v1. `credit_term_months` is kept because it is a ratio of two amounts in the same currency. Income and affordability stay in rule-based code, not in this model.

### Excluded features
| Feature | Reason |
| :--- | :--- |
| `income_total` | Home Credit income currency and reporting period are undocumented, so this amount cannot be mapped to Indian workers' monthly rupee figures. |
| `log_income` | Derived from income_total; inherits the same undocumented currency and period. |
| `income_per_family_member` | Derived from income_total divided by family size; units cannot be mapped to INR. |
| `annuity_to_income` | Ratio of annuity to undocumented income; numerator and denominator currencies are not independently usable in an Indian rupee affordability engine. |
| `credit_to_income` | Ratio of credit amount to undocumented income; cannot be mapped to monthly INR. |
| `bureau_total_debt` | Aggregate bureau debt is in the dataset's undocumented currency and cannot be mapped to Indian rupee outstanding balances. |

- **v2 feature count:** 24 (v1 had 30)
- **Seed:** 42

## 2. Dataset & split (identical to v1)
- **Total population:** 307,511 applicants
- **Train (60%):** 184,506 rows (default rate 8.0729%)
- **Validation (20%):** 61,502 rows (default rate 8.0729%)
- **Test (20%):** 61,503 rows (default rate 8.0728%)
- **Test SK_ID_CURR set:** asserted equal to `backend/data/processed/test_predictions.parquet`
- **Stratification:** `TARGET`, `random_state=42`, same `train_test_split` path as v1

## 3. XGBoost hyperparameters (copied from v1)
| Parameter | Value |
| :--- | :--- |
| `tree_method` | hist |
| `learning_rate` | 0.03 |
| `max_depth` | 4 |
| `min_child_weight` | 50 |
| `subsample` | 0.8 |
| `colsample_bytree` | 0.8 |
| `reg_lambda` | 5 |
| `n_estimators` | 3000 |
| `eval_metric` | auc |
| `early_stopping_rounds` | 100 |
| `random_state` | 42 |
| `n_jobs` | -1 |
| best_iteration (this run) | 1247 |

## 4. Cross-validation (train split only)
- **5-fold stratified CV AUC:** **0.70944** (std **0.00252**)
- Fold 1: 0.70557
- Fold 2: 0.71156
- Fold 3: 0.70732
- Fold 4: 0.71090
- Fold 5: 0.71183

## 5. v1 vs v2 on the same test set
v1 numbers are recomputed from `test_predictions.parquet` (calibrated PD). v2 numbers use this run's calibrated PD. Both use the same `SK_ID_CURR` test set.

| Metric | v1 (30 features) | v2 (24 features) | Δ (v2 − v1) |
| :--- | :---: | :---: | :---: |
| **ROC AUC** | 0.72071 | **0.71838** | -0.00233 |
| **PR AUC** | 0.19260 | **0.19365** | +0.00106 |
| **KS** | 0.32659 | **0.32120** | -0.00539 |
| **Brier** | 0.06992 | **0.07001** | +0.00009 |
| **Log loss** | 0.25617 | **0.25672** | +0.00055 |
| **Top-decile lift** | 2.90 | **2.90** | -0.00 |
| **ROC AUC 95% bootstrap CI** (n=1000, seed=42) | 0.72071 [0.71271, 0.72763] | **0.71838 [0.71050, 0.72547]** | — |

### 10-bin calibration table (test set)

**v1**
| Bin | Count | Defaults | Mean predicted PD | Observed default rate | Diff |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 6,151 | 110 | 1.59% | 1.79% | +0.0020 |
| 2 | 6,150 | 172 | 2.82% | 2.80% | -0.0002 |
| 3 | 6,150 | 214 | 4.00% | 3.48% | -0.0052 |
| 4 | 6,150 | 259 | 4.65% | 4.21% | -0.0044 |
| 5 | 6,151 | 349 | 5.03% | 5.67% | +0.0064 |
| 6 | 6,150 | 390 | 6.84% | 6.34% | -0.0049 |
| 7 | 6,150 | 536 | 8.22% | 8.72% | +0.0050 |
| 8 | 6,150 | 638 | 10.84% | 10.37% | -0.0046 |
| 9 | 6,150 | 856 | 13.24% | 13.92% | +0.0067 |
| 10 | 6,151 | 1,441 | 22.89% | 23.43% | +0.0054 |

**v2**
| Bin | Count | Defaults | Mean predicted PD | Observed default rate | Diff |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 6,151 | 107 | 1.77% | 1.74% | -0.0003 |
| 2 | 6,150 | 160 | 3.18% | 2.60% | -0.0058 |
| 3 | 6,150 | 237 | 3.75% | 3.85% | +0.0010 |
| 4 | 6,150 | 278 | 4.64% | 4.52% | -0.0012 |
| 5 | 6,151 | 338 | 5.59% | 5.50% | -0.0010 |
| 6 | 6,150 | 399 | 6.35% | 6.49% | +0.0014 |
| 7 | 6,150 | 514 | 8.28% | 8.36% | +0.0008 |
| 8 | 6,150 | 642 | 10.72% | 10.44% | -0.0028 |
| 9 | 6,150 | 851 | 13.78% | 13.84% | +0.0006 |
| 10 | 6,151 | 1,439 | 22.23% | 23.39% | +0.0116 |

### Default rate by risk band (test set)

Bands are LOW = lowest 40% of validation calibrated PD, MEDIUM = next 40%, HIGH = top 20%. Each model uses its own validation cutoffs.

**v1**
| Band | Applicants | Defaults | Observed default rate | Mean predicted PD |
| :--- | :---: | :---: | :---: | :---: |
| **LOW** | 25,127 | 793 | **3.16%** | 3.30% |
| **MEDIUM** | 25,983 | 2,106 | **8.11%** | 8.15% |
| **HIGH** | 10,393 | 2,066 | **19.88%** | 19.05% |

**v2**
| Band | Applicants | Defaults | Observed default rate | Mean predicted PD |
| :--- | :---: | :---: | :---: | :---: |
| **LOW** | 25,218 | 810 | **3.21%** | 3.38% |
| **MEDIUM** | 24,100 | 1,874 | **7.78%** | 7.82% |
| **HIGH** | 12,185 | 2,281 | **18.72%** | 18.07% |

## 6. v2 predicted-risk deciles (test set)
| Decile | Applicants | Defaults | Default rate | Lift | Mean PD |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 6,151 | 107 | **1.74%** | 0.22x | 1.77% |
| 2 | 6,150 | 160 | **2.60%** | 0.32x | 3.18% |
| 3 | 6,150 | 237 | **3.85%** | 0.48x | 3.75% |
| 4 | 6,150 | 278 | **4.52%** | 0.56x | 4.64% |
| 5 | 6,151 | 338 | **5.50%** | 0.68x | 5.59% |
| 6 | 6,150 | 399 | **6.49%** | 0.80x | 6.35% |
| 7 | 6,150 | 514 | **8.36%** | 1.04x | 8.28% |
| 8 | 6,150 | 642 | **10.44%** | 1.29x | 10.72% |
| 9 | 6,150 | 851 | **13.84%** | 1.71x | 13.78% |
| 10 | 6,151 | 1,439 | **23.39%** | 2.90x | 22.23% |

## 7. Thin-file segments (v2 test AUC)
Flags joined from `features_train.parquet` onto the shared test `SK_ID_CURR` set.

| Segment | n | Defaults | Default rate | v2 ROC AUC |
| :--- | :---: | :---: | :---: | :---: |
| `has_bureau_history == 0` | 8,776 | 890 | 10.14% | **0.72845** |
| `has_installment_history == 0` | 3,182 | 190 | 5.97% | **0.69127** |

## 8. Risk score and policy bands (v2)
- **Score:** `risk_score_0_100 = 100 − population_percentile(calibrated_PD)` using the validation quantile table.
- **LOW:** calibrated PD ≤ 0.050483 (lowest 40% of validation PD)
- **MEDIUM:** 0.050483 < PD ≤ 0.114407 (next 40%)
- **HIGH:** PD > 0.114407 (top 20%)

## 9. Feature importance (v2, top 15 by gain)
| Rank | Feature | Gain |
| :---: | :--- | :---: |
| 1 | `prev_refused_share` | 21.26 |
| 2 | `bureau_n_active` | 17.89 |
| 3 | `credit_term_months` | 17.67 |
| 4 | `years_employed` | 17.36 |
| 5 | `recent_late_share` | 15.98 |
| 6 | `bureau_max_days_overdue` | 15.63 |
| 7 | `late_share` | 12.80 |
| 8 | `days_since_phone_change` | 12.56 |
| 9 | `n_prev_loans` | 10.19 |
| 10 | `bureau_n_credits` | 9.73 |
| 11 | `mean_days_late` | 9.27 |
| 12 | `missing_payment_share` | 7.51 |
| 13 | `years_since_id_published` | 7.08 |
| 14 | `max_days_late` | 6.75 |
| 15 | `days_employed_anomaly` | 6.29 |

## 10. SHAP additivity and calibration reload
- **SHAP sample:** 1000 test rows, tolerance `0.001`
- **Maximum SHAP additivity error:** `6.67572021e-06`
- **Numpy isotonic vs sklearn `IsotonicRegression.predict` on the test set:** max absolute difference `5.96046448e-08`

## 11. Environment
- `python`: 3.14.8
- `xgboost`: 3.4.1
- `shap`: 0.52.0
- `sklearn`: 1.9.1
- `pandas`: 3.0.6
- `numpy`: 2.5.3
- `scipy`: 1.18.1
