"""The tenor of an implied-vol field, read from its name (ADR 0053 amendment 2026-10-17): the one
tenor (``iv30``: 30 calendar days, about 21 sessions) that prices every horizon of an
``option_model_pnl`` outcome, so a horizon far from it is refused by the document parser."""

import re

TRADING_DAYS_PER_YEAR, CALENDAR_DAYS_PER_YEAR = 252, 365
_IV_TENOR = re.compile(r"(?<![a-z0-9])iv(\d+)(?![0-9])")


def tenor_sessions(iv_field: str) -> int | None:
    """The tenor of an implied-vol field in sessions (``iv30`` is 30 calendar days: 21), from its
    name; None when the name carries none."""
    found = _IV_TENOR.search(iv_field.lower())
    if found is None:
        return None
    return round(int(found.group(1)) * TRADING_DAYS_PER_YEAR / CALENDAR_DAYS_PER_YEAR)
