"""``universe_basis_counts`` on a synthetic store (ADR 0087 decision 6): which listings qualify in
the window, which have no id, the delistings with bars and an event, the unknown ones and the
events of a snapshot written after ``as_of`` that are not seen."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data.listings.basis import universe_basis_counts
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

START, END = date(2015, 1, 5), date(2015, 12, 31)
AS_OF = datetime(2026, 11, 3, 12, tzinfo=UTC)
DAY = date(2026, 10, 5)


def _listing(iid: str | None, ticker: str, exchange: str, end: str | None, **extra: object) -> dict:  # type: ignore[type-arg]
    return {
        "instrument_id": iid, "ticker": ticker, "exchange": exchange, "asset_type": "Stock",
        "security_type": "COMMON_STOCK", "start_date": date(2000, 1, 3),
        "end_date": None if end is None else date.fromisoformat(end), "source": "tiingo",
        "id_source": "symbol_history", "ts": pd.Timestamp(DAY, tz="UTC"), **extra,
    }  # fmt: skip


def _store(
    events: list[dict] | None = None, written: date = DAY, merged: bool = True
) -> StoreReader:  # type: ignore[type-arg]
    rows = [
        _listing("EQ:A", "AAA", "NASDAQ", None),  # alive, qualifies
        _listing("EQ:B", "BBB", "NYSE", "2015-06-01"),  # S&P member, delisted in the window
        _listing(None, "CCC", "NASDAQ", None, id_source=None),  # no id
        _listing("EQ:D", "DDD", "NASDAQ", "2015-09-01", security_type=None),  # null type, no event
        _listing("EQ:E", "EEE", "NYSE", None),  # neither NASDAQ nor a member: not qualifying
        _listing("EQ:F", "FFF", "NYSE", None, asset_type="ETF"),  # an ETF qualifies
        _listing("EQ:G", "GGG", "NASDAQ", "2014-06-02"),  # ended before the window
    ]
    if not merged:
        rows = [{k: v for k, v in r.items() if k != "id_source"} for r in rows]
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    writer.write_table("instruments/listing_history", DAY, "r", stamped(rows, DAY, "r"))
    members = [{"index_name": "SP500", "ticker": "BBB", "start_date": date(2000, 1, 3),
                "end_date": None, "ts": pd.Timestamp(DAY, tz="UTC")}]  # fmt: skip
    writer.write_table("instruments/index_membership", DAY, "m", stamped(members, DAY, "m"))
    if events is not None:
        known = datetime(written.year, written.month, written.day, 9, tzinfo=UTC)
        frame = stamped(events, written, "e", knowledge=known)
        writer.write_table("events/delisting", written, "e", frame)
    return StoreReader(backend)


def _event(iid: str, day: date, **over: object) -> dict:  # type: ignore[type-arg]
    return {
        "instrument_id": iid, "ts": pd.Timestamp(day, tz="UTC"), "known_from": day,
        "last_session": day, "last_close": 3.0, "reason": "ACQUIRED",
        "terminal_basis": "ZERO_ACQUIRED", "delisting_return": 0.0, **over,
    }  # fmt: skip


def test_the_counts_of_a_window() -> None:
    reader = _store([_event("EQ:B", date(2015, 6, 1))])
    c = universe_basis_counts(reader, START, END, AS_OF)
    assert c.listing_snapshot == DAY and c.delisting_snapshot == DAY and c.merged
    assert (c.listings, c.no_id) == (5, 1)  # A B C D F; C has no id
    assert (c.stocks, c.null_type) == (3, 1)  # the named stocks A B D; D has no type
    assert (c.delisted, c.with_bars, c.unknown) == (2, 1, 1)  # D has no event: unknown
    assert c.by_reason == {"ACQUIRED": 1} and c.by_basis == {"ZERO_ACQUIRED": 1}


def test_a_zero_unknown_event_and_a_missing_one_are_both_unknown() -> None:
    reader = _store(
        [_event("EQ:B", date(2015, 6, 1), terminal_basis="ZERO_UNKNOWN", reason="UNKNOWN")]
    )
    c = universe_basis_counts(reader, START, END, AS_OF)
    assert (c.delisted, c.with_bars, c.unknown) == (2, 1, 2)  # D has no row; B's basis is unknown
    assert c.by_basis == {"ZERO_UNKNOWN": 1} and c.by_reason == {"UNKNOWN": 1}


def test_no_events_snapshot_makes_every_delisting_unknown() -> None:
    c = universe_basis_counts(_store(None), START, END, AS_OF)
    assert c.delisting_snapshot is None
    assert (c.delisted, c.with_bars, c.unknown) == (2, 0, 2)
    assert c.by_reason == {} and c.by_basis == {}


def test_a_snapshot_written_after_as_of_is_not_seen() -> None:
    late = _store([_event("EQ:B", date(2015, 6, 1))], written=date(2026, 11, 20))
    c = universe_basis_counts(late, START, END, AS_OF)  # a replay before the write
    assert c.delisting_snapshot is None and c.unknown == 2


def test_an_unmerged_snapshot_is_said_so() -> None:
    c = universe_basis_counts(_store(None, merged=False), START, END, AS_OF)
    assert not c.merged


def test_a_window_before_the_listings_counts_none() -> None:
    c = universe_basis_counts(_store(None), date(1990, 1, 2), date(1990, 12, 31), AS_OF)
    assert (c.listings, c.delisted) == (0, 0)
