"""Coverage grading of a sampled listing's bars (edges ED6c), on generated sessions."""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import sessions_between
from algotrade_ingestion.tasks.listings.sample_coverage import (
    DELISTED,
    LIVE,
    WINNER,
    Pick,
    coverage_row,
    split_adjusted_ratio,
    summarize,
)

SINCE, UNTIL = date(2010, 1, 1), date(2020, 12, 31)
SESSIONS = sessions_between(SINCE, UNTIL)
NONE = pd.DataFrame(columns=["ts", "split_factor"])


def bars(days: list[date], close: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame({"ts": pd.to_datetime(days, utc=True), "close": close})


def test_a_full_history_to_the_end_date_has_no_gap_and_reaches_the_end() -> None:
    pick = Pick("AAA", date(2008, 1, 2), date(2014, 6, 30), DELISTED)
    days = sessions_between(SINCE, date(2014, 6, 30))
    row = coverage_row(pick, bars(days), NONE, SESSIONS, SINCE, UNTIL)
    assert (row["bars"], row["gap_days"], row["outside_rows"]) == (len(days), 0, 0)
    assert row["first_bar"] == "2010-01-04" and row["last_bar"] == "2014-06-30"
    assert row["to_end"] is True and row["expected_sessions"] == len(days)


def test_missing_sessions_inside_the_history_and_a_short_end_are_counted() -> None:
    pick = Pick("BBB", date(2010, 1, 4), date(2014, 6, 30), DELISTED)
    days = sessions_between(SINCE, date(2014, 6, 30))
    thin = days[:100] + days[104:-40]  # 4 sessions missing inside, the last 40 never arrive
    row = coverage_row(pick, bars(thin), NONE, SESSIONS, SINCE, UNTIL)
    assert row["gap_days"] == 4 and row["end_gap_days"] == 40 and row["to_end"] is False


def test_rows_outside_the_listing_are_counted_so_a_recycled_ticker_shows_its_other_company() -> (
    None
):
    pick = Pick("RCY", date(2012, 3, 1), None, LIVE, recycled=True)
    days = sessions_between(date(2010, 1, 4), date(2010, 1, 8)) + sessions_between(
        date(2012, 3, 1), UNTIL
    )
    row = coverage_row(pick, bars(days), NONE, SESSIONS, SINCE, UNTIL)
    assert row["outside_rows"] == 5 and row["first_bar"] == "2012-03-01"
    verdict = summarize([row])
    assert verdict["recycled_outside_rows"] == 5 and not verdict["pass_recycled_clipped"]


def test_a_name_with_no_bars_is_a_miss() -> None:
    pick = Pick("NONE", date(2010, 1, 4), date(2015, 1, 2), DELISTED)
    row = coverage_row(pick, bars([]), NONE, SESSIONS, SINCE, UNTIL)
    assert row["bars"] == 0 and row["to_end"] is False and row["first_bar"] is None
    assert not summarize([row])["pass_delisted_to_end"]


def test_the_split_adjusted_ratio_undoes_a_split_between_the_two_closes() -> None:
    days = [date(2010, 12, 30), date(2016, 12, 30)]
    prices = pd.DataFrame(
        {"ts": pd.to_datetime(days, utc=True), "close": [10.0, 30.0]}  # 4-for-1 in between
    )
    split = pd.DataFrame(
        {"ts": pd.to_datetime([date(2014, 6, 9)], utc=True), "split_factor": [4.0]}
    )
    assert split_adjusted_ratio(prices, split) == 12.0
    assert split_adjusted_ratio(prices.iloc[:1], split) is None  # no 2016 bar


def test_summary_applies_the_three_pass_criteria() -> None:
    rows = []
    for i in range(10):
        pick = Pick(f"D{i}", date(2010, 1, 4), date(2014, 6, 30), DELISTED)
        days = sessions_between(SINCE, date(2014, 6, 30 if i else 1))  # one name stops early
        rows.append(coverage_row(pick, bars(days), NONE, SESSIONS, SINCE, UNTIL))
    rows.append(
        coverage_row(
            Pick("W", date(2005, 1, 3), None, WINNER), bars(SESSIONS), NONE, SESSIONS, SINCE, UNTIL
        )
    )
    verdict = summarize(rows)
    assert verdict["delisted_with_bars_to_end"] == 0.9 and verdict["pass_delisted_to_end"]
    assert verdict["gap_share"] == 0 and verdict["pass_gap_share"]
    assert verdict["by_stratum"] == {DELISTED: 10, LIVE: 0, WINNER: 1}
