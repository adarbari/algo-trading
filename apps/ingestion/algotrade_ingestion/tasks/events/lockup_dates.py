"""The date rules of ``events/ipo_lockup`` (ADR 0050, edge build D8), pure and calendar-only.

- **Acceptance session** (``acceptance_session``): ``core.time.calendar.acceptance_session``, the
  repo's one rule for an SEC acceptance: the first session whose close is after the instant (an
  acceptance at or after 16:00 New York, on a weekend or a holiday counts from the next session).
- **Lock-up end** (``restriction_end``): ``prospectus_date`` + the term. A term in days adds
  calendar days; one in months adds calendar months (the day clamped to the month's last day).
  ``lockup_days`` is the days between the two dates, so a "six months" term is the exact count
  of that prospectus.
- **Expiry** (``expiry_session``): the first exchange session strictly after ``restriction_end``,
  the first day holders may sell ("180 days after the date of this prospectus" restricts through
  that day). It is a future-dated fact, known from the acceptance.
- **Re-extraction** (``restated_known_from``): a row first stored is known from its acceptance
  session, a backfill included; a re-extracted row whose values changed is known from the later
  of that session and the session after the exchange date of the fetch's own clock (never the
  window the run asked for), because the change was not knowable before the run that found it.
"""

import calendar
from datetime import date, datetime, timedelta

import pandas as pd

from algotrade.core.time.calendar import acceptance_session as core_acceptance_session
from algotrade.core.time.calendar import exchange_date, next_session

DAYS, MONTHS = "days", "months"


def acceptance_session(accepted: pd.Timestamp) -> date:
    """The session ``accepted`` (an aware instant) is known from (module doc)."""
    return core_acceptance_session(accepted.to_pydatetime())


def restriction_end(start: date, n: int, unit: str) -> date:
    """``start`` + ``n`` calendar ``days`` or ``months`` (module doc)."""
    if unit == DAYS:
        return start + timedelta(days=n)
    if unit != MONTHS:
        raise ValueError(f"unknown lock-up unit {unit!r}")
    month = start.month - 1 + n
    year, month = start.year + month // 12, month % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def expiry_session(end: date) -> date:
    """The first exchange session strictly after ``end``."""
    return next_session(end)


def restated_known_from(acceptance: date, now: datetime) -> date:
    """``known_from`` of a version that changed values, found by a run whose clock reads ``now``."""
    return max(acceptance, next_session(exchange_date(now)))
