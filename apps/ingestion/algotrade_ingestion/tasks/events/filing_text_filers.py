"""The filers of the ``filing-text`` backfill (edge build D10b): every CIK that filed a 10-K / 10-Q
(or an amendment) in a window, from the SEC daily form index, delisted companies included.

The universe is today's, so a company delisted before the first snapshot is in no universe table
and no stored table maps a delisted listing to a CIK. The form index is the cheapest honest list
of who filed: one request a business day (the existing ``sec_daily_index`` source, asked for
``PERIODIC_FORMS``; no raw copy is saved, the day's file is every form). A weekday SEC publishes no
index for (a federal holiday: Columbus and Veterans Day are open on the exchange, Good Friday is
not) is skipped; more than ``MAX_GAP`` in a row is a failure, never an empty stretch of filers.

The list of a window in the past is final, so a run records it in its stats
(``filers_window``, ``filer_ciks``) and a later run of the same window reads it from there instead
of walking the days again (a backfill is many runs of ``--limit`` CIKs). A window that reaches the
recording run's own session is walked again.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.events.filings import filing_days
from algotrade_ingestion.tasks.framework.run import IngestRun
from algotrade_sources.framework.base import Source
from algotrade_sources.framework.series import (
    DAILY_INDEX_FRAME,
    PERIODIC_FORMS,
    DailyIndexRequest,
)

MAX_GAP = 6  # weekdays without a published index in a row that end the discovery as a failure
WINDOW_KEY = "filers_window"
CIKS_KEY = "filer_ciks"


class IndexGapError(RuntimeError):
    """More than ``MAX_GAP`` business days in a row without a published form index."""


@dataclass(frozen=True)
class Filers:
    """The CIKs that filed a periodic report in a window, how they were found (``cached``: from an
    earlier run's stats) and the days walked / without an index."""

    ciks: list[str]
    cached: bool
    days: int
    unpublished: list[date]


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


def walk_index(run: IngestRun, index: Source, since: date, until: date) -> Filers:
    """The filers of ``since..until`` read from the daily index, a weekday at a time (module doc).
    A block or a failing day raises: the list is never a partial one."""
    ciks: set[str] = set()
    missing: list[date] = []
    streak = days = 0
    for day in filing_days(since, min(until, run.session)):
        request = DailyIndexRequest(
            key=day.isoformat(), session_date=run.session, day=day, forms=PERIODIC_FORMS
        )
        payload = index.fetch(request)  # no raw copy: the day's file is every form
        days += 1
        if payload is None:
            missing.append(day)
            streak += 1
            if streak > MAX_GAP:
                raise IndexGapError(f"no daily index for {streak} business days up to {day}")
            continue
        streak = 0
        normalized = index.normalize(request, payload)
        assert normalized is not None
        ciks.update(str(c) for c in normalized.parsed[DAILY_INDEX_FRAME]["cik"])
    return Filers(sorted(ciks), False, days, missing)


def discover(
    run: IngestRun, index: Source, runs: Sequence[RunRecord], since: date, until: date
) -> Filers:
    """The filers of ``since..until``: an earlier run's recorded list, else the index walk."""
    if (found := cached_filers(runs, since, until)) is not None:
        return Filers(found, True, 0, [])
    return walk_index(run, index, since, until)
