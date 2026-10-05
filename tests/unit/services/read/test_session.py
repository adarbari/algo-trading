"""One resolved session per read (ADR 0036): which date a read serves, what is stored for it,
which reference snapshot identity comes from, and how each table grain is read."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.services.read.session import (
    EXPECTED_TABLES,
    Grain,
    NotFoundError,
    Session,
    expected_tables,
    grain_of,
    latest_session,
    resolve_session,
)
from algotrade.storage.backends.memory import MemoryBackend
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
    assert resolve_session(reader, D2, EXPECTED) == Session(
        date=D2, requested=D2, is_latest=False, latest_with_bars=None,
        reference_snapshot=None, pre_snapshot=False, present=(), missing=EXPECTED,
    )  # fmt: skip


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


def test_expected_tables_skip_families_and_other_grains(tmp_path: Path) -> None:
    ownership = tmp_path / "ownership.toml"
    ownership.write_text(
        "\n".join(
            f'[[table]]\nname = "{name}"\nowner = "x.py"\n'
            for name in ("results/*", "results/a", "chains/status", "live/option_quotes",
                         "verification/ibkr", "instruments/reference", "rollups/instrument/x@v1")
        )
    )  # fmt: skip
    assert expected_tables(ownership) == (
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
