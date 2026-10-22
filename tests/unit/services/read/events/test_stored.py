"""An instrument's events by event date (event grain): every ``events/*`` table, whatever
partition stored the row, among the rows known on or before the session (``known_from``, ADR
0050), in an explicit window, sorted, stamps dropped; one read for many."""

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.data.events import ALL_TIME, read_events
from algotrade.services.read.events.stored import (
    TIMELINE_KINDS,
    event_tables,
    load_events,
    warm_event_copies,
)
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryTables
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_dividends, write_rows, write_split
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


def _with_filing_text(writer: StoreWriter) -> None:
    _events(writer)
    row = {
        "instrument_id": None,
        "ts": pd.Timestamp(D0, tz="UTC"),
        "cik": "1",
        "form": "10-K",
        "accession": "a-1",
        "filing_date": D0,
        "char_count": 10,
        "item": "1A",
        "quality": "OK",
        "method": "parse",
        "parser_version": 1,
        "text": "x" * 10,
    }
    run = "ft"
    writer.write_table("events/filing_text", D0, run, stamped([{**row, "known_from": D0}], D0, run))


def _spy_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    reads: list[str] = []
    real = MemoryTables.read_range

    def spy(self: MemoryTables, table: str, *args: Any, **kwargs: Any) -> Any:
        reads.append(table)
        return real(self, table, *args, **kwargs)

    monkeypatch.setattr(MemoryTables, "read_range", spy)
    return reads


def test_filing_text_partitions_are_never_opened_for_an_instrument_events_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = context(store_with(_with_filing_text))
    reads = _spy_reads(monkeypatch)
    found = load_events(ctx, ["EQ:AAA"], None, None)["EQ:AAA"]
    assert "events/filing_text" not in reads and "events/split" in reads
    assert "events/filing_text" not in event_tables(ctx)
    # equivalence: the same events as a store with no filing_text partition
    plain = load_events(context(store_with(_events)), ["EQ:AAA"], None, None)["EQ:AAA"]
    assert found == plain


def test_a_repeated_events_read_reads_nothing_and_a_new_instrument_reads_only_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = context(store_with(_events))
    first = load_events(ctx, ["EQ:AAA"], None, None)
    reads = _spy_reads(monkeypatch)
    assert load_events(ctx, ["EQ:AAA"], None, None) == first
    assert reads == []  # held
    both = load_events(ctx, ["EQ:AAA", "EQ:ETFX"], None, None)
    assert both["EQ:AAA"] == first["EQ:AAA"] and len(both["EQ:ETFX"]) == 1
    assert reads and reads.count("events/split") == 1  # one read for the instrument not held
    other_window = load_events(ctx, ["EQ:AAA"], date(2026, 1, 1), None)["EQ:AAA"]
    assert [e.kind for e in other_window] == ["dividend"]  # the window is part of the key


def test_warming_the_event_copies_leaves_the_first_events_read_no_index_digest_to_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validating a copy digests each stored day's ``_runs.json`` once per process (8,400 files
    for ``events/fund_nav``, 1 to 2 s cold): the API's warmer pays it, the first read does not."""
    table = "events/demo"
    seed = LocalBackend(tmp_path / "data")
    for n in range(30):
        day = date(2025, 12, 20) + timedelta(days=n)
        rows = pd.DataFrame([{"instrument_id": "EQ:A", "ts": pd.Timestamp(day, tz="UTC"), "a": n}])
        seed.tables.write(table, day, "r1", stamped(rows.to_dict("records"), day, "r1"))
    assert seed.tables.build_history(table, [2025, 2026]) == [2025, 2026]
    backend = LocalBackend(tmp_path / "data")  # a fresh process: no digest held
    configs = MemoryConfigStore(
        {("site", "settings", "nightly"): {"history_copy": {"event_tables": [table]}}}
    )
    ctx: Any = SimpleNamespace(reader=StoreReader(backend), configs=configs)
    digests: list[Path] = []
    real = Path.read_bytes

    def spy(self: Path) -> bytes:
        digests.append(self) if self.name == "_runs.json" else None
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    assert warm_event_copies(ctx) == (table,)
    assert len(digests) >= 30  # one per stored day
    digests.clear()
    frame = read_events(ctx.reader, table, *ALL_TIME, ["EQ:A"]).frame
    assert len(frame) == 30 and digests == []


def _every_kind(writer: StoreWriter) -> None:
    _events(writer)
    write_rows(
        writer,
        "events/short_interest",
        D0,
        [
            {
                "instrument_id": "EQ:AAA",
                "ts": pd.Timestamp(D0, tz="UTC"),
                "known_from": D0,
                "published": D0,
                "short_position": 10,
            }
        ],
    )
    write_rows(
        writer,
        "events/short_volume",
        D0,
        [
            {
                "instrument_id": "EQ:AAA",
                "ts": pd.Timestamp(D0, tz="UTC"),
                "known_from": D0,
                "short_volume": 5,
                "total_volume": 50,
            }
        ],
    )


def test_the_timeline_kinds_return_exactly_the_calendar_rows_of_every_kind_read() -> None:
    ctx = context(store_with(_every_kind))
    everything = load_events(ctx, ["EQ:AAA"], None, None)["EQ:AAA"]
    assert {e.kind for e in everything} == {"split", "dividend", "short_interest", "short_volume"}
    page = load_events(ctx, ["EQ:AAA"], None, None, TIMELINE_KINDS)["EQ:AAA"]
    # same rows, same order, same known_from rule as the full read restricted to the kinds
    assert page == tuple(e for e in everything if e.kind in TIMELINE_KINDS)
    assert [e.kind for e in page] == ["split", "dividend"]


def test_another_kind_is_still_readable_when_asked() -> None:
    ctx = context(store_with(_every_kind))
    found = load_events(ctx, ["EQ:AAA"], None, None, ("short_interest",))["EQ:AAA"]
    assert [(e.kind, e.values["short_position"]) for e in found] == [("short_interest", 10)]


def test_the_default_timeline_read_opens_no_table_of_another_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Insider, short, filing and NAV partitions and copies are not opened for the page."""
    ctx = context(store_with(_every_kind))
    reads = _spy_reads(monkeypatch)
    load_events(ctx, ["EQ:AAA"], None, None, TIMELINE_KINDS)
    assert set(reads) == {"events/split", "events/dividend"}
    assert event_tables(ctx, TIMELINE_KINDS) == ("events/dividend", "events/split")
    reads.clear()
    load_events(ctx, ["EQ:AAA"], None, None, ("short_interest",))  # its own held entry
    assert set(reads) == {"events/short_interest"}
