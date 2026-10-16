"""``data.statements.reading``: increments union across partitions, the latest stored version per
key, a null ``period_start`` (an instant, a marker) equal to another null, every tag of a
concept kept, and point in time by the FILING date (a fact filed after the session is not
read, whenever it was stored)."""

from datetime import UTC, date, datetime

from algotrade.data import StoreReader
from algotrade.data.statements.reading import TABLE, statement_facts, stored_statements
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

D1, D2 = date(2026, 9, 1), date(2026, 10, 1)
STAMP1, STAMP2 = datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)


def instant(tag: str, value: float, end: date, filed: date, concept: str = "cash") -> dict:
    return {
        "instrument_id": "EQ:A", "cik": "0000000001", "concept": concept, "tag": tag,
        "period_type": "INSTANT", "period_start": None, "period_end": end, "filed": filed,
        "value": value, "unit": "usd", "fetched_on": D2,
    }  # fmt: skip


def marker(fetched: date) -> dict:
    return {
        "instrument_id": "EQ:A", "cik": "0000000001", "concept": "checked", "tag": None,
        "period_type": None, "period_start": None, "period_end": None, "filed": None,
        "value": None, "unit": None, "fetched_on": fetched,
    }  # fmt: skip


def test_empty_store() -> None:
    reader = StoreReader(MemoryBackend())
    assert stored_statements(reader).empty
    assert statement_facts(reader, D2).empty


def test_the_same_key_twice_keeps_the_latest_and_null_period_starts_are_one_key() -> None:
    """Fails if a null ``period_start`` (an instant) or a null ``tag`` (a marker) compared
    unequal to itself: the rewritten row and the marker would be stored twice."""
    writer = StoreWriter(MemoryBackend())
    end, filed = date(2026, 6, 30), date(2026, 8, 4)
    first = [
        instant("us-gaap:CashAndCashEquivalentsAtCarryingValue", 100.0, end, filed),
        marker(D1),
    ]
    writer.write_table(TABLE, D1, "r1", stamped(first, D1, "r1", STAMP1))
    second = [
        instant("us-gaap:CashAndCashEquivalentsAtCarryingValue", 105.0, end, filed),
        marker(D2),
    ]
    writer.write_table(TABLE, D2, "r2", stamped(second, D2, "r2", STAMP2))
    stored = stored_statements(StoreReader(writer._backend))
    assert len(stored) == 2
    assert list(stored[stored["concept"] == "cash"]["value"]) == [105.0]
    assert list(stored[stored["concept"] == "checked"]["fetched_on"]) == [D2]
    assert stored["period_start"].isna().all() and stored["tag"].isna().sum() == 1


def test_every_tag_of_a_concept_is_a_row_whatever_the_order() -> None:
    end, filed = date(2026, 6, 30), date(2026, 8, 4)
    rows = [
        instant("us-gaap:CashAndCashEquivalentsAtCarryingValue", 100.0, end, filed),
        instant(
            "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            110.0,
            end,
            filed,
        ),
        instant("us-gaap:ShortTermInvestments", 5.0, end, filed, "sti"),
    ]
    results = []
    for order in (rows, rows[::-1], [rows[1], rows[2], rows[0]]):
        writer = StoreWriter(MemoryBackend())
        writer.write_table(TABLE, D2, "r1", stamped(order, D2, "r1", STAMP2))
        facts = statement_facts(StoreReader(writer._backend), D2)
        assert sorted(facts["value"]) == [5.0, 100.0, 110.0]
        stored = stored_statements(StoreReader(writer._backend))
        results.append(stored[["concept", "tag", "value"]].to_dict("records"))
    assert results[0] == results[1] == results[2]


def test_a_fact_is_read_only_from_its_filing_date_whenever_it_was_stored() -> None:
    writer = StoreWriter(MemoryBackend())
    end = date(2026, 6, 30)
    rows = [
        instant("us-gaap:Assets", 1.0, date(2026, 3, 31), date(2026, 5, 1), "assets"),
        instant("us-gaap:Assets", 2.0, end, date(2026, 8, 4), "assets"),
        instant("us-gaap:Assets", 2.5, end, date(2026, 9, 20), "assets"),  # a restatement
        marker(D2),
    ]
    writer.write_table(TABLE, D2, "r1", stamped(rows, D2, "r1", STAMP2))  # all stored on D2
    reader = StoreReader(writer._backend)
    assert statement_facts(reader, date(2026, 4, 30)).empty
    assert list(statement_facts(reader, date(2026, 5, 1))["value"]) == [1.0]  # the filing day
    assert list(statement_facts(reader, date(2026, 8, 31))["value"]) == [1.0, 2.0]
    on_the_restatement = statement_facts(reader, date(2026, 9, 20))
    assert list(on_the_restatement["value"]) == [1.0, 2.0, 2.5]
    assert "run_id" not in on_the_restatement.columns
    assert "checked" not in set(on_the_restatement["concept"])
