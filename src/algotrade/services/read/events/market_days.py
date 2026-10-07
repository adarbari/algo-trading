"""The market-structure days of a window, by rule (ADR 0050 decision 1, "market structure"):
the monthly option expiries (the quarterly ones in March, June, September and December, when
stock options, index options and futures expire together), the quarter ends and the Russell
reconstitution. The dates come from the exchange calendar (``core.time.calendar``: a rule day
the exchange is closed on moves to the session before); this module names them. Pure: no
store read, the same for every instrument."""

from dataclasses import dataclass
from datetime import date

from algotrade.core.time.calendar import (
    last_session_of_month,
    monthly_expiry,
    russell_reconstitution,
)

QUARTER_MONTHS = (3, 6, 9, 12)
RECONSTITUTION_MONTH = 6


@dataclass(frozen=True)
class MarketDay:
    """A market-structure day: its date, a short label and what happens (all at the close);
    ``expiry``: the monthly or quarterly option expiry (what the calendar rules)."""

    date: date
    label: str
    name: str
    expiry: bool = False


def _months(start: date, end: date) -> list[tuple[int, int]]:
    first, last = start.year * 12 + start.month - 1, end.year * 12 + end.month - 1
    return [(m // 12, m % 12 + 1) for m in range(first, last + 1)]


def _month_days(year: int, month: int) -> list[MarketDay]:
    quarter = month in QUARTER_MONTHS
    days = [
        MarketDay(
            monthly_expiry(year, month),
            "Quarterly expiry" if quarter else "Monthly expiry",
            "Stock and index options and index futures expire (quarterly expiry)"
            if quarter
            else "Monthly options expire (the third Friday)",
            expiry=True,
        )
    ]
    if quarter:
        days.append(
            MarketDay(
                last_session_of_month(year, month),
                "Quarter end",
                f"Last session of Q{month // 3} {year}: fund rebalancing and window dressing",
            )
        )
    if month == RECONSTITUTION_MONTH:
        days.append(
            MarketDay(
                russell_reconstitution(year),
                "Russell reconstitution",
                "The Russell US indexes reconstitute at the close",
            )
        )
    return days


def market_days(start: date, end: date) -> tuple[MarketDay, ...]:
    """The market-structure days in ``start..end`` (inclusive), by date then label."""
    days = (d for year, month in _months(start, end) for d in _month_days(year, month))
    return tuple(
        sorted((d for d in days if start <= d.date <= end), key=lambda d: (d.date, d.label))
    )
