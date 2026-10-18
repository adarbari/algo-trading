"""When each FINRA fact became public, as the ``known_from`` the event tables carry (ADR 0050).

``known_from`` is the first session whose nightly run may read a fact (``data.events``: a row
is read as of S when ``known_from <= S``). Both rules are conservative and name the instant
they assume:

- **Short interest**: FINRA publishes on the 7th business day after the settlement date (the
  schedule page lists every date: 2026-09-30 -> 2026-10-09, 2026-10-15 -> 2026-10-26). The
  time of day is not stated anywhere, so the publication is taken as 23:59 New York, after any
  nightly run: ``known_from`` is the session AFTER the publication date. Business days are the
  exchange's sessions; a day FINRA treats as a holiday and the exchange does not would make us
  one day early, which no published date so far shows.
- **Daily short-sale volume**: files are posted "no later than 6:00:00pm ET" on the trade date
  and are sometimes re-posted later ("Updated"), so the trade date's own run does not read it:
  ``known_from`` is the session AFTER the trade date.
"""

from datetime import date

from algotrade.core.time.calendar import next_session

PUBLICATION_LAG_SESSIONS = 7  # short interest: business days from settlement to publication


def publication_date(settlement: date) -> date:
    """The 7th business day after ``settlement``: the day FINRA publishes that short interest."""
    day = settlement
    for _ in range(PUBLICATION_LAG_SESSIONS):
        day = next_session(day)
    return day


def short_interest_known_from(settlement: date) -> date:
    """The session after the publication date (module doc)."""
    return next_session(publication_date(settlement))


def short_volume_known_from(trade_date: date) -> date:
    """The session after the trade date (module doc)."""
    return next_session(trade_date)
