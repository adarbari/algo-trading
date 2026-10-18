"""The ``events/filing_text`` read rule (edge build D10): rows known on a session (the stored
``known_from`` floored by the acceptance session recomputed from ``ts``), the latest known version
per item (``known_from``, then ``parser_version``), null items equal, the null-item row of a filing
dropped when it has an item row, ``as_of`` pins, and every column the callers name."""

from datetime import date, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.filing_text.reading import (
    COLUMNS,
    effective_known_from,
    filing_text,
    latest_filing_versions,
    stored_filing_text,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped

TABLE = "events/filing_text"
ACCEPTED = pd.Timestamp("2026-02-10T21:30:00Z")  # 16:30 New York: public from 2026-02-11
FIRST = date(2026, 2, 11)
REVISED = date(2026, 10, 5)


def row(
    item: str | None, text: str | None, version: int = 1, known: date = FIRST, **kw: object
) -> dict[str, object]:
    return {
        "instrument_id": "EQ:AAA", "ts": ACCEPTED, "known_from": known, "cik": "0000000001",
        "form": "10-K", "accession": "A1", "filing_date": date(2026, 2, 10), "report_date": None,
        "item": item, "parser_version": version, "text": text, "char_count": len(text or ""),
        "quality": "OK" if text else "NO_ITEMS", "reason": None, "method": "item_headers", **kw,
    }  # fmt: skip


def reader(*runs: tuple[str, list[dict[str, object]], object]) -> StoreReader:
    writer = StoreWriter(MemoryBackend())
    for name, rows, at in runs:
        frame = stamped(rows, FIRST, name, at, "sec_edgar")  # type: ignore[arg-type]
        writer.write_table(TABLE, FIRST, name, frame)
    return StoreReader(writer._backend)


def test_a_row_is_never_read_before_its_acceptance_session_whatever_it_is_stamped() -> None:
    early = row("1A", "text", known=date(2026, 2, 10))  # a stamp from the old filing-date rule
    store = reader(("r1", [early], T0))
    assert filing_text(store, ["EQ:AAA"], date(2026, 2, 10)).empty
    found = filing_text(store, ["EQ:AAA"], FIRST)
    assert found["text"].tolist() == ["text"] and found["known_from"].iloc[0] == FIRST
    frame = pd.DataFrame([early])
    assert effective_known_from(frame).iloc[0] == pd.Timestamp(FIRST)


def test_the_latest_known_version_wins_and_a_later_one_is_unseen_until_its_stamp() -> None:
    store = reader(
        ("r1", [row("1A", "old")], T0),
        ("r2", [row("1A", "new", version=2, known=REVISED)], T0 + timedelta(days=1)),
    )
    assert filing_text(store, ["EQ:AAA"], REVISED - timedelta(days=1))["text"].tolist() == ["old"]
    assert filing_text(store, ["EQ:AAA"], REVISED)["text"].tolist() == ["new"]


def test_a_version_tie_on_known_from_goes_to_the_higher_parser_version() -> None:
    store = reader(("r1", [row("1A", "same", version=1), row("1A", "same", version=2)], T0))
    found = filing_text(store, ["EQ:AAA"], REVISED)
    assert found["parser_version"].tolist() == [2] and len(found) == 1


def test_the_null_item_row_is_dropped_when_the_filing_has_an_item_row_and_kept_alone() -> None:
    alone = reader(("r1", [row(None, None)], T0))
    assert filing_text(alone, ["EQ:AAA"], FIRST)["quality"].tolist() == ["NO_ITEMS"]
    both = reader(
        ("r1", [row(None, None)], T0),
        ("r2", [row("1A", "found", version=2, known=REVISED)], T0 + timedelta(days=1)),
    )
    assert filing_text(both, ["EQ:AAA"], FIRST)["quality"].tolist() == ["NO_ITEMS"]  # then
    assert filing_text(both, ["EQ:AAA"], REVISED)["item"].tolist() == ["1A"]  # now


def test_items_forms_since_and_as_of_narrow_the_read() -> None:
    other = row("7", "mda", accession="A2", form="10-Q", ts=pd.Timestamp("2026-05-01T14:00:00Z"),
                known_from=date(2026, 5, 1))  # fmt: skip
    store = reader(("r1", [row("1A", "risk"), row("7", "mda"), other], T0))
    on = date(2026, 10, 2)
    assert sorted(filing_text(store, ["EQ:AAA"], on)["accession"]) == ["A1", "A1", "A2"]
    assert filing_text(store, ["EQ:AAA"], on, items=["1A"])["item"].tolist() == ["1A"]
    assert filing_text(store, ["EQ:AAA"], on, forms=["10-Q"])["accession"].tolist() == ["A2"]
    assert filing_text(store, ["EQ:AAA"], on, as_of=T0 - timedelta(days=1)).empty
    assert filing_text(store, ["EQ:ZZZ"], on).empty


def test_an_empty_store_gives_the_columns_and_with_text_false_leaves_the_text_out() -> None:
    empty = StoreReader(MemoryBackend())
    assert tuple(filing_text(empty, ["EQ:AAA"], FIRST).columns) == COLUMNS
    assert "text" not in filing_text(empty, ["EQ:AAA"], FIRST, with_text=False).columns
    store = reader(("r1", [row("1A", "risk")], T0))
    assert "text" not in filing_text(store, ["EQ:AAA"], FIRST, with_text=False).columns
    assert stored_filing_text(empty, ["EQ:AAA"]).empty


def test_latest_filing_versions_groups_null_items_together() -> None:
    frame = pd.DataFrame([row(None, None, version=1), row(None, None, version=2)])
    frame["knowledge_ts"] = pd.Timestamp(T0)
    assert latest_filing_versions(frame)["parser_version"].tolist() == [2]


def test_since_bounds_the_acceptance_session_partitions_read() -> None:
    writer = StoreWriter(MemoryBackend())
    later = date(2026, 5, 1)
    for day, rows in (
        (FIRST, [row("1A", "risk")]),
        (later, [row("7", "mda", accession="A2", known=later)]),
    ):
        frame = stamped(rows, day, f"r{day}", T0, "sec_edgar")
        writer.write_table(TABLE, day, f"r{day}", frame)
    store = StoreReader(writer._backend)
    on = date(2026, 10, 2)
    assert filing_text(store, ["EQ:AAA"], on, since=date(2026, 4, 1))["accession"].tolist() == [
        "A2"
    ]
    assert filing_text(store, ["EQ:AAA"], later - timedelta(days=1))["accession"].tolist() == ["A1"]
