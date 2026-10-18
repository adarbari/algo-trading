"""``data.funds.shares``: what a reader on session S may know of a fund's shares outstanding."""

from datetime import UTC, date, datetime

from algotrade.data import StoreReader
from algotrade.data.funds.shares import COLUMNS, TABLE, etf_shares
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

FUND, OTHER = "EQ:FUND", "EQ:OTHER"
D1, D2, D3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5)


def row(fund: str, as_of: date, shares: float, known: date) -> dict[str, object]:
    return {
        "instrument_id": fund, "symbol": fund[3:], "as_of": as_of, "shares_outstanding": shares,
        "ts": datetime(as_of.year, as_of.month, as_of.day, tzinfo=UTC), "known_from": known,
    }  # fmt: skip


def store(*parts: tuple[date, str, list[dict[str, object]], datetime]) -> StoreReader:
    writer = StoreWriter(MemoryBackend())
    for session, run, rows, knowledge in parts:
        writer.write_table(TABLE, session, run, stamped(rows, session, run, knowledge, "ishares"))
    return StoreReader(writer._backend)


def at(day: date, hour: int = 22) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def test_a_row_is_invisible_before_its_known_from_whatever_its_as_of() -> None:
    """The count as of Oct 1 was fetched on the night of Oct 2: a reader on Oct 1 never sees it."""
    reader = store((D2, "r1", [row(FUND, D1, 100.0, D2)], at(D2)))
    assert etf_shares(reader, [FUND], D1, D1).empty
    seen = etf_shares(reader, [FUND], D1, D2)
    assert list(seen.columns) == list(COLUMNS)
    assert list(seen["shares_outstanding"]) == [100.0] and list(seen["as_of"]) == [D1]


def test_a_restated_count_is_seen_from_the_session_it_was_fetched() -> None:
    reader = store(
        (D2, "r1", [row(FUND, D1, 100.0, D2)], at(D2)),
        (D3, "r2", [row(FUND, D1, 104.0, D3)], at(D3)),
    )
    before = etf_shares(reader, [FUND], D1, D2)
    assert list(before["shares_outstanding"]) == [100.0]
    seen = etf_shares(reader, [FUND], D1, D3)
    assert len(seen) == 1 and list(seen["known_from"]) == [D3]
    assert list(seen["shares_outstanding"]) == [104.0]


def test_a_series_is_by_fund_then_date_and_limited_to_the_funds_asked() -> None:
    reader = store(
        (D2, "r1", [row(FUND, D1, 100.0, D2), row(OTHER, D1, 7.0, D2)], at(D2)),
        (D3, "r2", [row(FUND, D2, 110.0, D3)], at(D3)),
    )
    seen = etf_shares(reader, [FUND], D1, D3)
    assert list(seen["as_of"]) == [D1, D2] and set(seen["instrument_id"]) == {FUND}
    assert list(etf_shares(reader, [FUND], D2, D3)["as_of"]) == [D2]
    assert etf_shares(reader, [], D1, D3).empty
