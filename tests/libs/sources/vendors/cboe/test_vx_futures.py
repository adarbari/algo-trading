"""Cboe VIX futures files against the documented format (no network, made-up numbers)."""

from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest, TransientFetchError
from algotrade_sources.framework.http import HttpError
from algotrade_sources.vendors.cboe.option_chains import missing_chain
from algotrade_sources.vendors.cboe.vx_futures import (
    COLUMNS,
    TABLE,
    URL,
    CboeVxFutures,
    contract_id,
    parse_vx,
)
from tests.helpers.ingest_fakes import CountingLimiter, http_for
from tests.helpers.payloads import cboe as files

EXPIRY = date(2013, 5, 22)


def test_parse_reads_prices_counts_and_the_contract() -> None:
    frame = parse_vx(EXPIRY, files.vx_file("F (Jan 2014)"))
    assert tuple(frame.columns) == COLUMNS and len(frame) == 4
    assert set(frame["instrument_id"]) == {"FUT:VX-20130522"} == {contract_id(EXPIRY)}
    assert set(frame["contract"]) == {"F (Jan 2014)"} and set(frame["root"]) == {"VX"}
    assert set(frame["expiry"]) == {EXPIRY}
    last = frame.iloc[-1]
    assert last["session_date"] == date(2013, 5, 22)
    assert (last["settle"], last["close"], last["change"]) == (15.75, 15.8, 0.35)
    assert (last["volume"], last["efp"], last["open_interest"]) == (120, 5, 130)


def test_a_zero_price_is_null_never_a_price() -> None:
    frame = parse_vx(EXPIRY, files.vx_file("F (Jan 2014)")).set_index("session_date")
    assert frame.loc[date(2013, 5, 15), "settle"] != frame.loc[date(2013, 5, 15), "settle"]  # NaN
    quiet = frame.loc[date(2013, 5, 21)]  # no trade: OHLC null, the settle kept
    assert quiet[["open", "high", "low", "close"]].isna().all() and quiet["settle"] == 15.4
    assert frame.loc[date(2013, 5, 21), "volume"] == 0  # counts keep their zero


def test_the_weekly_files_carry_the_month_label_so_the_expiry_is_the_identity() -> None:
    weekly = parse_vx(date(2025, 1, 15), files.vx_file("F (Jan 2025)"))
    monthly = parse_vx(date(2025, 1, 22), files.vx_file("F (Jan 2025)"))
    assert set(weekly["contract"]) == set(monthly["contract"])
    assert set(weekly["instrument_id"]).isdisjoint(set(monthly["instrument_id"]))


def test_rows_with_an_unreadable_trade_date_are_dropped_and_sorted() -> None:
    payload = files.VX_HEADER.encode() + (
        b"\n2013-05-21,F (Jan 2014),1,1,1,1,1,0,1,0,1\nnot a date,F (Jan 2014),1,1,1,1,1,0,1,0,1"
        b"\n2013-05-20,F (Jan 2014),1,1,1,1,1,0,1,0,1\n"
    )
    assert parse_vx(EXPIRY, payload)["session_date"].tolist() == [
        date(2013, 5, 20),
        date(2013, 5, 21),
    ]


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        (b"<html>Just a moment...</html>", "HTML"),
        (b"Trade Date,Futures\n2013-05-20,F (Jan 2014)\n", "no column"),
        (b"", "not a CSV"),
    ],
)
def test_a_body_that_is_not_the_table_raises(payload: bytes, why: str) -> None:
    with pytest.raises(TransientFetchError, match=why):
        parse_vx(EXPIRY, payload)


def test_source_fetches_the_expiry_file_through_the_limiter_and_normalises() -> None:
    urls: list[str] = []
    limiter = CountingLimiter()

    def transport(url: str) -> bytes:
        urls.append(url)
        return files.vx_file("F (Jan 2014)")

    source = CboeVxFutures(http_for(transport, limiter=limiter))
    request = FetchRequest("2013-05-22")
    payload = source.fetch(request)
    assert urls == [URL.format(expiry="2013-05-22")] and limiter.waits == 1
    assert payload is not None
    normalized = source.normalize(request, payload)
    assert normalized is not None and normalized.session_date is None
    assert len(normalized.tables[TABLE]) == 4


def test_a_never_listed_expiry_is_s3_access_denied_which_the_registry_calls_missing() -> None:
    denied = HttpError(403, body=b"<Error><Code>AccessDenied</Code></Error>")
    assert missing_chain(denied)
    assert not missing_chain(HttpError(403, body=b"<html>Cloudflare</html>"))


def test_a_repeated_trade_date_keeps_one_row() -> None:
    """The 2020-03-25 file repeats two trade dates (identical rows): the table key
    (id, session_date, known_from) failed ``duplicate rows`` on the 2013-2026 backfill."""
    row = b"2020-02-27,H (Mar 2020),1,1,1,1,1,0,1,0,1\n"
    payload = (
        files.VX_HEADER.encode() + b"\n" + row + row + row.replace(b"2020-02-27", b"2020-02-28")
    )
    frame = parse_vx(date(2020, 3, 25), payload)
    assert frame["session_date"].tolist() == [date(2020, 2, 27), date(2020, 2, 28)]
