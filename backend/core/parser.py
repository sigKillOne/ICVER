import re

def extract_upi_inflow(sms_text: str) -> float:
    """
    Parses unstructured Indian banking and UPI SMS transaction logs to extract and sum
    credit/inflow amounts.

    Recognizes patterns such as:
      - 'Credited Rs. 500' / 'Credited Rs.500'
      - 'Received INR 1050.50'
      - 'Rs.200 credited' / 'Rs 200 credited'
      - 'credited with INR 2,000.00' / 'credited by Rs 300'
      - '₹500 has been credited' / 'credit of Rs 500'

    Args:
        sms_text: Raw text string containing one or multiple SMS receipts.

    Returns:
        float: Sum of all detected incoming credit amounts rounded to 2 decimal places.
    """
    if not sms_text or not isinstance(sms_text, str):
        return 0.0

    patterns = [
        # Pattern 1: Action preceding currency and amount
        # e.g., 'Credited Rs. 500', 'Received INR 1050.50', 'credited with Rs. 2,000.00'
        r'(?:credited|received|recd|deposited|credit\s+of)\s+(?:with\s+|by\s+|for\s+)?(?:rs\.?|inr|₹)?\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?)',
        # Pattern 2: Currency and amount preceding action
        # e.g., 'Rs.200 credited', 'INR 1,500.50 received', '₹500 has been credited'
        r'(?:rs\.?|inr|₹)\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?)\s*(?:is\s+|has been\s+)?(?:credited|received|recd|deposited)',
    ]

    matched_spans = []
    total = 0.0

    for pattern in patterns:
        for match in re.finditer(pattern, sms_text, re.IGNORECASE):
            span = match.span()
            # Avoid double-counting overlapping match spans
            if any(max(span[0], m[0]) < min(span[1], m[1]) for m in matched_spans):
                continue
            matched_spans.append(span)
            raw_val = match.group(1).replace(',', '')
            try:
                total += float(raw_val)
            except ValueError:
                pass

    return round(total, 2)
