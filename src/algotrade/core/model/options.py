"""Listed option contract identity: OSI symbols, rights and standard monthly expiries."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from algotrade.core.time.calendar import third_friday

_OSI = re.compile(r"^(?P<root>.*?)(?P<expiry>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")


class OptionRight(StrEnum):
    CALL = "C"
    PUT = "P"


@dataclass(frozen=True, slots=True)
class OsiSymbol:
    """A parsed OCC/OSI option symbol such as ``SPY261231C00586000``."""

    root: str
    expiry: date
    right: OptionRight
    strike: float


def parse_osi(symbol: str) -> OsiSymbol | None:
    """Parse an OSI symbol. Returns ``None`` if ``symbol`` is not one."""
    match = _OSI.match(symbol.strip())
    if not match:
        return None
    raw = match.group("expiry")
    expiry = date(2000 + int(raw[:2]), int(raw[2:4]), int(raw[4:]))
    return OsiSymbol(
        root=match.group("root").strip(),
        expiry=expiry,
        right=OptionRight(match.group("right")),
        strike=int(match.group("strike")) / 1000,
    )


def is_standard_root(root: str, underlying: str) -> bool:
    """False for adjusted/non-standard series (e.g. ``AAPL1`` after a corporate action)."""
    return root.replace(".", "") == underlying.replace(".", "")


def standard_monthly_expiries(listed: Iterable[date]) -> set[date]:
    """The standard monthly expiry in each month present in ``listed``.

    That is the third Friday, or the business day before it when the Friday is an exchange
    holiday (Good Friday, Juneteenth). Uses the listed expiries themselves, so no holiday
    calendar is needed: if the third Friday is not listed, the preceding Thursday is used
    when it is.
    """
    expiries = set(listed)
    monthly: set[date] = set()
    for year, month in {(e.year, e.month) for e in expiries}:
        friday = third_friday(year, month)
        thursday = friday - timedelta(days=1)
        if friday in expiries:
            monthly.add(friday)
        elif thursday in expiries:
            monthly.add(thursday)
    return monthly
