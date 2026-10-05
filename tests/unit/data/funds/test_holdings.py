"""``data.funds.holdings``: a fund's latest holdings, the run that stored them last, the CUSIP
bridge."""

from datetime import UTC, date, datetime

import pytest

from algotrade.data import StoreReader
from algotrade.data.funds.holdings import (
    COLUMNS,
    TABLE,
    cusip_of,
    etf_holdings,
    holdings_status,
    known_cusips,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import holdings_rows, stamped

FUND, OTHER = "EQ:FUND", "EQ:OTHER"
S1, S2, S3 = date(2026, 9, 1), date(2026, 9, 8), date(2026, 9, 15)


def store(*parts: tuple[date, str, list[dict[str, object]], datetime]) -> StoreReader:
    writer = StoreWriter(MemoryBackend())
    for session, run, rows, knowledge in parts:
        writer.write_table(
            TABLE, session, run, stamped(rows, session, run, knowledge, "ssga_holdings")
        )
    return StoreReader(writer._backend)


def at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 22, tzinfo=UTC)


LINES = [("AAA", "Alpha", 0.5), ("BBB", "Beta", 0.3), (None, "Cash", 0.2)]


def test_nothing_stored_is_an_empty_frame_with_the_columns() -> None:
    frame = etf_holdings(StoreReader(MemoryBackend()), FUND, S3)
    assert frame.empty and tuple(frame.columns) == COLUMNS
    assert holdings_status(StoreReader(MemoryBackend()), S3).empty
    assert known_cusips(StoreReader(MemoryBackend()), S3) == {}


def test_the_latest_as_of_wins_and_rows_are_ranked() -> None:
    reader = store(
        (S1, "r1", holdings_rows(FUND, date(2026, 8, 31), LINES), at(S1)),
        (S2, "r2", holdings_rows(FUND, date(2026, 9, 7), LINES[:2], total=40), at(S2)),
    )
    frame = etf_holdings(reader, FUND, S3)
    assert list(frame["rank"]) == [1, 2] and set(frame["as_of"]) == {date(2026, 9, 7)}
    assert set(frame["holdings_count"]) == {40}
    assert list(frame["source"]) == ["ssga_holdings"] * 2


def test_a_shorter_reread_of_the_same_date_leaves_no_stale_ranks() -> None:
    day = date(2026, 9, 7)
    reader = store(
        (S2, "r1", holdings_rows(FUND, day, LINES), at(S2)),
        (S3, "r2", holdings_rows(FUND, day, LINES[:2]), at(S3)),  # the issuer dropped a line
    )
    assert list(etf_holdings(reader, FUND, S3)["holding_name"]) == ["Alpha", "Beta"]


def test_a_date_before_the_read_is_not_known_yet() -> None:
    reader = store(
        (S1, "r1", holdings_rows(FUND, date(2026, 8, 31), LINES), at(S1)),
        (S3, "r2", holdings_rows(FUND, date(2026, 9, 14), LINES[:2]), at(S3)),
    )
    assert len(etf_holdings(reader, FUND, S2)) == 3  # the 14 September file came later
    assert len(etf_holdings(reader, FUND, S3)) == 2
    assert etf_holdings(reader, FUND, date(2026, 8, 1)).empty


def test_as_of_pins_what_was_stored_by_then() -> None:
    reader = store(
        (S1, "r1", holdings_rows(FUND, date(2026, 8, 31), LINES), at(S1)),
        (S2, "r2", holdings_rows(FUND, date(2026, 9, 7), LINES[:2]), at(S2)),
    )
    assert len(etf_holdings(reader, FUND, S3, as_of=at(S1))) == 3


def test_other_funds_are_not_mixed_in() -> None:
    reader = store(
        (S1, "r1", [*holdings_rows(FUND, S1, LINES), *holdings_rows(OTHER, S1, LINES[:1])], at(S1))
    )
    assert len(etf_holdings(reader, OTHER, S3)) == 1
    status = holdings_status(reader, S3)
    assert sorted(status["instrument_id"]) == [FUND, OTHER]


def test_status_has_the_issuers_date_and_the_last_session_read() -> None:
    reader = store(
        (S1, "r1", holdings_rows(FUND, date(2026, 8, 31), LINES), at(S1)),
        (S2, "r2", holdings_rows(FUND, date(2026, 9, 7), LINES), at(S2)),
    )
    row = holdings_status(reader, S3).iloc[0]
    assert (row["as_of"], row["fetched_on"]) == (date(2026, 9, 7), S2)


@pytest.mark.parametrize(
    ("identifier", "cusip"),
    [
        ("037833100", "037833100"),
        ("US0378331005", "037833100"),
        ("CA1234567890", "123456789"),
        ("GB0002634946", None),
        ("CASH_USD", None),
        (None, None),
    ],
)
def test_a_cusip_is_read_from_cusips_and_us_isins(
    identifier: str | None, cusip: str | None
) -> None:
    assert cusip_of(identifier) == cusip


def test_known_cusips_pair_tickers_with_their_security_ids() -> None:
    rows = holdings_rows(FUND, S1, LINES)
    rows[0]["identifier"] = "037833100"
    rows[2]["identifier"] = "CASH_USD"
    reader = store((S1, "r1", rows, at(S1)))
    assert known_cusips(reader, S3) == {"037833100": "AAA", "CUSIP0002": "BBB"}
