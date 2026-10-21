"""The default session follows the current serving release (ADR 0077 decision 7, ADR 0062): with a
``Serving`` the session a read with no date serves is the release's, whatever the nightly has
completed since; a complete but unreleased newer session is disclosed as ``PUBLISHING`` once the
configured delay has passed since the run that completed it finished, and the cached session
changes with that flag, not with the browser."""

from datetime import UTC, date, datetime, timedelta

from algotrade.data import StoreReader
from algotrade.services.read.context import ResultCache, served_session
from algotrade.services.read.session import (
    NIGHTLY,
    NewerSession,
    NewerState,
    Serving,
    default_session,
    publishing_due,
    resolve_session,
)
from algotrade.storage.runs import RunRecord, RunStatus
from tests.unit.services.read.test_session import EXPECTED, store, write_bar

D1, D2, D3 = date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)
DELAY = timedelta(minutes=15)


def finished(reader: StoreReader, day: date, status: RunStatus, minute: int = 0) -> datetime:
    """A ``nightly`` record of ``day`` that finished at 22:00 UTC + ``minute``."""
    end = datetime(day.year, day.month, day.day, 22, minute, tzinfo=UTC)
    record = RunRecord(
        f"nightly-{day}-{minute}", NIGHTLY, day, end - timedelta(hours=1), status, end
    )
    reader._backend.runs.save(record)  # type: ignore[attr-defined]
    return end


def world() -> tuple[StoreReader, datetime]:
    """D1, D2 complete and D3 complete too (finished 22:00 UTC): a release serves D2."""
    writer, reader = store()
    for day in (D1, D2, D3):
        write_bar(writer, day)
    finished(reader, D1, RunStatus.COMPLETE)
    finished(reader, D2, RunStatus.COMPLETE)
    return reader, finished(reader, D3, RunStatus.COMPLETE)


def serving(day: date, now: datetime) -> Serving:
    return Serving(day, now, DELAY)


def test_the_default_session_is_the_releases_not_the_newest_complete_one() -> None:
    reader, done = world()
    live = resolve_session(reader, None, EXPECTED)
    assert live.date == D3 == default_session(reader)  # ADR 0062 unchanged without a release
    served = resolve_session(reader, None, EXPECTED, serving(D2, done + timedelta(minutes=1)))
    assert (served.date, served.requested, served.is_latest, served.complete) == (
        D2,
        None,
        True,
        True,
    )
    assert served.cutoff is not None and served.cutoff.date() == D2


def test_a_complete_unreleased_session_is_disclosed_only_after_the_publishing_delay() -> None:
    reader, done = world()
    early = resolve_session(reader, None, EXPECTED, serving(D2, done + timedelta(minutes=14)))
    assert early.newer is None  # the release is probably about to be promoted: nothing to say
    late = resolve_session(reader, None, EXPECTED, serving(D2, done + DELAY))
    assert late.newer == NewerSession(D3, NewerState.PUBLISHING)


def test_a_session_still_running_or_failed_after_the_released_one_is_disclosed_as_before() -> None:
    writer, reader = store()
    for day in (D1, D2, D3):
        write_bar(writer, day)
    finished(reader, D1, RunStatus.COMPLETE)
    end = finished(reader, D2, RunStatus.COMPLETE)
    finished(reader, D3, RunStatus.FAILED)
    served = resolve_session(reader, None, EXPECTED, serving(D2, end + timedelta(hours=3)))
    assert served.date == D2 and served.newer is not None
    assert served.newer.state is NewerState.FAILED_RETRYING


def test_a_requested_date_is_never_changed_by_a_release() -> None:
    reader, done = world()
    asked = resolve_session(reader, D3, EXPECTED, serving(D2, done + DELAY))
    assert (asked.date, asked.requested, asked.newer) == (D3, D3, None)


def test_the_cached_session_changes_when_the_delay_passes_not_before() -> None:
    reader, done = world()
    cache = ResultCache()
    early = served_session(reader, cache, serving(D2, done + timedelta(minutes=5)))
    again = served_session(reader, cache, serving(D2, done + timedelta(minutes=10)))
    assert again is early  # one cached session while the flag holds
    late = served_session(reader, cache, serving(D2, done + timedelta(minutes=16)))
    assert early.newer is None and late.newer == NewerSession(D3, NewerState.PUBLISHING)


def test_a_release_for_the_newest_complete_session_has_nothing_newer_to_say() -> None:
    reader, done = world()
    current = resolve_session(reader, None, EXPECTED, serving(D3, done + timedelta(hours=2)))
    assert (current.date, current.newer) == (D3, None)


def counting_runs(reader: StoreReader) -> list[int]:
    """Count the reads of run records the store serves (each opens a JSON file locally)."""
    backend = reader._backend  # type: ignore[attr-defined]
    real, calls = backend.runs.find, []

    def find(*args: object, **kwargs: object) -> object:
        calls.append(1)
        return real(*args, **kwargs)

    backend.runs.find = find
    return calls


def test_a_request_does_not_read_run_records_per_call_under_a_release() -> None:
    """The session is cached and so is the instant the publishing flag flips: asking for it again
    (every request of every non-listed operation does) opens no run file."""
    reader, done = world()
    cache = ResultCache()
    calls = counting_runs(reader)
    served_session(reader, cache, serving(D2, done + timedelta(minutes=5)))
    first = len(calls)
    for minute in (6, 7, 8):
        served_session(reader, cache, serving(D2, done + timedelta(minutes=minute)))
    assert len(calls) == first  # no further read while the flag holds
    flipped = served_session(reader, cache, serving(D2, done + DELAY))
    assert flipped.newer == NewerSession(D3, NewerState.PUBLISHING)
    after_flip = len(calls)
    served_session(reader, cache, serving(D2, done + DELAY + timedelta(minutes=1)))
    assert len(calls) == after_flip


def test_a_complete_record_without_bars_is_not_a_session_to_publish() -> None:
    writer, reader = store()
    for day in (D1, D2):
        write_bar(writer, day)
    finished(reader, D1, RunStatus.COMPLETE)
    finished(reader, D2, RunStatus.COMPLETE)
    end = finished(reader, D3, RunStatus.COMPLETE)  # no bars/1d for D3
    served = resolve_session(reader, None, EXPECTED, serving(D2, end + timedelta(hours=2)))
    assert served.newer is not None and served.newer.state is NewerState.IN_PROGRESS
    assert Serving(D2, end + timedelta(hours=2), DELAY).key(publishing_due(reader, D2, DELAY)) == (
        D2,
        False,
    )
