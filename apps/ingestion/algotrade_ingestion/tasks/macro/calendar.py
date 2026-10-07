"""The ``macro-calendar`` task: the macro release calendar -> ``events/macro_release`` (ADR 0050).

Every release of the registry (``config/site/events/releases.toml``) gets one row per release
date from 400 days before the session to 400 days after it. A ``fred`` release is one request
to the registered ``fred_release_dates`` source (FRED lists the scheduled future dates too); a
``rule`` release (ISM: the n-th exchange session of the month) is computed, no fetch. A row's
``ts`` is the release date at ``time_et`` (New York) in UTC.

- ``status``: ``released`` when the release date is on or before the run's session, else
  ``scheduled``; ``moved`` when a later fetch no longer lists a stored scheduled date inside
  the window (FRED rescheduled or withdrew it). A status change is a new version of the same
  row (``instrument_id`` + ``ts``; the table merges runs on it and the latest wins).
- ``known_from`` (ADR 0050 decision 3), of each version: the session it was knowable on. A
  new row: the run's session or, for a past date, the release date (``min``). A version that
  turns ``released``: the same ``min``, so a session before the release date, which reads the
  latest version known by it, still sees ``scheduled`` and the release date on sees
  ``released``. A ``moved`` version: the run's session.

Only the rows the table lacks and the changed versions are written: a rerun on an unchanged
calendar writes nothing. A date FRED moves is a new ``ts``; the old row gets its ``moved``
version.

Per release, an item of the run: ``OK`` (rows written), ``UNCHANGED``, ``NO_DATA`` (FRED has no
dates for it), ``SKIPPED`` with the reason (the source is off, or ``ALGOTRADE_FRED_API_KEY`` is
missing: never an error, ``stats["skipped_releases"]``) or a ``FETCH_ERROR``.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from functools import partial

import pandas as pd

from algotrade.config.site.events.releases import MacroRelease, MacroReleases
from algotrade.core.time.calendar import EXCHANGE_TZ, sessions_between
from algotrade.data.events import ALL_TIME, read_events
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_sources.framework.base import Source
from algotrade_sources.framework.series import RELEASE_FRAME, ReleaseRequest

TASK = "macro_calendar"
TABLE = "events/macro_release"  # the table this task owns (architecture/tables.toml)
WINDOW_DAYS = 400  # dates from this many days before the session to this many after
RULE_SOURCE = "rule"  # the ``source`` stamped on computed rows
SCHEDULED, RELEASED, MOVED = "scheduled", "released", "moved"
KEY = ["instrument_id", "ts"]
COLUMNS = [
    *KEY,
    "release_key",
    "release_name",
    "release_date",
    "time_et",
    "status",
    "known_from",
]
HELD = ["known_from", "status", "release_name", "time_et"]


def release_moment(day: date, clock: time) -> datetime:
    """``day`` at ``clock`` New York time, as an aware UTC datetime."""
    return datetime.combine(day, clock, EXCHANGE_TZ).astimezone(UTC)


def rule_dates(spec: MacroRelease, start: date, end: date) -> list[date]:
    """The n-th exchange session of every month in ``[start, end]`` (``nth_business_day``), or
    the month's ``exceptions`` date where the registry names one, in order; a month with fewer
    sessions than that has no release."""
    assert spec.nth_business_day is not None, f"{spec.key}: not a rule release"
    found: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        following = date(year + month // 12, month % 12 + 1, 1)
        sessions = sessions_between(date(year, month, 1), following - timedelta(1))
        if f"{year}-{month:02d}" in spec.exceptions:
            found.append(spec.exceptions[f"{year}-{month:02d}"])
        elif len(sessions) >= spec.nth_business_day:
            found.append(sessions[spec.nth_business_day - 1])
        year, month = following.year, following.month
    return [d for d in found if start <= d <= end]


def release_rows(spec: MacroRelease, days: Sequence[date], session: date) -> pd.DataFrame:
    """``COLUMNS`` rows of ``spec`` for ``days``, before the stored-row comparison: ``status``
    by the session, ``known_from`` the earlier of the session and the release date."""
    rows = [
        {
            "instrument_id": spec.instrument_id,
            "ts": release_moment(day, spec.clock),
            "release_key": spec.key,
            "release_name": spec.name,
            "release_date": day,
            "time_et": spec.time_et,
            "status": RELEASED if day <= session else SCHEDULED,
            "known_from": min(session, day),
        }
        for day in sorted(set(days))
    ]
    out = pd.DataFrame(rows, columns=COLUMNS)
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    return out


def rows_to_write(target: pd.DataFrame, held: pd.DataFrame) -> pd.DataFrame:
    """The rows of ``target`` the table needs given ``held`` (its stored rows, latest version
    per key): the ones it lacks, those that turn ``released`` (a version of its own, with the
    ``known_from`` of ``target``: a session before the release date still reads ``scheduled``),
    a ``moved`` date FRED lists again, and a changed name (keeping the stored ``known_from``).
    A ``released`` row is final."""
    if target.empty:
        return target
    kept = held.reindex(columns=[*KEY, *HELD])
    kept["ts"] = pd.to_datetime(kept["ts"], utc=True)
    merged = target.merge(kept, on=KEY, how="left", suffixes=("", "_held"))
    new = merged["status_held"].isna()
    turned = (merged["status_held"] == SCHEDULED) & (merged["status"] == RELEASED)
    back = merged["status_held"] == MOVED
    renamed = (merged["status_held"] == merged["status"]) & (
        merged["release_name_held"] != merged["release_name"]
    )
    out = merged[new | turned | back | renamed].copy()
    keep_known = renamed[out.index]
    out.loc[keep_known, "known_from"] = out.loc[keep_known, "known_from_held"]
    return out[COLUMNS].reset_index(drop=True)


def moved_rows(
    held: pd.DataFrame, days: Sequence[date], window: tuple[date, date], session: date
) -> pd.DataFrame:
    """A ``moved`` version of every stored ``scheduled`` date inside ``window`` that a fetch
    which returned ``days`` no longer lists (the date was rescheduled or withdrawn), known
    from ``session``: ``COLUMNS`` rows, none when nothing went missing."""
    if held.empty:
        return held.reindex(columns=COLUMNS)
    dates = pd.to_datetime(held["release_date"]).dt.date
    gone = (
        (held["status"] == SCHEDULED)
        & (dates >= window[0])
        & (dates <= window[1])
        & ~dates.isin(set(days))
    )
    out = held[gone].reindex(columns=COLUMNS).copy()
    out["status"], out["known_from"] = MOVED, session
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    return out.reset_index(drop=True)


def _fetch_dates(
    run: IngestRun, spec: MacroRelease, source: Source, start: date, end: date
) -> list[date]:
    """The release's dates in ``[start, end]`` from FRED (none: ``NoResponseError`` or empty)."""
    request = ReleaseRequest(str(spec.release_id), session_date=run.session, start=start, end=end)
    normalized = run.fetch(source, request)
    frame = normalized.parsed[RELEASE_FRAME] if normalized else None
    if frame is None or frame.empty:
        return []
    days = pd.to_datetime(frame["release_date"]).dt.date
    return [d for d in days if start <= d <= end]


def _one_release(
    run: IngestRun,
    spec: MacroRelease,
    source: Source | None,
    held: pd.DataFrame,
    window: tuple[date, date],
) -> str:
    """Fetch or compute one release, stage what the table lacks -> the item status."""
    if spec.source == "fred":
        assert source is not None
        try:
            days = _fetch_dates(run, spec, source, *window)
        except NoResponseError:
            days = []
        stamp = source.name
    else:
        days, stamp = rule_dates(spec, *window), RULE_SOURCE
    if not days:
        return "NO_DATA"
    new = pd.concat(
        [
            rows_to_write(release_rows(spec, days, run.session), held),
            moved_rows(held, days, window, run.session),
        ],
        ignore_index=True,
    )
    if new.empty:
        return "UNCHANGED"
    run.stage(TABLE, spec.key, new, stamp)
    return f"OK: {len(new)} rows"


def ingest_macro_calendar(
    ctx: TaskContext, releases: MacroReleases, session: date, only: Sequence[str] = ()
) -> RunRecord:
    """Store the new and the newly released dates of the registry's releases (``only``: just
    these keys)."""
    chosen = [r for r in releases.releases if not only or r.key in only]
    unknown = sorted(set(only) - set(releases.keys))
    if unknown:
        raise KeyError(f"no release {unknown} in events/releases.toml")
    window = (session - timedelta(WINDOW_DAYS), session + timedelta(WINDOW_DAYS))
    source = ctx.sources.get("fred_release_dates")
    skipped: dict[str, str] = {}
    with IngestRun(ctx, TASK, session) as run:
        ids = [r.instrument_id for r in chosen]
        held = read_events(run.reader, TABLE, *ALL_TIME, instruments=ids).frame
        for spec in chosen:
            if spec.source == "fred" and source is None:
                why = ctx.unavailable.get("fred_release_dates", "fred_release_dates is not built")
                skipped[spec.key] = why
                run.record_item(spec.key, f"SKIPPED: {why}")
                continue
            mine = held[held["instrument_id"] == spec.instrument_id] if len(held) else held
            run.attempt(spec.key, partial(_one_release, run, spec, source, mine, window))
            run.checkpoint()
        written = run.publish(TABLE)
        run.stats.update(
            releases=len(chosen),
            rows=written,
            window=[window[0].isoformat(), window[1].isoformat()],
            skipped_releases=skipped,
            items=run.counts(),
        )
    return run.record
