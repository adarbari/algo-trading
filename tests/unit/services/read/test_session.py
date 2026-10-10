"""One resolved session per read (ADR 0036): which date a read serves, what is stored for it,
which reference snapshot identity comes from, and how each table grain is read."""

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.services.read.availability.cause import UnavailableKind
from algotrade.services.read.session import (
    EXPECTED_TABLES,
    NIGHTLY,
    Grain,
    NewerSession,
    NewerState,
    NotFoundError,
    Session,
    default_session,
    expected_tables,
    grain_of,
    latest_session,
    resolve_session,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows
from tests.helpers.stored_frames import write_reference

D0, D1, D2, D3 = date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)
EARNINGS = "rollups/instrument/earnings@v1"
STATUS = "chains/status"
EXPECTED = ("bars/1d", STATUS, EARNINGS)


def store() -> tuple[StoreWriter, StoreReader]:
    backend = MemoryBackend()
    return StoreWriter(backend), StoreReader(backend)


def nightly(reader: StoreReader, day: date, status: RunStatus, hour: int = 6) -> None:
    """Save a ``nightly`` run record of ``day`` in ``status`` (started at ``hour`` UTC)."""
    started = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
    record = RunRecord(f"nightly-{day}-{hour}", NIGHTLY, day, started, status)
    reader._backend.runs.save(record)


def write_bar(writer: StoreWriter, day: date) -> None:
    bar = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
    row = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), **bar}
    write_rows(writer, "bars/1d", day, [row])


def write_earnings(writer: StoreWriter, day: date) -> None:
    write_rows(writer, EARNINGS, day, [{"instrument_id": "EQ:AAA", "days_to_earnings": 3}])


def test_an_empty_store_has_no_latest_session() -> None:
    _, reader = store()
    with pytest.raises(NotFoundError, match="nothing stored"):
        resolve_session(reader, None, EXPECTED)


def test_latest_session_is_the_latest_bars_else_the_reference_snapshot() -> None:
    writer, reader = store()
    assert latest_session(reader) is None
    write_reference(writer, D2, {"AAA": "EQ:AAA"})
    assert latest_session(reader) == D2  # no bars: the reference snapshot
    write_bar(writer, D1)
    assert latest_session(reader) == D1  # bars win, even an earlier partition


def test_a_requested_date_is_served_even_when_nothing_is_stored_for_it() -> None:
    _, reader = store()
    found = resolve_session(reader, D2, EXPECTED)
    assert found == Session(
        date=D2, requested=D2, is_latest=False, latest_with_bars=None,
        reference_snapshot=None, pre_snapshot=False, present=(), missing=EXPECTED,
        unavailable=found.unavailable,
    )  # fmt: skip
    tables = [u.cause.links[0].subject for u in found.unavailable]
    assert tables == sorted(EXPECTED)  # one per table, its features after it


def test_no_date_resolves_to_the_latest_bars_partition() -> None:
    writer, reader = store()
    for day in (D1, D2):
        write_bar(writer, day)
    write_reference(writer, D3, {"AAA": "EQ:AAA"})  # a later reference never moves the session
    session = resolve_session(reader, None, EXPECTED)
    assert (session.date, session.requested, session.is_latest) == (D2, None, True)
    assert session.latest_with_bars == D2


def test_no_bars_resolves_to_the_latest_reference_snapshot() -> None:
    writer, reader = store()
    write_reference(writer, D1, {"AAA": "EQ:AAA"})
    write_reference(writer, D2, {"AAA": "EQ:AAA"})
    session = resolve_session(reader, None, EXPECTED)
    assert (session.date, session.is_latest, session.latest_with_bars) == (D2, True, None)
    assert (session.reference_snapshot, session.pre_snapshot) == (D2, False)


def test_an_earlier_or_later_requested_date_is_not_the_latest() -> None:
    writer, reader = store()
    for day in (D1, D2):
        write_bar(writer, day)
    assert resolve_session(reader, D1, EXPECTED).is_latest is False
    assert resolve_session(reader, D2, EXPECTED).is_latest is True
    later = resolve_session(reader, D3, EXPECTED)
    assert (later.date, later.is_latest, later.present) == (D3, False, ())


def test_snapshot_grain_is_disclosed_latest_on_or_before_else_pre_snapshot() -> None:
    writer, reader = store()
    write_reference(writer, D1, {"AAA": "EQ:AAA"})
    write_reference(writer, D3, {"AAA": "EQ:AAA"})
    on_or_before = resolve_session(reader, D2, EXPECTED)
    assert (on_or_before.reference_snapshot, on_or_before.pre_snapshot) == (D1, False)
    exact = resolve_session(reader, D3, EXPECTED)
    assert (exact.reference_snapshot, exact.pre_snapshot) == (D3, False)
    before_first = resolve_session(reader, D0, EXPECTED)  # survivorship: a later list stands in
    assert (before_first.reference_snapshot, before_first.pre_snapshot) == (D1, True)


def test_present_and_missing_are_for_exactly_the_session() -> None:
    """An older partition exists (earnings on D1) and is ignored: D2 lists it missing."""
    writer, reader = store()
    for day in (D1, D2):
        write_bar(writer, day)
    write_earnings(writer, D1)
    session = resolve_session(reader, D2, EXPECTED)
    assert (session.present, session.missing) == (("bars/1d",), (STATUS, EARNINGS))
    earlier = resolve_session(reader, D1, EXPECTED)
    assert (earlier.present, earlier.missing) == (("bars/1d", EARNINGS), (STATUS,))


def test_expected_tables_are_the_declared_nightly_session_tables() -> None:
    assert "bars/1d" in EXPECTED_TABLES
    assert {EARNINGS, STATUS, "results/rule_screen"} <= set(EXPECTED_TABLES)
    assert list(EXPECTED_TABLES) == sorted(EXPECTED_TABLES)
    assert all(grain_of(t) is Grain.SESSION for t in EXPECTED_TABLES)
    never = ("verification/", "live/", "events/", "instruments/", "holdings/", "rollups/daily/")
    assert not [t for t in EXPECTED_TABLES if t.startswith(never) or "*" in t]
    # an evaluation on request, partitioned by its range end: never missing for a session
    assert "results/edge_eval" not in EXPECTED_TABLES


def test_expected_tables_skip_families_and_other_grains(tmp_path: Path) -> None:
    tables = tmp_path / "tables.toml"
    tables.write_text(
        "\n".join(
            f'[[table]]\nname = "{name}"\nowner = "x.py"\n'
            for name in ("results/*", "results/a", "chains/status", "live/option_quotes",
                         "verification/ibkr", "instruments/reference", "rollups/instrument/x@v1")
        )
        + '[[table]]\nname = "results/eval"\nowner = "x.py"\nper_session = false\n'
    )  # fmt: skip
    assert expected_tables(tables) == (
        "bars/1d", "chains/status", "results/a", "rollups/instrument/x@v1",
    )  # fmt: skip


@pytest.mark.parametrize(
    ("table", "grain"),
    [
        ("rollups/instrument/price_stats@v2", Grain.SESSION),
        ("chains/option_quotes", Grain.SESSION),
        ("results/rule_screen", Grain.SESSION),
        ("bars/1d", Grain.SESSION),
        ("verification/ibkr", Grain.SESSION),
        ("live/option_quotes", Grain.SESSION),
        ("instruments/reference", Grain.SNAPSHOT),
        ("instruments/company", Grain.SNAPSHOT),
        ("universe", Grain.SNAPSHOT),
        ("instruments/id_map", Grain.SNAPSHOT),
        ("instruments/ibkr_contracts", Grain.SNAPSHOT),
        ("events/earnings", Grain.EVENT),
        ("holdings/etf", Grain.ISSUER_DATED),
        ("instruments/description", Grain.INCREMENTAL),
    ],
)
def test_every_table_grain_of_the_spec(table: str, grain: Grain) -> None:
    assert grain_of(table) is grain


@pytest.mark.parametrize(
    "table", ["rates/treasury", "bars/1d_extra", "universe/x", "rollups/daily/x"]
)
def test_a_table_without_a_declared_grain_is_refused(table: str) -> None:
    with pytest.raises(ValueError, match="no read grain declared"):
        grain_of(table)


def test_an_incomplete_newer_session_resolves_to_the_previous_complete_one() -> None:
    """Owner decision 2026-10-10: bars landed for D3 but its workflow FAILED: pages serve D2."""
    writer, reader = store()
    for day in (D1, D2, D3):
        write_bar(writer, day)
    nightly(reader, D1, RunStatus.COMPLETE)
    nightly(reader, D2, RunStatus.COMPLETE)
    nightly(reader, D3, RunStatus.FAILED)
    session = resolve_session(reader, None, EXPECTED)
    assert (session.date, session.is_latest, session.complete) == (D2, True, True)
    assert session.latest_with_bars == D3
    assert session.newer == NewerSession(D3, NewerState.FAILED_RETRYING, UnavailableKind.SYSTEM)


def test_a_requested_date_is_unchanged_by_completeness() -> None:
    writer, reader = store()
    for day in (D2, D3):
        write_bar(writer, day)
    nightly(reader, D2, RunStatus.COMPLETE)
    nightly(reader, D3, RunStatus.FAILED)
    asked = resolve_session(reader, D3, EXPECTED)
    assert (asked.date, asked.requested, asked.is_latest) == (D3, D3, False)
    assert (asked.complete, asked.newer) == (False, None)  # no notice on an explicit date
    assert resolve_session(reader, D2, EXPECTED).complete is True


def test_a_session_still_running_or_without_a_record_is_in_progress() -> None:
    writer, reader = store()
    for day in (D1, D2, D3):
        write_bar(writer, day)
    nightly(reader, D1, RunStatus.COMPLETE)
    assert resolve_session(reader, None, EXPECTED).newer == NewerSession(D3, NewerState.IN_PROGRESS)
    nightly(reader, D2, RunStatus.RUNNING)
    nightly(reader, D3, RunStatus.WAITING)
    found = resolve_session(reader, None, EXPECTED)
    assert (found.date, found.newer) == (D1, NewerSession(D3, NewerState.IN_PROGRESS))


def test_a_retry_that_succeeds_flips_it() -> None:
    writer, reader = store()
    for day in (D1, D2):
        write_bar(writer, day)
    nightly(reader, D1, RunStatus.COMPLETE)
    nightly(reader, D2, RunStatus.FAILED, hour=6)
    assert resolve_session(reader, None, EXPECTED).date == D1
    nightly(reader, D2, RunStatus.COMPLETE, hour=7)  # the hourly retry succeeded
    flipped = resolve_session(reader, None, EXPECTED)
    assert (flipped.date, flipped.newer) == (D2, None)


def test_a_complete_record_without_bars_is_not_complete() -> None:
    writer, reader = store()
    write_bar(writer, D1)
    nightly(reader, D1, RunStatus.COMPLETE)
    nightly(reader, D2, RunStatus.COMPLETE)  # no bars/1d for D2
    nightly(reader, D3, RunStatus.FAILED)
    write_bar(writer, D3)
    found = resolve_session(reader, None, EXPECTED)
    failing = NewerSession(D3, NewerState.FAILED_RETRYING, UnavailableKind.SYSTEM)
    assert (found.date, found.newer) == (D1, failing)


def test_no_complete_session_keeps_the_latest_bars_and_flags_it() -> None:
    writer, reader = store()
    for day in (D1, D2):
        write_bar(writer, day)
    nightly(reader, D2, RunStatus.FAILED)
    found = resolve_session(reader, None, EXPECTED)
    assert (found.date, found.is_latest, found.complete, found.newer) == (D2, True, False, None)


def test_a_partial_record_counts_as_done_as_the_ingestion_planner_does() -> None:
    """One rule (``storage.runs.done_sessions``): PARTIAL, written before ADR 0039, is done, and
    any done record counts even when a later attempt of the session is not."""
    writer, reader = store()
    for day in (D1, D2, D3):
        write_bar(writer, day)
    nightly(reader, D1, RunStatus.PARTIAL)
    nightly(reader, D2, RunStatus.COMPLETE, hour=6)
    nightly(reader, D2, RunStatus.FAILED, hour=9)  # a later rerun failing does not undo it
    nightly(reader, D3, RunStatus.WAITING)
    found = resolve_session(reader, None, EXPECTED)
    assert (found.date, found.complete) == (D2, True)
    assert resolve_session(reader, D1, EXPECTED).complete is True


def test_an_explicit_older_complete_session_is_complete() -> None:
    writer, reader = store()
    for day in (D1, D2, D3):
        write_bar(writer, day)
        nightly(reader, day, RunStatus.COMPLETE if day != D3 else RunStatus.FAILED)
    assert resolve_session(reader, D1, EXPECTED).complete is True  # not the default, still done
    assert resolve_session(reader, D3, EXPECTED).complete is False


def test_the_default_session_is_one_function_for_reads_and_runs() -> None:
    writer, reader = store()
    assert default_session(reader) is None
    for day in (D1, D2):
        write_bar(writer, day)
    assert default_session(reader) == D2  # no run records: the latest bars
    nightly(reader, D1, RunStatus.COMPLETE)
    nightly(reader, D2, RunStatus.FAILED)
    assert default_session(reader) == D1 == resolve_session(reader, None, EXPECTED).date
