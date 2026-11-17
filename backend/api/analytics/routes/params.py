"""Shared parsing / validation of query-string parameters for the GET endpoints."""

from fastapi import HTTPException


def parse_tickers(raw: str, max_tickers: int) -> list[str]:
    """Split a comma-separated ticker list, rejecting empty or oversized inputs (422)."""
    tickers = list(dict.fromkeys(t.strip() for t in raw.split(",") if t.strip()))
    if not tickers:
        raise HTTPException(status_code=422, detail="tickers is required")
    if len(tickers) > max_tickers:
        raise HTTPException(status_code=422, detail=f"At most {max_tickers} tickers per request (got {len(tickers)})")
    return tickers


def check_date_range(start_date: str, end_date: str) -> None:
    if start_date > end_date:  # ISO-formatted (IsoDate) strings compare chronologically
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")


def parse_confidence_levels(raw: str, max_levels: int = 10) -> list[float]:
    """Parse '0.95,0.99' into floats strictly between 0 and 1 (422 otherwise)."""
    try:
        levels = [float(x) for x in (p.strip() for p in raw.split(",")) if x]
    except ValueError:
        raise HTTPException(status_code=422, detail="confidence_levels must be comma-separated numbers, e.g. 0.95,0.99") from None
    if not levels or len(levels) > max_levels or not all(0 < c < 1 for c in levels):
        raise HTTPException(
            status_code=422, detail=f"confidence_levels must contain 1 to {max_levels} values strictly between 0 and 1"
        )
    return levels
