"""etf-holdings: shares outstanding from the iShares file it already reads, and the nightly
read of the ``daily_funds`` list (no network)."""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta

from algotrade.data import StoreReader
from algotrade.data.funds.shares import etf_shares
from algotrade_ingestion.tasks.market.etf_holdings import SHARES_SOURCE, daily_due, shares_frame
from tests.apps.ingestion.tasks.market.test_etf_holdings import DAY, run, world

FUNDS = ["EQ:IVV", "EQ:IWM", "EQ:AGG", "EQ:XLK"]
LATER = DAY + timedelta(days=1)


@dataclass(frozen=True)
class Fake:
    name: str


def counts(writer, on: date) -> dict[str, tuple[date, float, date]]:  # type: ignore[no-untyped-def]
    seen = etf_shares(StoreReader(writer._backend), FUNDS, DAY - timedelta(days=30), on)
    return {
        i[3:]: (a, s, k)
        for i, a, s, k in zip(
            seen["instrument_id"], seen["as_of"], seen["shares_outstanding"], seen["known_from"],
            strict=True,
        )
    }  # fmt: skip


def test_an_ishares_read_stores_the_files_count_and_date_and_a_ssga_read_none() -> None:
    writer, sources = world()
    run(writer, sources)
    assert counts(writer, DAY) == {
        "IVV": (date(2026, 10, 1), 1_149_200_000.0, DAY),
        "IWM": (date(2026, 10, 1), 277_650_000.0, DAY),
        "AGG": (date(2026, 10, 2), 1_441_300_000.0, DAY),
    }  # XLK (State Street's workbook states no count) has no row


def test_a_count_fetched_after_the_close_is_not_known_to_that_sessions_open() -> None:
    """IVV's file is as of Oct 1 and was fetched on Oct 2 at 18:00 New York time: known from
    Oct 2, so a reader on Oct 1 sees nothing (the as-of date is not the knowledge date)."""
    writer, sources = world()
    run(writer, sources)
    assert "IVV" not in counts(writer, date(2026, 10, 1))
    assert counts(writer, DAY)["IVV"][0] == date(2026, 10, 1)


def test_known_from_is_the_new_york_date_of_the_fetch_and_never_before_the_as_of_date() -> None:
    late_night = datetime(2026, 10, 3, 1, tzinfo=UTC)  # 21:00 on Oct 2 in New York
    assert shares_frame("EQ:X", "X", date(2026, 10, 1), 5.0, late_night)["known_from"][0] == date(
        2026, 10, 2
    )
    early = datetime(2026, 10, 1, 12, tzinfo=UTC)  # a file claiming a date after the fetch
    assert shares_frame("EQ:X", "X", date(2026, 10, 2), 5.0, early)["known_from"][0] == date(
        2026, 10, 2
    )


def test_a_daily_fund_is_read_every_night_outside_the_cap_and_the_rest_weekly() -> None:
    writer, sources = world()
    daily = replace(sources, daily_funds=("IVV",))
    first = run(writer, daily, DAY, limit=0)  # a zero cap reads only the daily list
    assert first.stats["daily"] == 1 and first.stats["requested"] == 1
    assert set(counts(writer, DAY)) == {"IVV"}
    second = run(writer, daily, LATER, limit=0)
    assert second.stats["requested"] == 1 and second.stats["share_rows"] == 1
    third = run(writer, daily, LATER, limit=0)  # already read that session: not again
    assert third.stats["requested"] == 0


def test_daily_due_takes_only_ishares_funds_not_read_today_and_not_held() -> None:
    ishares, other = Fake(SHARES_SOURCE), Fake("ssga_holdings")
    covered = {"A": ishares, "B": ishares, "C": ishares, "D": other}
    read = {"A": DAY, "B": DAY - timedelta(days=1)}
    hold = {"C": DAY + timedelta(days=2)}
    due = daily_due(["D", "C", "B", "A", "Z"], covered, read, DAY, hold)  # type: ignore[arg-type]
    assert due == ["B"]
    assert daily_due(["C"], covered, {}, DAY + timedelta(days=2), hold) == ["C"]  # type: ignore[arg-type]


def test_a_weekend_fetch_is_known_from_the_next_session() -> None:
    saturday = datetime(2026, 10, 3, 15, tzinfo=UTC)  # Saturday 11:00 in New York
    frame = shares_frame("EQ:X", "X", date(2026, 10, 2), 5.0, saturday)
    assert frame["known_from"][0] == date(2026, 10, 5)  # the Monday
    friday_night = datetime(2026, 10, 3, 1, tzinfo=UTC)  # Friday 21:00 in New York
    assert shares_frame("EQ:X", "X", date(2026, 10, 2), 5.0, friday_night)["known_from"][0] == (
        date(2026, 10, 2)
    )
