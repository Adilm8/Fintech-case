"""Risk scoring weights, thresholds, and deterministic demo constants."""

from __future__ import annotations

from datetime import date

# Fixed reference date for synthetic data generation and recency checks.
DEMO_TODAY: date = date(2026, 4, 20)

# Bank CenterCredit identifiers (matching data/banks.json).
BCC_BANK_CODE: str = "125"
BCC_BIK: str = "KCJBKZKX"

# Verdict score thresholds (green < 30, yellow 30..64, red >= 65).
THRESHOLD_YELLOW: int = 30
THRESHOLD_RED: int = 65

# Amplifiers alone cannot exceed this cap (prevents amplifiers alone from turning yellow).
AMPLIFIER_ONLY_CAP: int = 29

# A single signal at or below this point value alone does not raise colour.
SINGLE_SIGNAL_NO_RAISE_MAX: int = 25

# Primary and standalone signal weights.
WEIGHT_LOOKALIKE_SUPPLIER: int = 60
WEIGHT_BIN_NAME_MISMATCH: int = 50
WEIGHT_IIK_CHANGED: int = 35
WEIGHT_ENTITY_TYPE_MISMATCH: int = 25
WEIGHT_NEW_BCC_ACCOUNT: int = 25

# Amplifier weights.
WEIGHT_BANK_CHANGED_AMPLIFIER: int = 15
WEIGHT_URGENT_WORDING: int = 10
WEIGHT_AMOUNT_ANOMALY_MIN: int = 10
WEIGHT_AMOUNT_ANOMALY_MAX: int = 25

# Rule parameters.
LOOKALIKE_SIMILARITY_THRESHOLD: float = 85.0
NEW_BCC_ACCOUNT_MAX_DAYS: int = 30
AMOUNT_ANOMALY_MIN_HISTORY: int = 5

URGENT_PHRASES: tuple[str, ...] = (
    "срочно",
    "новые реквизиты",
    "изменились реквизиты",
    "по новым реквизитам",
)
