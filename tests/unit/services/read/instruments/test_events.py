"""An instrument's events by event date (event grain): every ``events/*`` table, whatever
partition stored the row, in an explicit window, sorted, stamps dropped; one read for many."""

from datetime import date

import pandas as pd

from algotrade.services.read.instruments.events import event_tables, load_events
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_dividends, write_split
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with


def _events(writer: StoreWriter) -> None:
    write_split(writer, "EQ:AAA", date(2020, 8, 31), 4.0, D0)  # learned long after the fact
    paid = [("EQ:AAA", date(2026, 9, 1), 0.25, "CD"), ("EQ:ETFX", date(2026, 6, 1), 0.5, "CD")]
    write_dividends(writer, paid, D1)


def test_every_event_of_the_instruments_by_event_date() -> None:
    ctx = context(store_with(_events))
    assert event_tables(ctx) == ("events/dividend", "events/split")
    found = load_events(ctx, ["EQ:AAA", "EQ:ETFX", "EQ:ZZZ"], None, None)
    aaa = found["EQ:AAA"]
    assert [(e.kind, e.table, e.date) for e in aaa] == [
        ("split", "events/split", date(2020, 8, 31)),
        ("dividend", "events/dividend", date(2026, 9, 1)),
    ]
    assert aaa[0].values == {"ratio": 4.0}  # no instrument id, ts or point-in-time stamps
    assert aaa[0].ts == pd.Timestamp(2020, 8, 31, tz="UTC").to_pydatetime()
    assert [e.date for e in found["EQ:ETFX"]] == [date(2026, 6, 1)]
    assert found["EQ:ZZZ"] == ()


def test_the_window_is_by_event_date_not_the_stored_partition() -> None:
    ctx = context(store_with(_events))
    recent = load_events(ctx, ["EQ:AAA"], date(2026, 1, 1), None)["EQ:AAA"]
    assert [e.kind for e in recent] == ["dividend"]
    old = load_events(ctx, ["EQ:AAA"], None, date(2021, 1, 1))["EQ:AAA"]
    assert [e.kind for e in old] == ["split"]


def test_no_event_tables_is_no_events(ctx: object) -> None:
    empty = context(store_with())
    assert event_tables(empty) == ()
    assert load_events(empty, ["EQ:AAA"], None, None) == {"EQ:AAA": ()}
