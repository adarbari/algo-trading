"""``data.shares``: increments union across partitions, the latest stored version per key
(a year-to-date and a quarterly fact of one end date are two keys), markers kept apart from
facts, facts ordered by filing date."""

from datetime import UTC, date, datetime

from algotrade.data import StoreReader
from algotrade.data.shares import TABLE, share_facts, stored_shares
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

D1, D2 = date(2026, 9, 1), date(2026, 10, 1)


def row(concept: str, shares: float | None, filed: date | None, fetched: date) -> dict[str, object]:
    return {
        "instrument_id": "EQ:A", "cik": "0000000001", "concept": concept, "shares": shares,
        "period_start": None, "period_end": filed, "filed": filed, "fetched_on": fetched,
    }  # fmt: skip


def test_empty_store() -> None:
    reader = StoreReader(MemoryBackend())
    assert stored_shares(reader).empty and share_facts(reader).empty


def test_union_latest_version_and_markers() -> None:
    writer = StoreWriter(MemoryBackend())
    first = [row("dei", 10.0, date(2026, 5, 1), D1), row("checked", None, None, D1)]
    writer.write_table(TABLE, D1, "r1", stamped(first, D1, "r1", datetime(2026, 9, 1, tzinfo=UTC)))
    second = [
        row("dei", 11.0, date(2026, 5, 1), D2),  # a re-stated value for the same key
        row("dei", 12.0, date(2026, 8, 1), D2),
        row("checked", None, None, D2),
    ]
    writer.write_table(
        TABLE, D2, "r2", stamped(second, D2, "r2", datetime(2026, 10, 1, tzinfo=UTC))
    )
    reader = StoreReader(writer._backend)
    stored = stored_shares(reader)
    assert len(stored) == 3
    marker = stored[stored["concept"] == "checked"]
    assert list(marker["fetched_on"]) == [D2]
    facts = share_facts(reader)
    assert list(facts["shares"]) == [11.0, 12.0]
    assert list(facts["filed"]) == [date(2026, 5, 1), date(2026, 8, 1)]
    assert "run_id" not in facts.columns


def test_flows_of_one_end_date_are_told_apart_by_their_start() -> None:
    writer = StoreWriter(MemoryBackend())
    end, filed = date(2026, 6, 30), date(2026, 8, 4)
    rows = [
        {"instrument_id": "EQ:A", "cik": "0000000001", "concept": "revenue", "value": v,
         "unit": "usd", "period_start": start, "period_end": end, "filed": filed,
         "fetched_on": D2}
        for v, start in ((140.0, date(2026, 4, 1)), (270.0, date(2026, 1, 1)))
    ]  # fmt: skip
    writer.write_table(TABLE, D2, "r1", stamped(rows, D2, "r1", datetime(2026, 10, 1, tzinfo=UTC)))
    again = [{**rows[0], "value": 150.0}]  # a restated quarter replaces only its own key
    writer.write_table(TABLE, D2, "r2", stamped(again, D2, "r2", datetime(2026, 10, 2, tzinfo=UTC)))
    facts = share_facts(StoreReader(writer._backend))
    assert sorted(facts["value"]) == [150.0, 270.0]
