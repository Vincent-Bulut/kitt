"""Classification of instruments from their names.

Leveraged and inverse ETFs (e.g. "Amundi CAC 40 Daily (-2x) Inverse") reset their
exposure daily: they are trading tools, not buy-and-hold building blocks. In a
mean-variance search they show up as hedges (strongly negative correlation),
which can win on Sharpe while only cancelling exposure.
"""

import re

_LEVERAGED_OR_INVERSE = re.compile(
    r"""
      \(\s*-?\d+(?:[.,]\d+)?\s*x\s*\)      # (2x), (-1x), (-2x), (3x)
    | \binverse\b
    | \bleveraged?\b
    | \blevdax\b
    | \bbear\b
    | \bdaily\s+short\b | \bshort\s+daily\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_leveraged_or_inverse(name: str | None) -> bool:
    return bool(name) and _LEVERAGED_OR_INVERSE.search(name) is not None
