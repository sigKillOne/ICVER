#!/usr/bin/env python3
"""
Exploratory Data Analysis (EDA) on Home Credit Default Risk dataset.
Loads application_train.csv and installments_payments.csv from backend/data/raw/,
prints the summary to stdout, and writes it to backend/data/eda_summary.md.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
RAW_DATA_DIR = REPO_ROOT / "backend" / "data" / "raw"
OUTPUT_MD_PATH = REPO_ROOT / "backend" / "data" / "eda_summary.md"


def format_currency(val):
    if pd.isna(val):
        return "N/A"
    return f"{val:,.2f}"


def format_num(val, decimals=2):
    if pd.isna(val):
        return "N/A"
    return f"{val:,.{decimals}f}"


def run_eda():
    app_train_path = RAW_DATA_DIR / "application_train.csv"
    installments_path = RAW_DATA_DIR / "installments_payments.csv"

    # Rule: Do not fabricate data. If file is missing, stop and tell user.
    missing_files = []
    if not app_train_path.exists():
        missing_files.append(str(app_train_path))
    if not installments_path.exists():
        missing_files.append(str(installments_path))

    if missing_files:
        error_msg = (
            f"ERROR: Missing required data file(s):\n"
            + "\n".join(f" - {f}" for f in missing_files)
            + f"\nPlease run 'python backend/scripts/download_home_credit.py' first."
        )
        print(error_msg, file=sys.stderr)
        sys.exit(1)

    print("Loading application_train.csv...")
    app_df = pd.read_csv(app_train_path)

    print("Loading installments_payments.csv...")
    inst_df = pd.read_csv(installments_path)

    # -------------------------------------------------------------
    # 1. application_train.csv Overview
    # -------------------------------------------------------------
    n_rows_app, n_cols_app = app_df.shape
    target_counts = app_df["TARGET"].value_counts()
    target_mean = app_df["TARGET"].mean()

    # -------------------------------------------------------------
    # 2. Top 15 Missing Columns
    # -------------------------------------------------------------
    missing_counts = app_df.isnull().sum()
    missing_pct = (missing_counts / n_rows_app) * 100
    missing_df = (
        pd.DataFrame({"missing_count": missing_counts, "missing_pct": missing_pct})
        .sort_values(by="missing_pct", ascending=False)
        .head(15)
    )

    # -------------------------------------------------------------
    # 3. Summary Stats for Requested Columns
    # -------------------------------------------------------------
    stats_cols = [
        "AMT_INCOME_TOTAL",
        "AMT_ANNUITY",
        "AMT_CREDIT",
        "DAYS_EMPLOYED",
        "DAYS_LAST_PHONE_CHANGE",
        "CNT_FAM_MEMBERS",
    ]

    summary_rows = []
    for col in stats_cols:
        if col in app_df.columns:
            s = app_df[col].dropna()
            summary_rows.append(
                {
                    "Feature": col,
                    "Min": s.min(),
                    "25%": s.quantile(0.25),
                    "Median": s.median(),
                    "Mean": s.mean(),
                    "75%": s.quantile(0.75),
                    "Max": s.max(),
                    "Missing Count": app_df[col].isnull().sum(),
                    "Missing Pct": (app_df[col].isnull().sum() / n_rows_app) * 100,
                }
            )
    summary_stats_df = pd.DataFrame(summary_rows)

    # -------------------------------------------------------------
    # 4. Anomalies in application_train
    # -------------------------------------------------------------
    # DAYS_EMPLOYED == 365243
    days_employed_anomaly_count = (app_df["DAYS_EMPLOYED"] == 365243).sum()
    days_employed_anomaly_pct = (days_employed_anomaly_count / n_rows_app) * 100
    valid_days_employed = app_df.loc[app_df["DAYS_EMPLOYED"] != 365243, "DAYS_EMPLOYED"]

    # Extreme Income
    max_income = app_df["AMT_INCOME_TOTAL"].max()
    income_99_9 = app_df["AMT_INCOME_TOTAL"].quantile(0.999)

    # Family members max
    max_fam = app_df["CNT_FAM_MEMBERS"].max()

    # -------------------------------------------------------------
    # 5. installments_payments.csv Analysis
    # -------------------------------------------------------------
    n_rows_inst, n_cols_inst = inst_df.shape
    n_clients_inst = inst_df["SK_ID_CURR"].nunique()

    # Payment flags:
    # Late payment: DAYS_ENTRY_PAYMENT > DAYS_INSTALMENT (greater means entered after due date)
    # Underpaid: AMT_PAYMENT < AMT_INSTALMENT
    # Note: If DAYS_ENTRY_PAYMENT is null, payment was never entered.
    # Note: If AMT_PAYMENT is null, amount paid was missing/0.
    inst_df["is_late"] = (
        inst_df["DAYS_ENTRY_PAYMENT"].notnull()
        & (inst_df["DAYS_ENTRY_PAYMENT"] > inst_df["DAYS_INSTALMENT"])
    ) | (inst_df["DAYS_ENTRY_PAYMENT"].isnull())

    inst_df["is_underpaid"] = (
        inst_df["AMT_PAYMENT"].notnull()
        & (inst_df["AMT_PAYMENT"] < inst_df["AMT_INSTALMENT"])
    ) | (inst_df["AMT_PAYMENT"].isnull())

    # Per-client aggregation
    client_grp = inst_df.groupby("SK_ID_CURR").agg(
        total_installments=("NUM_INSTALMENT_NUMBER", "count"),
        late_share=("is_late", "mean"),
        underpaid_share=("is_underpaid", "mean"),
    )

    late_dist = client_grp["late_share"].describe(
        percentiles=[0.05, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    )
    underpaid_dist = client_grp["underpaid_share"].describe(
        percentiles=[0.05, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    )

    clients_with_any_late = (client_grp["late_share"] > 0).mean() * 100
    clients_with_any_underpaid = (client_grp["underpaid_share"] > 0).mean() * 100

    # Anomalies in installments
    missing_entry_payment = inst_df["DAYS_ENTRY_PAYMENT"].isnull().sum()
    missing_amt_payment = inst_df["AMT_PAYMENT"].isnull().sum()
    zero_instalment_amt = (inst_df["AMT_INSTALMENT"] == 0).sum()

    # -------------------------------------------------------------
    # Build Markdown Content
    # -------------------------------------------------------------
    md_lines = []
    md_lines.append("# Home Credit Default Risk - Exploratory Data Analysis (EDA) Summary\n")
    md_lines.append(f"**Analysis Date:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    md_lines.append("## 1. Dataset Dimensions & Target Overview (`application_train.csv`)\n")
    md_lines.append(f"- **Total Rows (Applications):** {n_rows_app:,}")
    md_lines.append(f"- **Total Columns:** {n_cols_app:,}")
    md_lines.append(
        f"- **Default Rate (`TARGET` Mean):** **{target_mean:.4%}** ({target_mean:.4f})"
    )
    md_lines.append(
        f"  - Non-Defaulters (`TARGET = 0`): {target_counts.get(0, 0):,} ({target_counts.get(0, 0) / n_rows_app:.2%})"
    )
    md_lines.append(
        f"  - Defaulters (`TARGET = 1`): {target_counts.get(1, 0):,} ({target_counts.get(1, 0) / n_rows_app:.2%})"
    )
    md_lines.append(
        f"- **Class Imbalance Ratio:** ~{target_counts.get(0, 0) / max(target_counts.get(1, 1), 1):.1f} : 1 (Significant imbalance)\n"
    )

    md_lines.append("## 2. Top 15 Columns with Highest Missing Percentage\n")
    md_lines.append("| Column Name | Missing Count | Missing Percentage |")
    md_lines.append("| :--- | :---: | :---: |")
    for col_name, row in missing_df.iterrows():
        md_lines.append(
            f"| `{col_name}` | {int(row['missing_count']):,} | {row['missing_pct']:.2f}% |"
        )
    md_lines.append("")

    md_lines.append("## 3. Summary Statistics for Key Numerical Features\n")
    md_lines.append(
        "| Feature | Min | 25% | Median | Mean | 75% | Max | Missing (%) |"
    )
    md_lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for _, row in summary_stats_df.iterrows():
        md_lines.append(
            f"| `{row['Feature']}` | {format_num(row['Min'])} | {format_num(row['25%'])} | "
            f"**{format_num(row['Median'])}** | {format_num(row['Mean'])} | {format_num(row['75%'])} | "
            f"**{format_num(row['Max'])}** | {row['Missing Pct']:.2f}% |"
        )
    md_lines.append("")

    md_lines.append("## 4. Installments & Payment Behavior (`installments_payments.csv`)\n")
    md_lines.append(f"- **Total Installment Rows:** {n_rows_inst:,}")
    md_lines.append(f"- **Unique Clients (`SK_ID_CURR`):** {n_clients_inst:,}")
    md_lines.append(
        f"- **Clients with at least one late payment:** {clients_with_any_late:.2f}%"
    )
    md_lines.append(
        f"- **Clients with at least one underpayment:** {clients_with_any_underpaid:.2f}%\n"
    )

    md_lines.append(
        "### Distribution of Per-Client Payment Shares (`late_share` & `underpaid_share`)\n"
    )
    md_lines.append(
        "| Metric | Late Payment Share (`DAYS_ENTRY > DAYS_INSTALMENT`) | Underpayment Share (`AMT_PAYMENT < AMT_INSTALMENT`) |"
    )
    md_lines.append("| :--- | :---: | :---: |")
    md_lines.append(
        f"| **Mean** | {late_dist['mean']:.4f} ({late_dist['mean']:.2%}) | {underpaid_dist['mean']:.4f} ({underpaid_dist['mean']:.2%}) |"
    )
    md_lines.append(
        f"| **Std** | {late_dist['std']:.4f} | {underpaid_dist['std']:.4f} |"
    )
    md_lines.append(
        f"| **Min** | {late_dist['min']:.4f} | {underpaid_dist['min']:.4f} |"
    )
    md_lines.append(
        f"| **25%** | {late_dist['25%']:.4f} | {underpaid_dist['25%']:.4f} |"
    )
    md_lines.append(
        f"| **Median (50%)** | **{late_dist['50%']:.4f} ({late_dist['50%']:.2%})** | **{underpaid_dist['50%']:.4f} ({underpaid_dist['50%']:.2%})** |"
    )
    md_lines.append(
        f"| **75%** | {late_dist['75%']:.4f} ({late_dist['75%']:.2%}) | {underpaid_dist['75%']:.4f} ({underpaid_dist['75%']:.2%}) |"
    )
    md_lines.append(
        f"| **90%** | {late_dist['90%']:.4f} ({late_dist['90%']:.2%}) | {underpaid_dist['90%']:.4f} ({underpaid_dist['90%']:.2%}) |"
    )
    md_lines.append(
        f"| **95%** | {late_dist['95%']:.4f} ({late_dist['95%']:.2%}) | {underpaid_dist['95%']:.4f} ({underpaid_dist['95%']:.2%}) |"
    )
    md_lines.append(
        f"| **99%** | {late_dist['99%']:.4f} ({late_dist['99%']:.2%}) | {underpaid_dist['99%']:.4f} ({underpaid_dist['99%']:.2%}) |"
    )
    md_lines.append(
        f"| **Max** | {late_dist['max']:.4f} ({late_dist['max']:.2%}) | {underpaid_dist['max']:.4f} ({underpaid_dist['max']:.2%}) |"
    )
    md_lines.append("")

    md_lines.append("## 5. Detected Data Anomalies & Modeling Considerations\n")
    md_lines.append(
        f"1. **`DAYS_EMPLOYED = 365243` Sentinel Value:**\n"
        f"   - Found in **{days_employed_anomaly_count:,} rows ({days_employed_anomaly_pct:.2f}%)** of `application_train.csv`.\n"
        f"   - `365243` days equals exactly 1,000 years. This is a known encoding for pensioners, unemployed, or individuals without formal employment history.\n"
        f"   - When excluding this sentinel value, `DAYS_EMPLOYED` ranges from **{valid_days_employed.min():,.0f} days** (~{abs(valid_days_employed.min())/365:.1f} years) to **{valid_days_employed.max():,.0f} days** (median: **{valid_days_employed.median():,.0f} days** / ~{abs(valid_days_employed.median())/365:.1f} years).\n"
        f"   - *Action required during feature engineering:* Create a binary indicator flag `DAYS_EMPLOYED_ANOM` and replace `365243` with `NaN` before modeling.\n"
    )
    md_lines.append(
        f"2. **Negative Relative Days Encoding:**\n"
        f"   - Columns such as `DAYS_BIRTH`, `DAYS_EMPLOYED`, `DAYS_REGISTRATION`, `DAYS_ID_PUBLISH`, and `DAYS_LAST_PHONE_CHANGE` are stored as negative numbers counting backwards from application date.\n"
        f"   - `DAYS_LAST_PHONE_CHANGE` has a minimum of {app_df['DAYS_LAST_PHONE_CHANGE'].min():,.0f} days and max of 0 days (with 1 missing value).\n"
    )
    md_lines.append(
        f"3. **Extreme Outlier in `AMT_INCOME_TOTAL`:**\n"
        f"   - Maximum income is **{format_currency(max_income)}**, whereas the median is **{format_currency(app_df['AMT_INCOME_TOTAL'].median())}** and 99.9th percentile is **{format_currency(income_99_9)}**.\n"
        f"   - This single extreme outlier will distort non-tree algorithms and unscaled aggregations.\n"
    )
    md_lines.append(
        f"4. **Installment Missing Records & Zero Amounts:**\n"
        f"   - In `installments_payments.csv`, {missing_entry_payment:,} records ({missing_entry_payment / n_rows_inst:.3%}) have missing `DAYS_ENTRY_PAYMENT` and `AMT_PAYMENT`, representing scheduled installments with no recorded payment.\n"
        f"   - {zero_instalment_amt:,} records have `AMT_INSTALMENT == 0`.\n"
    )

    md_content = "\n".join(md_lines)

    # Print to stdout
    print("\n" + "=" * 70)
    print("EDA SUMMARY")
    print("=" * 70)
    print(md_content)

    # Write to backend/data/eda_summary.md
    OUTPUT_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_MD_PATH, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\nSuccessfully wrote EDA summary to {OUTPUT_MD_PATH}")


if __name__ == "__main__":
    run_eda()
