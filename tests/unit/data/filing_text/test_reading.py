"""The ``events/filing_text`` read rule (edge builds D10, D10b): rows known on a session (the stored
``known_from`` floored by the acceptance session recomputed from ``ts``), the latest known version
per item (``known_from``, then ``parser_version``), null items equal, the null-item row of a filing
dropped when it has an item row, ``as_of`` pins, and every column the callers name; a filing read
before and after its id version (NULL, then the id, one filing), the scan of every filer
(``ids=None``, NULL ids included), the ``ciks`` filter, and ids mapped through the company
snapshot as of the session."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
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


SNAPSHOT = date(2026, 1, 1)  # the first company snapshot, before every filing here


def company(*pairs: tuple[str, str]) -> list[dict[str, object]]:
    return [
        {"instrument_id": i, "symbol": i[3:], "cik": cik, "name": i, "sic": "1", "sector": "x",
         "fetched_on": SNAPSHOT}
        for i, cik in pairs
    ]  # fmt: skip


def reader(
    *runs: tuple[str, list[dict[str, object]], object],
    companies: tuple[tuple[str, str], ...] = (("EQ:AAA", "1"),),
) -> StoreReader:
    writer = StoreWriter(MemoryBackend())
    for name, rows, at in runs:
        frame = stamped(rows, FIRST, name, at, "sec_edgar")  # type: ignore[arg-type]
        writer.write_table(TABLE, FIRST, name, frame)
    if companies:
        writer.write_table(
            "instruments/company", SNAPSHOT, "co", stamped(company(*companies), SNAPSHOT, "co")
        )
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
    assert filing_text(store, None, on, as_of=T0 - timedelta(days=1)).empty  # nothing known yet
    assert filing_text(store, ["EQ:ZZZ"], on).empty


def test_an_empty_store_gives_the_columns_and_with_text_false_leaves_the_text_out() -> None:
    empty = StoreReader(MemoryBackend())
    assert tuple(filing_text(empty, None, FIRST).columns) == COLUMNS
    assert "text" not in filing_text(empty, None, FIRST, with_text=False).columns
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
    writer.write_table(
        "instruments/company", SNAPSHOT, "co", stamped(company(("EQ:AAA", "1")), SNAPSHOT, "co")
    )
    store = StoreReader(writer._backend)
    on = date(2026, 10, 2)
    assert filing_text(store, ["EQ:AAA"], on, since=date(2026, 4, 1))["accession"].tolist() == [
        "A2"
    ]
    assert filing_text(store, ["EQ:AAA"], later - timedelta(days=1))["accession"].tolist() == ["A1"]


# ----------------------------------------------- filer-first (D10b): ids mapped at the session

OTHER = pd.Timestamp("2026-03-03T15:00:00Z")


def stored(item: str | None, text: str | None, **kw: object) -> dict[str, object]:
    """A row as the producer stores it: no instrument id."""
    return row(item, text, instrument_id=None, **kw)


def two_filers(companies: tuple[tuple[str, str], ...] = (("EQ:AAA", "1"),)) -> StoreReader:
    """Filer 1's filing A1 (items 1A and 7) and a delisted filer 2's A2 (accepted on 03-03), no
    id stored in any row; ``companies`` is the snapshot (filer 2 is in none of it)."""
    gone = {"cik": "0000000002", "accession": "A2", "ts": OTHER, "known_from": date(2026, 3, 3)}
    writer = StoreWriter(MemoryBackend())
    parts = [
        (FIRST, "r1", [stored("1A", "risk"), stored("7", "mda")]),
        (date(2026, 3, 3), "r1b", [stored("1A", "gone", **gone)]),
    ]
    for day, name, rows_ in parts:
        writer.write_table(TABLE, day, name, stamped(rows_, day, name, T0, "sec_edgar"))
    if companies:
        frame = stamped(company(*companies), SNAPSHOT, "co")
        writer.write_table("instruments/company", SNAPSHOT, "co", frame)
    return StoreReader(writer._backend)


ON = date(2026, 10, 2)


def test_ids_are_mapped_through_the_company_snapshot_whatever_the_stored_id() -> None:
    store = two_filers()
    found = filing_text(store, ["EQ:AAA"], ON)
    assert sorted(found["item"]) == ["1A", "7"] and found["instrument_id"].eq("EQ:AAA").all()
    assert found["accession"].eq("A1").all() and len(found) == 2  # one row an item
    assert filing_text(store, ["EQ:ZZZ"], ON).empty
    shared = two_filers((("EQ:AAA", "1"), ("EQ:AAB", "1")))  # two share classes of one filer
    both = filing_text(shared, ["EQ:AAA", "EQ:AAB"], ON)
    assert sorted(set(both["instrument_id"])) == ["EQ:AAA", "EQ:AAB"] and len(both) == 4


def test_a_read_before_the_first_snapshot_uses_the_earliest_and_discloses_it() -> None:
    store = two_filers()
    early = filing_text(store, ["EQ:AAA"], date(2025, 12, 1), since=date(2025, 1, 1))
    assert early.empty  # nothing was filed yet, the snapshot used is still disclosed
    assert early.attrs["pre_snapshot"] is True and early.attrs["company_snapshot"] == SNAPSHOT
    late = reader(("r1", [stored("1A", "risk", known=date(2026, 1, 20))], T0))
    cold = StoreWriter(late._backend)  # a snapshot taken AFTER the filing was known
    cold.write_table(
        "instruments/company",
        date(2026, 6, 1),
        "co2",
        stamped(company(("EQ:AAB", "1")), SNAPSHOT, "co2"),
    )
    seen = filing_text(late, ["EQ:AAA"], date(2026, 2, 12))  # the 2026-01-01 snapshot stands
    assert seen["instrument_id"].tolist() == ["EQ:AAA"] and seen.attrs["pre_snapshot"] is False
    after = filing_text(late, ["EQ:AAB"], ON)  # the later one holds the later class
    assert after["instrument_id"].tolist() == ["EQ:AAB"]


def test_a_read_by_ids_with_no_company_snapshot_raises_but_the_scan_reads_null_ids() -> None:
    store = two_filers(())
    with pytest.raises(MissingDataError):
        filing_text(store, ["EQ:AAA"], ON)
    scan = filing_text(store, None, ON)
    assert len(scan) == 3 and scan["instrument_id"].isna().all()
    assert scan.attrs["company_snapshot"] is None


def test_ids_none_scans_every_filer_unmapped_ciks_have_a_null_id_and_ciks_filters() -> None:
    store = two_filers()
    scan = filing_text(store, None, ON)
    assert sorted(scan["cik"].unique()) == ["0000000001", "0000000002"]
    assert scan.loc[scan["cik"] == "0000000001", "instrument_id"].eq("EQ:AAA").all()
    assert scan.loc[scan["cik"] == "0000000002", "instrument_id"].isna().all()  # delisted
    assert len(scan) == 3 and tuple(scan.columns) == COLUMNS
    one = filing_text(store, None, ON, ciks=["0000000002"])
    assert one["text"].tolist() == ["gone"]
    assert filing_text(store, None, ON, ciks=["2"])["text"].tolist() == ["gone"]  # as vendors write
    assert filing_text(store, None, ON, ciks=["0000000003"]).empty


def test_with_text_false_reads_no_text_column() -> None:
    store = two_filers()
    light = filing_text(store, None, ON, with_text=False)
    assert "text" not in light.columns and len(light) == 3


def test_the_scan_by_accession_window_bounds_what_is_found() -> None:
    store = two_filers()
    window = filing_text(store, None, ON, since=date(2026, 3, 1), forms=["10-K"])
    assert window["accession"].tolist() == ["A2"]  # since floors the acceptance session
    assert filing_text(store, None, ON, forms=["10-Q"]).empty
    early = filing_text(store, None, date(2026, 3, 2))
    assert early["accession"].tolist() == ["A1", "A1"]  # A2 is accepted on the 3rd


def test_the_text_of_a_chosen_version_is_read_from_its_own_partition() -> None:
    writer = StoreWriter(MemoryBackend())
    later = date(2026, 5, 1)
    second = stored("1A", "risk two", accession="A2", known=later)
    second["ts"] = pd.Timestamp("2026-05-01T14:00:00Z")
    for day, rows_ in ((FIRST, [stored("1A", "risk one")]), (later, [second])):
        writer.write_table(TABLE, day, f"r{day}", stamped(rows_, day, f"r{day}", T0, "sec_edgar"))
    found = filing_text(StoreReader(writer._backend), None, ON)
    assert found.sort_values("accession")["text"].tolist() == ["risk one", "risk two"]


def test_stored_filing_text_scans_every_filer_and_filters_by_cik() -> None:
    store = two_filers()
    everything = stored_filing_text(store, None, ("cik", "item"))
    assert len(everything) == 3 and set(everything["cik"]) == {"0000000001", "0000000002"}
    one = stored_filing_text(store, None, ("item",), ciks=["0000000002"])
    assert one["cik"].tolist() == ["0000000002"]
