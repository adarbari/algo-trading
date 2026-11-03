"""``merge_listings`` step 6 (ADR 0087, PR3b): Massive ticker details fill the start a Massive-only
record still lacks, only when the identity agrees, and every refusal is counted and keeps the old
reason. The BBBY case is the probed one: Tiingo's meta cannot date it (``perma_ambiguous``), the
details of 2023-05-02 name the old Bed Bath & Beyond, listed 1992-06-04."""

from datetime import date
from typing import Any

import pandas as pd
import pytest

from algotrade_ingestion.tasks.listings.listing_merge import COLUMNS, merge_listings
from algotrade_sources.vendors.massive.tickers import parse_inactive
from algotrade_sources.vendors.tiingo.listings import parse_listings
from algotrade_sources.vendors.tiingo.meta import parse_meta
from tests.helpers.payloads import massive as mfx
from tests.helpers.payloads import tiingo as tfx

LIVE = "ZLIVE,NYSE,Stock,USD,2000-01-03,2026-10-08"
END = date(2023, 5, 2)


def tiingo(*rows: str) -> pd.DataFrame:
    header = "ticker,exchange,assetType,priceCurrency,startDate,endDate\n"
    return parse_listings((header + "\n".join([LIVE, *rows])).encode())[0]


def massive(*records: dict[str, object]) -> pd.DataFrame:
    return parse_inactive(list(records))[0]


def details(ticker: str = "BBBY", end: date = END, found: bool = True, **more: Any) -> pd.DataFrame:
    row = {
        "ticker": ticker, "end_date": end, "found": found, "list_date": date(1992, 6, 4),
        "cik": "0000886158", "figi": "BBG000BB5R87", "delisted_date": end,
    }  # fmt: skip
    return pd.DataFrame([{**row, **more}])


def ask_bbby_meta(tickers: Any) -> pd.DataFrame:
    return parse_meta(tfx.meta_bbby_payload())  # perma_ambiguous for BBBY


def no_meta(tickers: Any) -> None:
    return None


def record(out: pd.DataFrame, ticker: str = "BBBY") -> pd.Series:
    rows = out[(out["source"] == "massive") & (out["ticker"] == ticker)]
    assert len(rows) == 1
    return rows.iloc[0]


T = tiingo("BBBYQ,PINK,Stock,USD,1992-06-04,2023-09-29")
M = massive(mfx.inactive_record("BBBY", "2023-05-02", "XNAS", "CS"))


def test_bbby_perma_ambiguous_is_dated_by_its_details() -> None:
    out, stats = merge_listings(T, M, ask_bbby_meta, details())
    row = record(out)
    assert row["start_date"] == date(1992, 6, 4) and row["start_source"] == "massive_details"
    assert pd.isna(row["no_id_reason"]) and row["end_date"] == END and row["perma_ticker"] == ""
    assert stats["details_dated"] == 1 and stats["massive_dated"] == 1
    assert "massive_perma_ambiguous" not in stats
    without, base = merge_listings(T, M, ask_bbby_meta)  # no details frame: as PR2
    assert record(without)["no_id_reason"] == "perma_ambiguous" and base["details_dated"] == 0
    empty, _ = merge_listings(T, M, ask_bbby_meta, pd.DataFrame())
    assert record(empty)["no_id_reason"] == "perma_ambiguous"


@pytest.mark.parametrize(
    ("tiingo_rows", "meta", "reason"),
    [
        ((), no_meta, "no_start"),  # no successor to ask about
        (("BBBYQ,PINK,Stock,USD,1992-06-04,2023-09-29",), no_meta, "no_meta"),  # unanswered
        (("BBBYQ,PINK,Stock,USD,1992-06-04,2023-09-29",), ask_bbby_meta, "perma_ambiguous"),
    ],
)
def test_each_reason_details_can_lift_is_lifted(tiingo_rows: Any, meta: Any, reason: str) -> None:
    t = tiingo(*tiingo_rows)
    assert record(merge_listings(t, M, meta)[0])["no_id_reason"] == reason
    row = record(merge_listings(t, M, meta, details())[0])
    assert row["start_date"] == date(1992, 6, 4) and row["start_source"] == "massive_details"


@pytest.mark.parametrize(
    ("answer", "counter"),
    [
        (details(cik="0000999999"), "details_mismatch"),
        (details(figi="BBG000OTHER0"), "details_mismatch"),
        (details(delisted_date=date(2023, 5, 10)), "details_mismatch"),  # 8 days from the end
        (details(list_date=date(2023, 5, 3)), "details_after_end"),
    ],
)
def test_a_refused_detail_keeps_the_old_reason_and_is_counted(answer: Any, counter: str) -> None:
    m = massive(mfx.inactive_record("BBBY", "2023-05-02", "XNAS", "CS", cik="0000886158",
                                    composite_figi="BBG000BB5R87"))  # fmt: skip
    out, stats = merge_listings(T, m, ask_bbby_meta, answer)
    row = record(out)
    assert row["no_id_reason"] == "perma_ambiguous" and pd.isna(row["start_date"])
    assert pd.isna(row["start_source"]) and stats[counter] == 1 and stats["details_dated"] == 0


def test_the_delisted_date_within_seven_days_and_missing_identifiers_agree() -> None:
    m = massive(mfx.inactive_record("BBBY", "2023-05-02", "XNAS", "CS", cik="0000886158"))
    near = details(delisted_date=date(2023, 5, 9), figi=None)  # 7 days; the record has no figi
    out, stats = merge_listings(T, m, ask_bbby_meta, near)
    assert record(out)["start_date"] == date(1992, 6, 4) and stats["details_dated"] == 1
    bare = details(cik=None, figi=None, delisted_date=None)
    assert record(merge_listings(T, M, ask_bbby_meta, bare)[0])["start_date"] == date(1992, 6, 4)


def test_a_life_that_meets_an_in_scope_row_of_the_ticker_is_overlaps_listing_from_details() -> None:
    t = tiingo("BBBY,NASDAQ,Stock,USD,2005-01-03,2020-01-15")  # a reused ticker, ended earlier
    out, stats = merge_listings(t, M, no_meta, details())
    row = record(out)
    assert row["no_id_reason"] == "no_start" and pd.isna(row["start_date"])
    assert stats["details_overlaps"] == 1 and stats["details_dated"] == 0


def test_a_not_found_marker_or_another_session_end_changes_nothing() -> None:
    marker, stats = merge_listings(T, M, ask_bbby_meta, details(found=False))
    assert record(marker)["no_id_reason"] == "perma_ambiguous"
    assert not any(stats[k] for k in ("details_dated", "details_mismatch", "details_after_end"))
    other_day, _ = merge_listings(T, M, ask_bbby_meta, details(end=date(2023, 5, 3)))
    assert record(other_day)["no_id_reason"] == "perma_ambiguous"  # keyed by (ticker, end)
    other_ticker, _ = merge_listings(T, M, ask_bbby_meta, details(ticker="OTHER"))
    assert record(other_ticker)["no_id_reason"] == "perma_ambiguous"


def test_pair_ambiguous_and_overlaps_listing_are_never_lifted() -> None:
    reused = tiingo("REU,NYSE,Stock,USD,2012-01-03,2018-06-04")
    both = massive(
        mfx.inactive_record("REU", "2018-06-01", "XNYS"),
        mfx.inactive_record("REU", "2018-06-08", "XNYS"),
    )
    out, stats = merge_listings(reused, both, no_meta, details("REU", date(2018, 6, 1)))
    reu = out[(out["source"] == "massive") & (out["ticker"] == "REU")]
    assert set(reu["no_id_reason"]) == {"pair_ambiguous"} and stats["details_dated"] == 0
    covered = tiingo("BBBY,NASDAQ,Stock,USD,2015-01-02,2026-10-01")  # alive on its last day
    out, stats = merge_listings(covered, M, no_meta, details())
    assert record(out)["no_id_reason"] == "overlaps_listing" and stats["details_overlaps"] == 0


def test_start_source_says_where_each_start_came_from() -> None:
    same = tfx.meta_rows(
        ("US000000000258", "bbby", None, False), ("US000000000258", "bbbyq", "Bed Bath", True)
    )
    out, _ = merge_listings(T, M, lambda tickers: parse_meta(same), details())
    assert record(out)["start_source"] == "perma_successor"  # step 5 won; details not consulted
    assert set(out[out["source"] == "tiingo"]["start_source"]) == {"tiingo"}
    assert "start_source" in COLUMNS
