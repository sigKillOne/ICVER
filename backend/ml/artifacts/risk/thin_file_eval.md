# ICVER Repayment Risk Model - Thin-File & Credit History Evaluation

**Generated:** 2026-10-22 10:23:08  
**Runtime:** 28.33 seconds  
**Target Dataset:** Home Credit Default Risk (`backend/data/processed/test_predictions.parquet`)

## 1. Credit History Segments Overview & Model Performance
Segments are partitioned using presence flags: `has_installment_history`, `has_bureau_history`, and `has_prev_application`. Bootstrap confidence intervals are computed using 1,000 resamples with random seed 42.

| Segment | Clients | Share | Defaults | Default Rate | ROC AUC (95% CI) | KS Stat | Mean Pred PD | Calib Gap |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `no_history` | 447 | 0.73% | 33 | **7.38%** | **0.72530** `[0.63637, 0.80673]` | 36.43% | 7.69% | +0.31% |
| `some_history` | 61,056 | 99.27% | 4,932 | **8.08%** | **0.72068** `[0.71292, 0.72798]` | 32.68% | 8.01% | -0.06% |
| `no_installment_history` | 3,182 | 5.17% | 190 | **5.97%** | **0.68662** `[0.64918, 0.72249]` | 27.89% | 6.36% | +0.39% |
| `no_bureau_history` | 8,776 | 14.27% | 890 | **10.14%** | **0.72794** `[0.71038, 0.74484]` | 34.10% | 9.99% | -0.15% |
| `no_prev_application` | 3,280 | 5.33% | 189 | **5.76%** | **0.68137** `[0.64677, 0.71659]` | 26.73% | 6.22% | +0.46% |

## 2. Policy Risk Band Distribution by Segment
Distribution of applicants across policy risk bands (`LOW`: bottom 40% risk, `MEDIUM`: middle 40%, `HIGH`: top 20% risk, defined on validation quantiles).

| Segment | Total Clients | LOW Band (%) | MEDIUM Band (%) | HIGH Band (%) |
| :--- | :---: | :---: | :---: | :---: |
| `no_history` | 447 | 37.36% | 47.20% | 15.44% |
| `some_history` | 61,056 | 40.88% | 42.21% | 16.91% |
| `no_installment_history` | 3,182 | 48.99% | 43.40% | 7.61% |
| `no_bureau_history` | 8,776 | 26.62% | 47.52% | 25.87% |
| `no_prev_application` | 3,280 | 50.15% | 42.44% | 7.41% |

## 3. History-Free Model Benchmark Comparison
An in-memory XGBoost model trained strictly on 13 non-history features (application, income, demographic, and employment metrics) with the same hyperparameters and early stopping on the identical 60/20/20 stratified split.

| Population / Cohort | Full Model (30 Features) | History-Free Model (13 Features) | Delta (History-Free - Full) |
| :--- | :---: | :---: | :---: |
| **Full Test Set** (n=61,503) | **0.72071** | 0.68899 | -0.03172 |
| **No-History Segment** (n=447) | **0.72530** | **0.67128** | **-0.05402** |

## 4. Conclusion
1. For no-history applicants, the full model preserves strong discriminatory power (0.72530 AUC with 95% CI [0.636, 0.807] vs 0.72071 overall), and its calibrated PD remains well-aligned with observed default rates (7.69% mean PD vs 7.38% defaults).
2. The history-free benchmark reaches 0.67128 AUC on no-history applicants, falling 0.0540 AUC behind the full model (0.72530), indicating the full model's native tree routing handles unobserved history better than omitting those features.
3. While prior credit history boosts general population discrimination by +3.17% AUC, demographic and stability features provide a sturdy baseline for applicants with thin files.
4. The full model avoids adverse bias against thin-file borrowers: 37.4% are assigned LOW risk, 47.2% MEDIUM, and only 15.4% enter HIGH risk.
5. A single unified model with native NaN handling effectively underwrites thin-file borrowers without requiring a segregated scoring pipeline.
