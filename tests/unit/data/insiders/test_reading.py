"""``read_insider_transactions``: the rows known on or before the session, each line's latest
version (a restated line shows its old version until its own ``known_from``), and without the
originals a known 4/A replaced."""

from datetime import date

import pandas as pd

from algotrade.data.insiders.reading import read_insider_transactions
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

S1, S2, S3 = date(2026, 10, 2), date(2026, 10, 6), date(2026, 10, 9)


def row(accession: str, known: date, **over: object) -> dict[str, object]:
    base = {
        "instrument_id": "EQ:EXMP", "ts": pd.Timestamp("2026-09-30T20:30:00Z"),
        "known_from": known, "accession": accession, "line": 1, "owner_cik": "0000888001",
        "form": "4", "issuer_cik": "0000999001", "filing_date": date(2026, 9, 30),
        "period_of_report": date(2026, 9, 28), "amends_date": None,
        "transaction_date": date(2026, 9, 28), "derivative": False, "transaction_code": "P",
        "acquired_disposed": "A", "shares": 1000.0, "price": 12.5, "shares_after": 26000.0,
        "direct_indirect": "D", "is_director": True, "is_officer": True,
        "is_ten_pct_owner": False, "is_other": False, "officer_title": "CFO",
        "plan_10b5_1": None, "owner_count": 1,
    }  # fmt: skip
    return {**base, **over}


def reader(*runs: tuple[date, list[dict[str, object]]]) -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for i, (session, rows) in enumerate(runs):
        writer.write_table(
            "events/insider_transaction", session, f"r{i}", stamped(rows, session, f"r{i}")
        )
    return StoreReader(backend)


def test_a_row_is_seen_from_its_known_from_and_never_before() -> None:
    found = reader((S1, [row("A1", date(2026, 9, 30))]))
    assert len(read_insider_transactions(found, through=date(2026, 9, 29))) == 0
    assert len(read_insider_transactions(found, through=date(2026, 9, 30))) == 1
    assert len(read_insider_transactions(found)) == 1  # no bound: every row
    assert read_insider_transactions(reader()).empty


def test_a_restated_line_shows_its_old_version_until_its_own_known_from() -> None:
    old = row("A1", date(2026, 9, 30), price=12.5)
    new = row("A1", date(2026, 10, 7), price=12.0)  # restated: known from the fetch's next session
    found = reader((S1, [old]), (S2, [new]))
    before = read_insider_transactions(found, through=date(2026, 10, 6))
    after = read_insider_transactions(found, through=date(2026, 10, 7))
    assert before["price"].tolist() == [12.5] and after["price"].tolist() == [12.0]
    assert len(read_insider_transactions(found, through=date(2026, 9, 29))) == 0


def test_a_known_amendment_replaces_the_originals_it_names() -> None:
    original = row("A1", date(2026, 9, 30))
    amendment = row(
        "A2", date(2026, 10, 7), form="4/A", amends_date=date(2026, 9, 30), shares=900.0
    )
    found = reader((S1, [original]), (S2, [amendment]))
    seen_before = read_insider_transactions(found, through=date(2026, 10, 6))
    assert seen_before["accession"].tolist() == ["A1"]  # the amendment is not known yet
    seen_after = read_insider_transactions(found, through=date(2026, 10, 7))
    assert seen_after["accession"].tolist() == ["A2"] and seen_after["shares"].tolist() == [900.0]


def test_an_amendment_that_names_no_original_or_another_one_replaces_nothing() -> None:
    kept = row("A1", date(2026, 9, 30))
    unnamed = row("A2", date(2026, 10, 1), form="4/A", amends_date=None)
    elsewhere = row("A3", date(2026, 10, 1), form="4/A", amends_date=date(2026, 9, 29))
    other_owner = row("A4", date(2026, 10, 1), form="4/A", amends_date=date(2026, 9, 30),
                      owner_cik="0000888002")  # fmt: skip
    found = reader((S1, [kept, unnamed, elsewhere, other_owner]))
    assert sorted(read_insider_transactions(found)["accession"]) == ["A1", "A2", "A3", "A4"]


def test_lines_and_owners_of_one_filing_stay_separate_rows() -> None:
    rows = [row("A1", date(2026, 9, 30), line=n, owner_cik=o)
            for n in (1, 2) for o in ("0000888001", "0000888002")]  # fmt: skip
    found = reader((S1, rows), (S3, rows[:1]))  # a rerun of one line: the same key, one row
    assert len(read_insider_transactions(found)) == 4
    only = read_insider_transactions(found, instruments=["EQ:NOPE"])
    assert only.empty
