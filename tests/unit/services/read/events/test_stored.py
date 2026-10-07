"""An instrument's events by event date (event grain): every ``events/*`` table, whatever
partition stored the row, among the rows known on or before the session (``known_from``, ADR
0050), in an explicit window, sorted, stamps dropped; one read for many."""

from datetime import date, timedelta

import pandas as pd

from algotrade.services.read.events.stored import event_tables, load_events
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_dividends, write_split
from tests.helpers.stored_frames import T0, stamped
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


def test_facts_of_record_are_read_without_a_knowledge_bound() -> None:
    """Splits and dividends adjust bars at read time (ADR 0016): a past session shows the ones
    stored after it, at their latest version, as its adjusted bars use them."""

    def revisions(writer: StoreWriter) -> None:
        write_dividends(writer, [("EQ:AAA", date(2026, 9, 1), 0.25, "CD")], D0)
        row = {
            "instrument_id": "EQ:AAA",
            "symbol": "AAA",
            "ts": pd.Timestamp(2026, 9, 1, tz="UTC"),
            "cash_amount": 0.30,
            "distribution_type": "CD",
        }
        later = T0 + timedelta(days=1)
        writer.write_table("events/dividend", D1, "rev", stamped([row], D1, "rev", later))

    reader = store_with(revisions)
    for day in (D0, D1):
        found = load_events(context(reader, day), ["EQ:AAA"], None, None)["EQ:AAA"]
        assert [e.values["cash_amount"] for e in found] == [0.30]


def test_a_past_session_sees_only_the_earnings_known_by_then() -> None:
    def calendars(writer: StoreWriter) -> None:
        for stored, report in ((D0, date(2026, 10, 20)), (D1, date(2026, 10, 27))):
            row = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(report, tz="UTC")}
            run = f"e{stored}"
            frame = stamped([{**row, "known_from": stored}], stored, run)
            writer.write_table("events/earnings", stored, run, frame)

    reader = store_with(calendars)
    past = load_events(context(reader, D0), ["EQ:AAA"], None, None)["EQ:AAA"]
    assert [e.date for e in past] == [date(2026, 10, 20)]  # the 10-27 row was stored on D1
    now = load_events(context(reader, D1), ["EQ:AAA"], None, None)["EQ:AAA"]
    assert [e.date for e in now] == [date(2026, 10, 20), date(2026, 10, 27)]


def test_a_backfilled_report_is_known_from_its_report_date() -> None:
    def backfill(writer: StoreWriter) -> None:
        row = {
            "instrument_id": "EQ:AAA",
            "ts": pd.Timestamp(D0, tz="UTC"),
            "known_from": D0,
            "eps_reported": 1.5,
        }
        writer.write_table("events/earnings", D1, "bf", stamped([row], D1, "bf"))

    found = load_events(context(store_with(backfill), D0), ["EQ:AAA"], None, None)["EQ:AAA"]
    assert [(e.kind, e.date) for e in found] == [("earnings", D0)]  # stored on D1, known on D0
    assert found[0].values["known_from"] == D0.isoformat()  # disclosed with the row (JSON)


def test_no_event_tables_is_no_events() -> None:
    empty = context(store_with())
    assert event_tables(empty) == ()
    assert load_events(empty, ["EQ:AAA"], None, None) == {"EQ:AAA": ()}
