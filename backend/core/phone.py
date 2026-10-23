"""
Phone number normalization utility for Indian phone numbers.
"""

import re


def normalize_phone(raw: str) -> str:
    """
    Normalizes a raw phone number string into canonical E.164 Indian format (+91XXXXXXXXXX).

    Accepted input formats:
    - '+919876543210'
    - '9876543210'
    - '98765 43210'
    - '09876543210'
    - '+91 98765-43210'

    All valid formats map to '+919876543210'.
    Raises ValueError with a clear explanation for invalid or malformed input.
    """
    if raw is None or not isinstance(raw, str):
        raise ValueError("Phone number must be a non-empty string.")

    # Strip whitespace and common punctuation
    cleaned = re.sub(r"[\s\-\(\)\.]+", "", raw.strip())

    if not cleaned:
        raise ValueError("Phone number cannot be empty or blank.")

    # Handle country prefixes
    if cleaned.startswith("+91"):
        digits = cleaned[3:]
    elif cleaned.startswith("0091"):
        digits = cleaned[4:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        digits = cleaned[1:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        digits = cleaned[2:]
    else:
        digits = cleaned

    # Must be exactly 10 digits
    if not digits.isdigit() or len(digits) != 10:
        raise ValueError(
            f"Invalid phone number '{raw}': Expected 10-digit Indian mobile number, got {len(digits)} digits."
        )

    # Indian mobile numbers begin with 6, 7, 8, or 9
    if digits[0] not in ("6", "7", "8", "9"):
        raise ValueError(
            f"Invalid Indian phone number '{raw}': Indian mobile numbers must begin with 6, 7, 8, or 9."
        )

    return f"+91{digits}"
