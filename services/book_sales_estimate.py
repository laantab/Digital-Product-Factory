"""Isolated Book Sales Estimate calculator.

Factory does not ship an authorized BSR-to-sales formula. This module is
intentionally modular so a verified method can be configured later without
changing research scoring. Until then, estimation is unavailable and must
never invent sales, revenue, or BSR figures.
"""
from __future__ import annotations

UNAVAILABLE_REASON = (
    "Book sales estimation is unavailable until a verified method is configured. "
    "Factory does not invent BSR, unit sales, or revenue figures."
)

NOT_VERIFIED = "Not verified"


def estimate_book_sales(bsr=None, **_kwargs) -> dict:
    """Return a structured unavailable estimate. Never fabricates numbers."""
    del bsr  # accepted for future wiring; ignored until a verified method exists
    return {
        "available": False,
        "status": "unavailable",
        "method": None,
        "bsr": NOT_VERIFIED,
        "estimated_monthly_sales": NOT_VERIFIED,
        "estimated_revenue": NOT_VERIFIED,
        "reason": UNAVAILABLE_REASON,
        "disclaimer": (
            "Scores and revenue estimates are research indicators, "
            "not guaranteed sales or earnings."
        ),
    }
