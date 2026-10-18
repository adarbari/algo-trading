"""The tenor of an ``option_model_pnl`` outcome's implied-vol field (ADR 0053 amendment
2026-10-17), read from the field's name, and the horizons it can price: split from
``document.py`` (at its line cap), which checks an outcome's horizons with it."""

import re

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

# The implied vol is one tenor (``iv30``: 30 calendar days, about 21 sessions) and prices every
# horizon of the outcome, so a horizon far from it prices the wrong option: an option_model_pnl
# horizon must lie within ``[tenor / 2, tenor * 2]`` sessions of the field's tenor, read from its
# name (a field with no ``iv<days>`` in its name has no known tenor and is refused).
TRADING_DAYS_PER_YEAR, CALENDAR_DAYS_PER_YEAR = 252, 365
_IV_TENOR = re.compile(r"(?<![a-z0-9])iv(\d+)(?![0-9])")


def tenor_sessions(iv_field: str) -> int | None:
    """The tenor of an implied-vol field in sessions (``iv30`` is 30 calendar days: 21), from its
    name; None when the name carries none."""
    found = _IV_TENOR.search(iv_field.lower())
    if found is None:
        return None
    return round(int(found.group(1)) * TRADING_DAYS_PER_YEAR / CALENDAR_DAYS_PER_YEAR)


def check_tenor(o: Table, horizons: tuple[int, ...], iv_field: str | None) -> None:
    """Refuse an ``option_model_pnl`` horizon the field's one tenor cannot price (module top)."""
    if iv_field is None:
        return  # required, and reported, by ``_expires_otm``
    tenor = tenor_sessions(iv_field)
    if tenor is None:
        raise ConfigurationError(
            f"{o.where} iv_field: {iv_field!r} names no tenor (iv<days>), so an option_model_pnl "
            f"cannot tell which horizons its vol prices"
        )
    low, high = tenor // 2, tenor * 2
    bad = [h for h in horizons if not low <= h <= high]
    if bad:
        raise ConfigurationError(
            f"{o.where} horizon_sessions: {bad} are outside {low}..{high} sessions, what the "
            f"{tenor}-session tenor of {iv_field!r} prices; use a field of the horizon's tenor"
        )
