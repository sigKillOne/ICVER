#!/usr/bin/env python3
"""
Download and extract the Home Credit Default Risk dataset from Kaggle.
"""
import os
import sys
import zipfile
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
RAW_DATA_DIR = REPO_ROOT / "backend" / "data" / "raw"

EXPECTED_CSVS = [
    "application_train.csv",
    "installments_payments.csv",
]


def check_csvs_exist(target_dir: Path) -> bool:
    """Check if the core CSV files already exist in target_dir."""
    return all((target_dir / csv_name).exists() for csv_name in EXPECTED_CSVS)


def extract_zips(target_dir: Path) -> bool:
    """Detect and extract all zip files in target_dir, including nested zips."""
    extracted_any = False
    processed_zips = set()

    while True:
        zip_files = [z for z in target_dir.glob("*.zip") if z not in processed_zips]
        if not zip_files:
            break

        for z in zip_files:
            print(f"Extracting {z.name} into {target_dir}...")
            try:
                with zipfile.ZipFile(z, "r") as zip_ref:
                    zip_ref.extractall(target_dir)
                processed_zips.add(z)
                extracted_any = True
            except Exception as e:
                print(f"Error extracting {z.name}: {e}", file=sys.stderr)
                processed_zips.add(z)

    return extracted_any


def check_kaggle_credentials() -> bool:
    """
    Check that Kaggle credentials exist, accepting ANY of:
      1. KAGGLE_API_TOKEN environment variable (non-empty)
      2. ~/.kaggle/access_token
      3. ~/.kaggle/kaggle.json

    CRITICAL: Never print, log, or write any token value.
    """
    if os.environ.get("KAGGLE_API_TOKEN", "").strip():
        return True

    kaggle_dir = Path.home() / ".kaggle"
    if (kaggle_dir / "access_token").is_file():
        return True
    if (kaggle_dir / "kaggle.json").is_file():
        return True

    return False


def print_kaggle_instructions():
    """Print step-by-step instructions for setting up Kaggle credentials without leaking token values."""
    print("=" * 70)
    print("ERROR: Kaggle credentials not found!")
    print("=" * 70)
    print(
        "\nNo Kaggle credentials detected. You can provide credentials via ANY of:\n"
        "  - The 'KAGGLE_API_TOKEN' environment variable\n"
        "  - The file '~/.kaggle/access_token'\n"
        "  - The file '~/.kaggle/kaggle.json'\n\n"
        "Step-by-step setup instructions:\n"
        "1. Accept competition rules:\n"
        "   Visit: https://www.kaggle.com/competitions/home-credit-default-risk/rules\n"
        "   Log in and click 'I Understand and Accept'.\n\n"
        "2. Create an API token:\n"
        "   Go to your Kaggle account settings: https://www.kaggle.com/settings\n"
        "   Scroll down to the 'API' section.\n"
        "   - Option A: Generate an API token and save it to ~/.kaggle/access_token\n"
        "     or export it in your shell: export KAGGLE_API_TOKEN='<your-token>'\n"
        "   - Option B: Click 'Create New Token' to download kaggle.json and move it to ~/.kaggle/kaggle.json\n\n"
        "3. Secure the credentials:\n"
        "     mkdir -p ~/.kaggle\n"
        "     chmod 600 ~/.kaggle/access_token 2>/dev/null || true\n"
        "     chmod 600 ~/.kaggle/kaggle.json 2>/dev/null || true\n\n"
        "4. Re-run this script:\n"
        "     python backend/scripts/download_home_credit.py\n\n"
        "Alternatively, you can manually download the competition zip archive\n"
        "from Kaggle, place it into 'backend/data/raw/', and re-run this script\n"
        "to automatically detect and unzip it.\n"
    )


def main():
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. If CSVs already exist, skip download and extraction immediately
    if check_csvs_exist(RAW_DATA_DIR):
        print(f"Dataset CSV files already exist in {RAW_DATA_DIR}. Skipping download.")
        return

    # 2. If CSVs do not exist, check if a zip file was manually placed in backend/data/raw/
    print("Checking for existing zip archives in backend/data/raw/...")
    extracted_from_zip = extract_zips(RAW_DATA_DIR)
    if extracted_from_zip and check_csvs_exist(RAW_DATA_DIR):
        print(f"Successfully extracted dataset from local zip archive(s) into {RAW_DATA_DIR}.")
        return

    # 3. Check that Kaggle credentials exist (KAGGLE_API_TOKEN, ~/.kaggle/access_token, or ~/.kaggle/kaggle.json)
    if not check_kaggle_credentials():
        print_kaggle_instructions()
        sys.exit(1)

    # 4. Download using kaggle package
    print("Authenticating with Kaggle API...")
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
    except Exception as e:
        print(f"Failed to authenticate with Kaggle API: {e}", file=sys.stderr)
        print_kaggle_instructions()
        sys.exit(1)

    print("Downloading competition 'home-credit-default-risk' into backend/data/raw/...")
    try:
        api.competition_download_files(
            "home-credit-default-risk",
            path=str(RAW_DATA_DIR),
            quiet=False,
        )
    except Exception as e:
        print(f"Error downloading competition files: {e}", file=sys.stderr)
        print(
            "\nPlease verify that your Kaggle account has accepted the competition rules:\n"
            "https://www.kaggle.com/competitions/home-credit-default-risk/rules\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # 5. Unzip all downloaded files
    print("Unzipping downloaded files...")
    extract_zips(RAW_DATA_DIR)

    # 6. Verify that expected CSVs exist
    if check_csvs_exist(RAW_DATA_DIR):
        print(f"Successfully downloaded and extracted dataset to {RAW_DATA_DIR}.")
    else:
        print(
            f"Warning: Extraction completed, but some expected CSVs were not found in {RAW_DATA_DIR}.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
