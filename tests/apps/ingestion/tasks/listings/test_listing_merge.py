"""``merge_listings``: pairing Tiingo's rows with Massive's records, and the start date of a
Massive-only record (ADR 0087). The frames come from the two real adapters' parsers; the meta
answers are the RECORDED BBBY one (``meta_bbby_payload``) or built by hand in its shape."""

from collections.abc import Sequence
from datetime import date

import pandas as pd

from algotrade_ingestion.tasks.listings.listing_merge import (
    COLUMNS,
    compare_key,
    merge_listings,
)
from algotrade_sources.vendors.massive.tickers import parse_inactive
from algotrade_sources.vendors.tiingo.listings import parse_listings
from algotrade_sources.vendors.tiingo.meta import parse_meta
from tests.helpers.payloads import massive as mfx
from tests.helpers.payloads import tiingo as tfx

LIVE = (
    "ZLIVE,NYSE,Stock,USD,2000-01-03,2026-10-08"  # the file's latest day: every other end is real
)


def tiingo(*rows: str) -> pd.DataFrame:
    """Rows of ``ticker,exchange,assetType,priceCurrency,startDate,endDate`` through the adapter."""
    header = "ticker,exchange,assetType,priceCurrency,startDate,endDate\n"
    return parse_listings((header + "\n".join([LIVE, *rows])).encode())[0]


def massive(*records: dict[str, object]) -> pd.DataFrame:
    return parse_inactive(list(records))[0]


class Meta:
    """``ask_meta`` over a fixed answer; remembers what it was asked."""

    def __init__(self, payload: bytes | None = None) -> None:
        self.payload, self.asked = payload, []

    def __call__(self, tickers: Sequence[str]) -> pd.DataFrame | None:
        self.asked.append(list(tickers))
        return None if self.payload is None else parse_meta(self.payload)


def merged(
    t: pd.DataFrame, m: pd.DataFrame, meta: Meta | None = None
) -> tuple[pd.DataFrame, dict[str, int]]:
    return merge_listings(t, m, meta or Meta())


def only(frame: pd.DataFrame, source: str, ticker: str) -> pd.Series:
    rows = frame[(frame["source"] == source) & (frame["ticker"] == ticker)]
    assert len(rows) == 1, rows
    return rows.iloc[0]


def test_a_tiingo_row_pairs_with_a_record_ended_within_seven_days_not_eight() -> None:
    for gap, pairs in ((6, True), (7, True), (8, False)):
        end = date(2020, 1, 15 + gap).isoformat()
        out, stats = merged(
            tiingo("OLD,NYSE,Stock,USD,2005-01-03,2020-01-15"),
            massive(mfx.inactive_record("OLD", end, "XNYS", "CS", cik="0000123456")),
        )
        assert (stats["paired"] == 1) is pairs, gap
        if pairs:
            row = only(out, "tiingo", "OLD")
            assert row["security_type"] == "COMMON_STOCK" and row["cik"] == "0000123456"
            assert row["vendor_exchange"] == "XNYS" and row["vendor_end_date"] == date(
                2020, 1, 15 + gap
            )
            assert row["end_date"] == date(2020, 1, 15)  # Tiingo's own end stays
            assert (out["source"] == "massive").sum() == 0
        else:  # not the same listing: the record stands alone, undated (nothing covers it)
            record = only(out, "massive", "OLD")
            assert record["no_id_reason"] == "no_start" and pd.isna(record["start_date"])
            assert pd.isna(only(out, "tiingo", "OLD")["security_type"])


def test_a_reused_ticker_is_pair_ambiguous_and_pairs_nothing() -> None:
    out, stats = merged(
        tiingo("REU,NYSE,Stock,USD,2012-01-03,2018-06-04"),
        massive(
            mfx.inactive_record("REU", "2018-06-01", "XNYS"),  # both within 7 days of Tiingo's end
            mfx.inactive_record("REU", "2018-06-08", "XNYS"),
        ),
    )
    assert stats["paired"] == 0 and stats["pair_ambiguous_records"] == 2
    records = out[out["source"] == "massive"]
    assert list(records["no_id_reason"]) == ["pair_ambiguous", "pair_ambiguous"]
    assert records["start_date"].isna().all()  # never guessed
    assert pd.isna(only(out, "tiingo", "REU")["cik"])  # and the Tiingo row took nothing
    out, stats = merged(  # the other way: two Tiingo rows, one record
        tiingo(
            "TWO,NYSE,Stock,USD,2001-01-03,2010-01-04", "TWO,NYSE,Stock,USD,2000-06-01,2010-01-06"
        ),
        massive(mfx.inactive_record("TWO", "2010-01-05", "XNYS")),
    )
    assert stats["paired"] == 0 and stats["pair_ambiguous_records"] == 1


def test_a_share_class_pairs_across_the_dot_and_the_hyphen_and_a_preferred_never_pairs() -> None:
    assert compare_key("brk.b") == compare_key("BRK-B") == "BRK-B"
    assert compare_key("KIM$L") is None
    out, stats = merged(
        tiingo("BRK-B,NYSE,Stock,USD,1996-05-09,2019-01-03"),
        massive(
            mfx.inactive_record("BRK.B", "2019-01-03", "XNYS"),
            mfx.inactive_record("KIM$L", "2019-01-03", "XNYS", "PFD"),
        ),
    )
    assert stats["paired"] == 1
    assert only(out, "tiingo", "BRK-B")["vendor_end_date"] == date(2019, 1, 3)
    preferred = only(out, "massive", "KIM$L")  # never paired: written alone, undated
    assert preferred["security_type"] == "PREFERRED" and preferred["no_id_reason"] == "no_start"


def test_an_open_tiingo_row_and_a_record_without_an_end_never_pair() -> None:
    out, stats = merged(
        tiingo("OPEN,NYSE,Stock,USD,2005-01-03,2026-10-08"),
        massive(
            mfx.inactive_record("OPEN", "2026-10-06", "XNYS"),
            mfx.inactive_record("NOEND", None, "XNYS"),
        ),
    )
    assert stats["paired"] == 0
    assert only(out, "massive", "NOEND")["no_id_reason"] == "no_start"
    assert pd.isna(only(out, "massive", "NOEND")["end_date"])  # written with its null end


def test_a_massive_only_record_is_written_with_its_exchange_type_and_attributes() -> None:
    out, _ = merged(
        tiingo(),
        massive(
            mfx.inactive_record(
                "FUNDX", "2019-03-01", "ARCX", "ETF", cik="0000999", composite_figi="BBG000F"
            ),
            mfx.inactive_record("WRNT", "2019-03-01", "XNAS", "WARRANT"),
            mfx.inactive_record("PINKY", "2019-03-01", "XOTC", "CS"),
            mfx.inactive_record("NOMIC", "2019-03-01", None, None),
        ),
    )
    fund = only(out, "massive", "FUNDX")
    assert (fund["exchange"], fund["asset_type"], fund["security_type"]) == ("ARCA", "ETF", "ETF")
    assert (fund["end_date"], fund["vendor_end_date"]) == (date(2019, 3, 1), date(2019, 3, 1))
    assert (fund["figi"], fund["cik"], fund["vendor_type"]) == ("BBG000F", "0000999", "ETF")
    assert fund["price_currency"] == "USD" and fund["name"] == "FUNDX Inc"
    assert pd.isna(fund["scope_reason"])
    assert only(out, "massive", "WRNT")["security_type"] == "WARRANT"  # typed, not a common stock
    assert only(out, "massive", "WRNT")["asset_type"] == "Stock"
    pink = only(out, "massive", "PINKY")  # an unmapped MIC: stored, out of scope, MIC kept
    assert (pink["scope_reason"], pink["exchange"], pink["vendor_exchange"]) == (
        "other_exchange",
        "XOTC",
        "XOTC",
    )
    assert only(out, "massive", "NOMIC")["scope_reason"] == "other_exchange"
    assert list(out.columns) == COLUMNS


def test_every_row_and_every_record_is_kept() -> None:
    t = tiingo(
        "AAA,NYSE,Stock,USD,2005-01-03,2020-01-15",
        "BC/PA,NYSE,Stock,USD,2005-01-03,2020-01-15",  # odd ticker
        "CNY1,NYSE,Stock,CNY,2005-01-03,2020-01-15",  # not USD
    )
    m = massive(
        mfx.inactive_record("AAA", "2020-01-15", "XNYS"),
        mfx.inactive_record("ONLYM", "2018-01-15", "XNYS"),
    )
    out, stats = merged(t, m)
    assert len(out) == len(t) + 1  # the paired record is the Tiingo row; ONLYM is one more
    assert stats["massive_records"] == 2 and stats["massive_only"] == 1
    assert out.loc[out["ticker"] == "BC/PA", "scope_reason"].item() == "odd_ticker"


def test_bbby_takes_the_start_of_its_otc_successor_only_when_meta_names_one_company() -> None:
    t = tiingo("BBBYQ,PINK,Stock,USD,1992-06-04,2023-09-29")
    m = massive(mfx.inactive_record("BBBY", "2023-05-02", "XNAS", "CS"))
    # What Tiingo answered on 2026-11-01: bbby is a reused ticker's permaTicker, bbbyq the bankrupt
    # company's. Two permaTickers: the start stays null (the safe outcome), nothing is guessed.
    meta = Meta(tfx.meta_bbby_payload())
    out, stats = merged(t, m, meta)
    record = only(out, "massive", "BBBY")
    assert meta.asked == [["BBBY", "BBBYQ"]] and stats["meta_record_requests"] == 1
    assert pd.isna(record["start_date"]) and record["no_id_reason"] == "perma_ambiguous"
    assert record["perma_ticker"] == "" and stats["massive_perma_ambiguous"] == 1
    # Were both tickers one company (one permaTicker on both rows), the record takes BBBYQ's start.
    same = Meta(
        tfx.meta_rows(
            ("US000000000258", "bbby", None, True),
            ("US000000000258", "bbbyq", "Bed Bath & Beyond Inc", True),
        )
    )
    record = only(merged(t, m, same)[0], "massive", "BBBY")
    assert record["start_date"] == date(1992, 6, 4) and pd.isna(record["no_id_reason"])
    assert record["perma_ticker"] == "US000000000258"
    assert record["data_provider_perma_ticker"] == "000258" and not record["is_adr"]
    assert record["end_date"] == date(2023, 5, 2) and record["source"] == "massive"
    # One candidate and meta naming only the record's own ticker: still that candidate's start.
    own = Meta(tfx.meta_rows(("US000000000258", "bbby", None, True)))
    assert only(merged(t, m, own)[0], "massive", "BBBY")["start_date"] == date(1992, 6, 4)


def test_with_no_successor_the_record_is_still_written_undated_and_nothing_is_asked() -> None:
    meta = Meta(tfx.meta_bbby_payload())
    out, stats = merged(tiingo(), massive(mfx.inactive_record("BBBY", "2023-05-02")), meta)
    record = only(out, "massive", "BBBY")
    assert pd.isna(record["start_date"]) and record["no_id_reason"] == "no_start"
    assert meta.asked == [] and stats["meta_record_requests"] == 0
    # A successor that started after the record's last day, or ended long before it, is none.
    late = tiingo(
        "BBBYQ,PINK,Stock,USD,2024-01-02,2024-06-03", "BBBYZ,PINK,Stock,USD,1990-01-02,2020-01-03"
    )
    out, _ = merged(late, massive(mfx.inactive_record("BBBY", "2023-05-02")), meta)
    assert only(out, "massive", "BBBY")["no_id_reason"] == "no_start" and meta.asked == []
    # A prefix longer by more than two characters is another company.
    far = tiingo("BBBYXYZ,PINK,Stock,USD,1992-06-04,2023-09-29")
    out, _ = merged(far, massive(mfx.inactive_record("BBBY", "2023-05-02")), meta)
    assert only(out, "massive", "BBBY")["no_id_reason"] == "no_start"


def test_a_record_whose_ticker_a_kept_tiingo_row_covers_is_undated_not_asked() -> None:
    meta = Meta(tfx.meta_bbby_payload())
    t = tiingo(
        "BBBY,NASDAQ,Stock,USD,2015-01-02,2026-10-01", "BBBYQ,PINK,Stock,USD,1992-06-04,2023-09-29"
    )
    out, _ = merged(t, massive(mfx.inactive_record("BBBY", "2023-05-02")), meta)
    record = only(
        out, "massive", "BBBY"
    )  # the ticker was reused: that row's life is not the record's
    assert record["no_id_reason"] == "overlaps_listing" and pd.isna(record["start_date"])
    assert meta.asked == []


def test_an_unanswered_meta_request_leaves_the_record_undated_with_no_meta() -> None:
    t = tiingo("BBBYQ,PINK,Stock,USD,1992-06-04,2023-09-29")
    out, stats = merged(t, massive(mfx.inactive_record("BBBY", "2023-05-02")), Meta(None))
    assert only(out, "massive", "BBBY")["no_id_reason"] == "no_meta"
    assert stats["massive_no_meta"] == 1


def test_two_candidates_naming_one_company_are_ambiguous_too() -> None:
    t = tiingo(
        "BBBYQ,PINK,Stock,USD,1992-06-04,2023-09-29", "BBBYQ,OTC,Stock,USD,2010-02-03,2023-09-29"
    )
    both = Meta(tfx.meta_rows(("US1", "bbby", None, True), ("US1", "bbbyq", "Bed Bath", True)))
    out, _ = merged(t, massive(mfx.inactive_record("BBBY", "2023-05-02")), both)
    assert only(out, "massive", "BBBY")["no_id_reason"] == "perma_ambiguous"  # which start?
