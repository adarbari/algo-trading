"""Fixed rules of an option position at expiry and around an ex-dividend date (ADR 0088, design
2.4, F1 / section 7.10), as pure decisions: assignment of an in-the-money American short at
expiry, early assignment of a short call the close before an ex-date when the dividend exceeds its
extrinsic value, and the report skip against the selected expiry (N3: a security type that does
not report passes). The callers pass the facts (the dividend of record, the expected report date);
nothing here reads a store."""

import math
from datetime import date

from algotrade.quant.edges.chain_pnl import intrinsic

ASSIGNED, EARLY_ASSIGNED_DIVIDEND, EXPIRED = "ASSIGNED", "EARLY_ASSIGNED_DIVIDEND", "EXPIRED"
REPORTING_TYPES = frozenset({"COMMON_STOCK", "ADR"})  # what files a report (N3)


def expiry_kind(
    spot: float, strike: float, is_call: bool, short: bool, cash_settled: bool
) -> str | None:
    """``ASSIGNED`` for an in-the-money American short at expiry (a cash-settled European index
    root settles at intrinsic instead: ``EXPIRED``), else ``EXPIRED``; None when the spot is
    not known."""
    if not math.isfinite(spot):
        return None  # an unknown spot is not an expiry
    itm = float(intrinsic(spot, strike, is_call)) > 0
    return ASSIGNED if short and itm and not cash_settled else EXPIRED


def early_assignment(
    day: date, ex_date: date | None, dividend: float | None, spot: float, strike: float,
    mid: float, is_call: bool = True, short: bool = True,
) -> bool:  # fmt: skip
    """A short in-the-money call is assigned at the close of the session before ``ex_date`` when
    the ``dividend`` exceeds the call's extrinsic value (``mid`` less intrinsic). ``day`` is that
    close: the caller passes the session before the ex-date. Never for a put or a long leg; an
    unknown dividend or mid is not assigned (never fill)."""
    if not (short and is_call) or ex_date is None or dividend is None or day >= ex_date:
        return False
    value = float(intrinsic(spot, strike, True))
    if value <= 0 or not math.isfinite(mid):
        return False
    return dividend > mid - value


def report_in_life(
    security_type: str | None, expected_report: date | None, entry: date, expiry: date
) -> bool | None:
    """Whether a report falls in the life of the position (``entry`` to ``expiry``): False for a
    type that does not report (ETF, index, closed-end fund), None (UNKNOWN: fails the skip) when a
    reporting type has no expected date."""
    if security_type is None:
        return None
    if security_type not in REPORTING_TYPES:
        return False
    if expected_report is None:
        return None
    return entry <= expected_report <= expiry
