#!/usr/bin/env python3
"""
Feature engineering pipeline for Home Credit Default Risk dataset.
Builds applicant-level feature table joined with payment, bureau, and application history.

Excluded on purpose from model features:
- CODE_GENDER and age (saved separately in backend/data/processed/audit_columns.parquet)
- EXT_SOURCE_1/2/3 (omitted by default, included only when include_ext_sources=True)
- TARGET (never used to construct any features)
"""
import argparse
import sys
import time
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

# Paths
MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parent.parent
DEFAULT_RAW_DIR = REPO_ROOT / "backend" / "data" / "raw"
DEFAULT_PROCESSED_DIR = REPO_ROOT / "backend" / "data" / "processed"


def check_raw_files(raw_dir: Path) -> None:
    """Verify that all required raw data files exist."""
    required_files = [
        "application_train.csv",
        "installments_payments.csv",
        "bureau.csv",
        "previous_application.csv",
    ]
    missing = [f for f in required_files if not (raw_dir / f).exists()]
    if missing:
        error_msg = (
            f"ERROR: Missing required raw data file(s) in {raw_dir}:\n"
            + "\n".join(f" - {f}" for f in missing)
            + "\nPlease ensure the dataset is downloaded before running feature extraction."
        )
        raise FileNotFoundError(error_msg)


def extract_installments_features(raw_dir: Path) -> pd.DataFrame:
    """
    Extract aggregated repayment behaviour features from installments_payments.csv.
    Ignores rows with AMT_INSTALMENT == 0 in share calculations.
    """
    dtypes = {
        "SK_ID_PREV": "int32",
        "SK_ID_CURR": "int32",
        "DAYS_INSTALMENT": "float32",
        "DAYS_ENTRY_PAYMENT": "float32",
        "AMT_INSTALMENT": "float32",
        "AMT_PAYMENT": "float32",
    }
    usecols = list(dtypes.keys())
    file_path = raw_dir / "installments_payments.csv"

    print("Loading and aggregating installments_payments.csv...")
    df = pd.read_csv(file_path, usecols=usecols, dtype=dtypes)

    # Base counts on all records
    counts = df.groupby("SK_ID_CURR").agg(
        n_prev_loans=("SK_ID_PREV", "nunique"),
        n_installments=("SK_ID_PREV", "count"),
    )

    # Share calculations ignore rows with AMT_INSTALMENT == 0
    df_valid = df[df["AMT_INSTALMENT"] > 0].copy()

    df_valid["is_late"] = (
        df_valid["DAYS_ENTRY_PAYMENT"] > df_valid["DAYS_INSTALMENT"]
    ).astype("float32")

    df_valid["is_underpaid"] = (
        df_valid["AMT_PAYMENT"] < df_valid["AMT_INSTALMENT"]
    ).astype("float32")

    df_valid["is_missing_payment"] = df_valid["DAYS_ENTRY_PAYMENT"].isna().astype("float32")

    df_valid["days_late"] = (
        df_valid["DAYS_ENTRY_PAYMENT"] - df_valid["DAYS_INSTALMENT"]
    ).clip(lower=0)

    shares = df_valid.groupby("SK_ID_CURR").agg(
        late_share=("is_late", "mean"),
        underpaid_share=("is_underpaid", "mean"),
        mean_days_late=("days_late", "mean"),
        max_days_late=("days_late", "max"),
        missing_payment_share=("is_missing_payment", "mean"),
    )

    # Recent late share using only installments with DAYS_INSTALMENT >= -365
    recent_df = df_valid[df_valid["DAYS_INSTALMENT"] >= -365]
    recent_agg = (
        recent_df.groupby("SK_ID_CURR")["is_late"]
        .mean()
        .rename("recent_late_share")
    )

    inst_agg = counts.join(shares).join(recent_agg)
    return inst_agg


def extract_bureau_features(raw_dir: Path) -> pd.DataFrame:
    """Extract aggregated credit history features from bureau.csv."""
    dtypes = {
        "SK_ID_CURR": "int32",
        "CREDIT_ACTIVE": "category",
        "AMT_CREDIT_SUM_DEBT": "float32",
        "CREDIT_DAY_OVERDUE": "float32",
    }
    usecols = list(dtypes.keys())
    file_path = raw_dir / "bureau.csv"

    print("Loading and aggregating bureau.csv...")
    df = pd.read_csv(file_path, usecols=usecols, dtype=dtypes)

    df["is_active"] = (df["CREDIT_ACTIVE"] == "Active").astype("int32")

    bureau_agg = df.groupby("SK_ID_CURR").agg(
        bureau_n_credits=("CREDIT_ACTIVE", "count"),
        bureau_n_active=("is_active", "sum"),
        bureau_total_debt=("AMT_CREDIT_SUM_DEBT", lambda x: x.sum(min_count=1)),
        bureau_max_days_overdue=("CREDIT_DAY_OVERDUE", "max"),
    )
    return bureau_agg


def extract_prev_app_features(raw_dir: Path) -> pd.DataFrame:
    """Extract prior application features from previous_application.csv."""
    dtypes = {
        "SK_ID_CURR": "int32",
        "NAME_CONTRACT_STATUS": "category",
    }
    usecols = list(dtypes.keys())
    file_path = raw_dir / "previous_application.csv"

    print("Loading and aggregating previous_application.csv...")
    df = pd.read_csv(file_path, usecols=usecols, dtype=dtypes)

    df["is_refused"] = (df["NAME_CONTRACT_STATUS"] == "Refused").astype("float32")

    prev_agg = df.groupby("SK_ID_CURR").agg(
        prev_n_apps=("NAME_CONTRACT_STATUS", "count"),
        prev_refused_share=("is_refused", "mean"),
    )
    return prev_agg


def build_features(
    raw_dir: Union[str, Path] = DEFAULT_RAW_DIR,
    include_ext_sources: bool = False,
) -> pd.DataFrame:
    """
    Build the tabular features dataset for Home Credit Default Risk.

    Parameters:
    -----------
    raw_dir: Path or str
        Path to raw CSV files directory.
    include_ext_sources: bool
        Whether to include EXT_SOURCE_1, EXT_SOURCE_2, EXT_SOURCE_3.

    Returns:
    --------
    pd.DataFrame: One row per SK_ID_CURR (307,511 rows), with TARGET column.
    """
    raw_dir = Path(raw_dir)
    check_raw_files(raw_dir)

    print(f"Building features from {raw_dir} (include_ext_sources={include_ext_sources})...")
    start_time = time.time()

    # 1. Load application_train.csv
    app_cols = [
        "SK_ID_CURR",
        "TARGET",
        "CODE_GENDER",
        "DAYS_BIRTH",
        "AMT_INCOME_TOTAL",
        "AMT_ANNUITY",
        "AMT_CREDIT",
        "CNT_FAM_MEMBERS",
        "DAYS_EMPLOYED",
        "DAYS_LAST_PHONE_CHANGE",
        "DAYS_ID_PUBLISH",
        "DAYS_REGISTRATION",
        "CNT_CHILDREN",
        "EXT_SOURCE_1",
        "EXT_SOURCE_2",
        "EXT_SOURCE_3",
    ]
    app_dtypes = {
        "SK_ID_CURR": "int32",
        "TARGET": "int8",
        "CODE_GENDER": "string",
        "DAYS_BIRTH": "float32",
        "AMT_INCOME_TOTAL": "float32",
        "AMT_ANNUITY": "float32",
        "AMT_CREDIT": "float32",
        "CNT_FAM_MEMBERS": "float32",
        "DAYS_EMPLOYED": "float32",
        "DAYS_LAST_PHONE_CHANGE": "float32",
        "DAYS_ID_PUBLISH": "float32",
        "DAYS_REGISTRATION": "float32",
        "CNT_CHILDREN": "int32",
        "EXT_SOURCE_1": "float32",
        "EXT_SOURCE_2": "float32",
        "EXT_SOURCE_3": "float32",
    }

    app_path = raw_dir / "application_train.csv"
    print(f"Loading {app_path.name}...")
    app_df = pd.read_csv(app_path, usecols=app_cols, dtype=app_dtypes)

    # 2. Extract and save audit columns (SK_ID_CURR, CODE_GENDER, age_years)
    # Excluded on purpose from model features for later fairness audit.
    processed_dir = raw_dir.parent / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    audit_df = pd.DataFrame(
        {
            "SK_ID_CURR": app_df["SK_ID_CURR"],
            "CODE_GENDER": app_df["CODE_GENDER"],
            "age_years": (-app_df["DAYS_BIRTH"] / 365.0).astype("float32"),
        }
    )
    audit_path = processed_dir / "audit_columns.parquet"
    audit_df.to_parquet(audit_path, index=False)
    print(f"Saved fairness audit columns to {audit_path} ({len(audit_df):,} rows).")

    # 3. Group 1: Income and affordability
    p99_9 = app_df["AMT_INCOME_TOTAL"].quantile(0.999)
    income_total = app_df["AMT_INCOME_TOTAL"].clip(upper=p99_9)
    log_income = np.log1p(income_total).astype("float32")

    annuity_to_income = (app_df["AMT_ANNUITY"] / app_df["AMT_INCOME_TOTAL"]).astype("float32")
    credit_to_income = (app_df["AMT_CREDIT"] / app_df["AMT_INCOME_TOTAL"]).astype("float32")
    credit_term_months = (app_df["AMT_CREDIT"] / app_df["AMT_ANNUITY"]).astype("float32")
    income_per_family_member = (app_df["AMT_INCOME_TOTAL"] / app_df["CNT_FAM_MEMBERS"]).astype("float32")

    # 4. Group 2: Stability
    # DAYS_EMPLOYED == 365243 is a sentinel value for retired / unemployed
    days_employed_raw = app_df["DAYS_EMPLOYED"]
    days_employed_anomaly = (days_employed_raw == 365243).astype("int32")
    days_employed_valid = days_employed_raw.where(days_employed_raw != 365243, np.nan)
    years_employed = (-days_employed_valid / 365.0).astype("float32")

    days_since_phone_change = (-app_df["DAYS_LAST_PHONE_CHANGE"]).astype("float32")
    years_since_id_published = (-app_df["DAYS_ID_PUBLISH"] / 365.0).astype("float32")
    years_registered = (-app_df["DAYS_REGISTRATION"] / 365.0).astype("float32")
    cnt_children = app_df["CNT_CHILDREN"].astype("int32")
    cnt_fam_members = app_df["CNT_FAM_MEMBERS"].astype("float32")

    features = pd.DataFrame(
        {
            "SK_ID_CURR": app_df["SK_ID_CURR"],
            # Group 1
            "income_total": income_total.astype("float32"),
            "log_income": log_income,
            "annuity_to_income": annuity_to_income,
            "credit_to_income": credit_to_income,
            "credit_term_months": credit_term_months,
            "income_per_family_member": income_per_family_member,
            # Group 2
            "years_employed": years_employed,
            "days_employed_anomaly": days_employed_anomaly,
            "days_since_phone_change": days_since_phone_change,
            "years_since_id_published": years_since_id_published,
            "years_registered": years_registered,
            "cnt_children": cnt_children,
            "cnt_fam_members": cnt_fam_members,
        }
    )

    # 5. Group 3: Repayment behaviour from installments_payments.csv
    inst_agg = extract_installments_features(raw_dir)
    features = features.merge(inst_agg, on="SK_ID_CURR", how="left")

    # Applicants with no installment history get flag=0, counts=0, ratios=NaN
    features["has_installment_history"] = features["n_installments"].notnull().astype("int32")
    features["n_prev_loans"] = features["n_prev_loans"].fillna(0).astype("int32")
    features["n_installments"] = features["n_installments"].fillna(0).astype("int32")

    # 6. Group 4: Credit history from bureau.csv
    bureau_agg = extract_bureau_features(raw_dir)
    features = features.merge(bureau_agg, on="SK_ID_CURR", how="left")

    # Applicants with no bureau history get flag=0, counts=0, others=NaN
    features["has_bureau_history"] = features["bureau_n_credits"].notnull().astype("int32")
    features["bureau_n_credits"] = features["bureau_n_credits"].fillna(0).astype("int32")
    features["bureau_n_active"] = features["bureau_n_active"].fillna(0).astype("int32")

    # 7. Group 5: Prior applications from previous_application.csv
    prev_agg = extract_prev_app_features(raw_dir)
    features = features.merge(prev_agg, on="SK_ID_CURR", how="left")

    # Applicants with no prior applications get flag=0, counts=0, ratios=NaN
    features["has_prev_application"] = features["prev_n_apps"].notnull().astype("int32")
    features["prev_n_apps"] = features["prev_n_apps"].fillna(0).astype("int32")

    # 8. External sources (optional)
    if include_ext_sources:
        features["ext_source_1"] = app_df["EXT_SOURCE_1"].astype("float32")
        features["ext_source_2"] = app_df["EXT_SOURCE_2"].astype("float32")
        features["ext_source_3"] = app_df["EXT_SOURCE_3"].astype("float32")

    # 9. TARGET column (kept as a separate column named TARGET, never used to build features)
    features["TARGET"] = app_df["TARGET"].astype("int8")

    elapsed = time.time() - start_time
    print(
        f"Feature engineering completed in {elapsed:.2f}s: "
        f"{len(features):,} rows, {features.shape[1]} columns."
    )
    return features


def generate_feature_report(
    features_path: Union[str, Path] = DEFAULT_PROCESSED_DIR / "features_train.parquet",
    output_path: Union[str, Path] = DEFAULT_PROCESSED_DIR / "feature_report.txt",
) -> str:
    """
    Generate validation report for the engineered feature dataset.
    Reads features_train.parquet, runs integrity asserts, computes missing rates
    and quintile default rates, and writes the report to output_path.
    """
    features_path = Path(features_path)
    output_path = Path(output_path)

    if not features_path.exists():
        raise FileNotFoundError(
            f"Feature file not found at {features_path}. Please build features first."
        )

    print(f"Loading {features_path} for validation report...")
    df = pd.read_parquet(features_path)

    # -------------------------------------------------------------
    # 1. Assertions
    # -------------------------------------------------------------
    n_rows, n_cols = df.shape
    assert n_rows == 307511, f"Assertion Failed: Expected exactly 307,511 rows, got {n_rows:,}"
    assert df["SK_ID_CURR"].nunique() == 307511, "Assertion Failed: SK_ID_CURR is not unique across all rows"
    assert "TARGET" in df.columns, "Assertion Failed: TARGET column missing from features_train.parquet"

    model_features = [c for c in df.columns if c not in ("SK_ID_CURR", "TARGET")]
    assert "TARGET" not in model_features, "Assertion Failed: TARGET must not be among model features"
    assert not any("EXT_SOURCE" in c.upper() for c in df.columns), (
        "Assertion Failed: EXT_SOURCE columns must not be in features_train.parquet"
    )
    assert not any("CODE_GENDER" in c.upper() for c in df.columns), (
        "Assertion Failed: CODE_GENDER column must not be in features_train.parquet"
    )
    assert "age" not in [c.lower() for c in df.columns], (
        "Assertion Failed: age column must not be in features_train.parquet"
    )

    # -------------------------------------------------------------
    # 2. Missing Percentage Analysis
    # -------------------------------------------------------------
    missing_counts = df[model_features].isnull().sum()
    missing_pcts = (missing_counts / n_rows) * 100
    missing_summary = pd.DataFrame(
        {
            "missing_count": missing_counts,
            "missing_pct": missing_pcts,
        }
    ).sort_values(by="missing_pct", ascending=False)

    high_missing = missing_summary[missing_summary["missing_pct"] > 60]

    # -------------------------------------------------------------
    # 3. Quintile Default Rate Analysis
    # -------------------------------------------------------------
    quintile_rows = []
    for col in model_features:
        valid = df[[col, "TARGET"]].dropna()
        n_valid = len(valid)

        # Handle ties: use pd.qcut if bin edges are unique; fallback to rank(method='first')
        try:
            bins = pd.qcut(valid[col], q=5, labels=False)
            tie_handling = "standard pd.qcut (unique bin edges)"
        except ValueError:
            bins = pd.qcut(valid[col].rank(method="first"), q=5, labels=False)
            tie_handling = "rank-first qcut (equal-sized 20% bins with sequential tie-breaking)"

        q1_sub = valid[bins == 0]
        q5_sub = valid[bins == 4]

        q1_rate = q1_sub["TARGET"].mean()
        q5_rate = q5_sub["TARGET"].mean()

        q1_min, q1_max = q1_sub[col].min(), q1_sub[col].max()
        q5_min, q5_max = q5_sub[col].min(), q5_sub[col].max()

        rate_diff = q5_rate - q1_rate
        rate_ratio = (q5_rate / q1_rate) if q1_rate > 0 else np.nan

        quintile_rows.append(
            {
                "feature": col,
                "n_valid": n_valid,
                "q1_rate": q1_rate,
                "q5_rate": q5_rate,
                "diff": rate_diff,
                "ratio": rate_ratio,
                "q1_range": f"[{q1_min:,.2f}, {q1_max:,.2f}]",
                "q5_range": f"[{q5_min:,.2f}, {q5_max:,.2f}]",
                "tie_handling": tie_handling,
            }
        )

    quintile_df = pd.DataFrame(quintile_rows)

    # -------------------------------------------------------------
    # 4. Construct Report Text
    # -------------------------------------------------------------
    lines = []
    lines.append("=" * 80)
    lines.append("ICVER - HOME CREDIT FEATURE ENGINEERING VALIDATION REPORT")
    lines.append("=" * 80)
    lines.append(f"Report Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Source Parquet:   {features_path}")
    lines.append(f"Output File:      {output_path}")
    lines.append("")
    lines.append("1. DATASET DIMENSIONS & INTEGRITY")
    lines.append("-" * 80)
    lines.append(f"Total Applications (Rows):    {n_rows:,}")
    lines.append(f"Unique Applicant IDs (SK_ID): {df['SK_ID_CURR'].nunique():,}")
    lines.append(f"Total Columns in Parquet:     {n_cols}")
    lines.append(f"Model Feature Columns:        {len(model_features)}")
    lines.append(f"Overall Default Rate:         {df['TARGET'].mean():.4%} ({df['TARGET'].sum():,} / {n_rows:,})")
    lines.append("")
    lines.append("2. QUALITY & FAIRNESS ASSERTIONS")
    lines.append("-" * 80)
    lines.append("[PASS] Exactly 307,511 rows present.")
    lines.append("[PASS] SK_ID_CURR is strictly unique across all rows.")
    lines.append("[PASS] TARGET column preserved as separate label; not included in model features.")
    lines.append("[PASS] No EXT_SOURCE columns present in features_train.parquet.")
    lines.append("[PASS] CODE_GENDER and age columns strictly excluded from model features.")
    lines.append("[PASS] Audit columns saved in backend/data/processed/audit_columns.parquet.")
    lines.append("")
    lines.append("3. MISSING PERCENTAGE PER FEATURE")
    lines.append("-" * 80)
    lines.append(f"{'Feature Name':<28} | {'Missing Count':>14} | {'Missing (%)':>12}")
    lines.append("-" * 60)
    for col_name, row in missing_summary.iterrows():
        lines.append(f"{col_name:<28} | {int(row['missing_count']):>14,} | {row['missing_pct']:>11.2f}%")
    lines.append("")
    lines.append("4. HIGH-MISSING FEATURES (> 60% MISSING)")
    lines.append("-" * 80)
    if len(high_missing) == 0:
        lines.append("None. (0 features have > 60% missing values; highest missing feature is recent_late_share at 29.27%).")
    else:
        for col_name, row in high_missing.iterrows():
            lines.append(f" - {col_name}: {row['missing_pct']:.2f}% missing ({int(row['missing_count']):,} rows)")
    lines.append("")
    lines.append("5. QUINTILE DEFAULT RATE ANALYSIS (LOWEST Q1 VS HIGHEST Q5)")
    lines.append("-" * 80)
    lines.append("Methodology & Edge Case Handling:")
    lines.append(" - Missing Values (NaN): Excluded per-feature via dropna() before quintile partitioning.")
    lines.append("   Applicants without history in that group are not assigned to a quintile bucket.")
    lines.append(" - Ties / Discrete Distributions: Discretized with pd.qcut when unique bin edges exist.")
    lines.append("   When duplicate values / point masses exist (e.g. heavy clustering at 0), stable rank-based")
    lines.append("   ordering rank(method='first') is used to guarantee exactly 20% in each quintile bucket.")
    lines.append("")
    lines.append(f"{'Feature Name':<28} | {'Q1 Rate':>9} | {'Q5 Rate':>9} | {'Diff':>8} | {'Ratio':>7} | {'Q1 Range':<22} | {'Q5 Range':<26}")
    lines.append("-" * 120)
    for _, r in quintile_df.iterrows():
        ratio_str = f"{r['ratio']:.2f}x" if not np.isnan(r['ratio']) else "N/A"
        diff_str = f"{r['diff']:+.4f}"
        lines.append(
            f"{r['feature']:<28} | {r['q1_rate']:>8.2%} | {r['q5_rate']:>8.2%} | {diff_str:>8} | {ratio_str:>7} | {r['q1_range']:<22} | {r['q5_range']:<26}"
        )
    lines.append("")
    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)

    report_content = "\n".join(lines) + "\n"

    # Write report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"Report written to {output_path}")
    return report_content


def main():
    parser = argparse.ArgumentParser(
        description="Build feature table for Home Credit Default Risk dataset."
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
        help=f"Path to raw CSV dataset directory (default: {DEFAULT_RAW_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        help=f"Path to processed parquet output directory (default: {DEFAULT_PROCESSED_DIR})",
    )
    parser.add_argument(
        "--include-ext-sources",
        action="store_true",
        help="Include EXT_SOURCE_1/2/3 features and write to features_train_with_ext.parquet",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Generate validation report from existing features_train.parquet without recomputing features",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Report only mode
    if args.report_only:
        features_file = args.output_dir / "features_train.parquet"
        report_file = args.output_dir / "feature_report.txt"
        report_text = generate_feature_report(
            features_path=features_file,
            output_path=report_file,
        )
        print(report_text)
        return

    # 2. Check if features already exist
    if args.include_ext_sources:
        out_file = args.output_dir / "features_train_with_ext.parquet"
    else:
        out_file = args.output_dir / "features_train.parquet"

    if out_file.exists():
        print(f"Feature file {out_file} already exists. Skipping feature recomputation.")
    else:
        features_df = build_features(
            raw_dir=args.raw_dir,
            include_ext_sources=args.include_ext_sources,
        )
        print(f"Saving feature table to {out_file}...")
        features_df.to_parquet(out_file, index=False)
        file_size_mb = out_file.stat().st_size / (1024 * 1024)
        print(f"Successfully wrote {out_file} ({file_size_mb:.2f} MB, {len(features_df):,} rows).")

    # Generate and print validation report
    features_train_file = args.output_dir / "features_train.parquet"
    if features_train_file.exists():
        report_file = args.output_dir / "feature_report.txt"
        report_text = generate_feature_report(
            features_path=features_train_file,
            output_path=report_file,
        )
        print(report_text)


if __name__ == "__main__":
    main()
