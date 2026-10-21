"""The filers of the ``filing-text`` backfill (edge build D10b): every CIK that filed a 10-K / 10-Q
(or an amendment) in a window, from the SEC daily form index, delisted companies included.

The universe is today's, so a company delisted before the first snapshot is in no universe table
and no stored table maps a delisted listing to a CIK. The form index is the cheapest honest list
of who filed: one request a business day (the existing ``sec_daily_index`` source, asked for
``PERIODIC_FORMS``; no raw copy is saved, the day's file is every form). SEC publishes no index on
its closure days (``sec_holidays``: the federal holidays, observed on the weekday before or after
a weekend one, and the two national days of mourning since 2018; Columbus and Veterans Day are
open on the exchange but closed at SEC, Good Friday the reverse). A weekday with no index that is
none of those is a failure, never an empty day of filers: the list is built whole or the run
fails, and only a whole list is recorded.

The list of a window in the past is final, so a run records it in its stats
(``filers_window``, ``filer_ciks``) and a later run of the same window reads it from there instead
of walking the days again (a backfill is many runs of ``--limit`` CIKs). A window that reaches the
recording run's own session is walked again.
"""

from collections.abc import Collection, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta

from algotrade.core.time.calendar import is_weekend, nth_weekday
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.events.filings import filing_days
from algotrade_ingestion.tasks.framework.run import IngestRun
from algotrade_sources.framework.base import Source
from algotrade_sources.framework.series import (
    DAILY_INDEX_FRAME,
    PERIODIC_FORMS,
    DailyIndexRequest,
)

SPECIAL_CLOSURES = frozenset(
    {
        *(date(2010, 2, d) for d in range(8, 12)),  # winter storm
        date(2012, 10, 29),  # Hurricane Sandy
        date(2012, 10, 30),
        date(2012, 12, 24),  # executive-order closures
        date(2014, 12, 26),
        date(2015, 12, 24),
        date(2018, 12, 24),
        date(2019, 12, 24),
        date(2020, 12, 24),
        date(2024, 12, 24),
        date(2025, 12, 24),
        date(2025, 12, 26),
        date(2018, 12, 5),  # national days of mourning: Bush, Carter
        date(2025, 1, 9),
        date(2017, 1, 20),  # Inauguration Days that fell on a weekday
        date(2021, 1, 20),
    }
)
WALK_THREADS = 6  # daily index files in flight (the shared SEC limiter sets the rate)
WINDOW_KEY = "filers_window"
CIKS_KEY = "filer_ciks"


class IndexGapError(RuntimeError):
    """A weekday that is no SEC holiday has no published form index (``--allow-gap`` lists one an
    operator has verified)."""


def _observed(day: date) -> date:
    """A holiday on a Saturday is observed the Friday before, one on a Sunday the Monday after."""
    if not is_weekend(day):
        return day
    return (
        day - timedelta(days=1) if is_weekend(day + timedelta(days=1)) else day + timedelta(days=1)
    )


def sec_holidays(year: int) -> set[date]:
    """The weekdays SEC is closed in ``year``: the federal holidays (a Saturday one is observed
    the Friday before, a Sunday one the Monday after) and the executive-order, mourning,
    inauguration and weather closures of ``SPECIAL_CLOSURES``."""
    fixed = [date(year, 1, 1), date(year, 7, 4), date(year, 11, 11), date(year, 12, 25)]
    if year >= 2021:
        fixed.append(date(year, 6, 19))  # Juneteenth
    named = [
        nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        nth_weekday(year, 2, 0, 3),  # Presidents Day
        nth_weekday(year, 5, 0, -1),  # Memorial Day
        nth_weekday(year, 9, 0, 1),  # Labor Day
        nth_weekday(year, 10, 0, 2),  # Columbus Day
        nth_weekday(year, 11, 3, 4),  # Thanksgiving
    ]
    observed = {_observed(d) for d in fixed}
    return {d for d in observed | set(named) if not is_weekend(d)} | {
        d for d in SPECIAL_CLOSURES if d.year == year
    }


@dataclass(frozen=True)
class Filers:
    """The CIKs that filed a periodic report in a window, how they were found (``cached``: from an
    earlier run's stats) and the days walked / SEC holidays among them."""

    ciks: list[str]
    cached: bool
    days: int
    holidays: list[date]


def window_label(since: date, until: date) -> str:
    return f"{since.isoformat()}..{until.isoformat()}"


def cached_filers(runs: Sequence[RunRecord], since: date, until: date) -> list[str] | None:
    """The filers an earlier run recorded for exactly ``since..until``, when that window ended
    before the recording run's session (a window still open is not final)."""
    label = window_label(since, until)
    for record in sorted(runs, key=lambda r: r.started_at, reverse=True):
        found = record.stats.get(CIKS_KEY)
        if record.stats.get(WINDOW_KEY) == label and found and until < record.session_date:
            return [str(c) for c in found]
    return None


def walk_index(
    run: IngestRun,
    index: Source,
    since: date,
    until: date,
    allowed: Collection[date] = (),
) -> Filers:
    """The filers of ``since..until`` read from the daily index, a weekday at a time (module doc).
    A block or a failing day raises, so does a weekday with no index that is no SEC holiday (the
    run's own day may not be published yet) unless an operator verified it and listed it in
    ``allowed`` (``--allow-gap``): the list is never a partial one."""
    ciks: set[str] = set()
    closed: list[date] = []
    days = 0
    walk = list(filing_days(since, min(until, run.session)))

    def read(day: date) -> frozenset[str] | None:
        request = DailyIndexRequest(
            key=day.isoformat(), session_date=run.session, day=day, forms=PERIODIC_FORMS
        )
        payload = index.fetch(request)  # no raw copy: the day's file is every form
        if payload is None:
            return None
        normalized = index.normalize(request, payload)
        assert normalized is not None
        return frozenset(str(c) for c in normalized.parsed[DAILY_INDEX_FRAME]["cik"])

    with ThreadPoolExecutor(WALK_THREADS, thread_name_prefix="ft-index") as pool:
        futures = [pool.submit(read, day) for day in walk]  # the shared limiter sets the rate
        try:
            for day, future in zip(walk, futures, strict=True):
                found = future.result()  # in day order: the first failing day is the one raised
                days += 1
                if found is None:
                    if day in allowed or day in sec_holidays(day.year) | sec_holidays(day.year + 1):
                        closed.append(day)
                        continue
                    if day >= run.session:  # today's index comes after the close
                        continue
                    raise IndexGapError(
                        f"no daily index for {day}, a weekday that is no SEC holiday: if SEC was "
                        f"closed (verified by hand), pass --allow-gap {day}"
                    )
                ciks.update(found)
        except BaseException:
            for future in futures:
                future.cancel()  # a failed walk sends no more requests
            raise
    return Filers(sorted(ciks), False, days, closed)


def discover(
    run: IngestRun,
    index: Source,
    runs: Sequence[RunRecord],
    since: date,
    until: date,
    allowed: Collection[date] = (),
) -> Filers:
    """The filers of ``since..until``: an earlier run's recorded list, else the index walk
    (``allowed``: verified weekdays with no index, ``--allow-gap``)."""
    if (found := cached_filers(runs, since, until)) is not None:
        return Filers(found, True, 0, [])
    return walk_index(run, index, since, until, allowed)
