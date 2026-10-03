"""The Treasury par yield curve source against recorded CSVs (no network)."""

import math
from datetime import date

import pandas as pd
import pytest

from algotrade_ingestion.sources.framework.base import FetchRequest
from algotrade_ingestion.sources.framework.http import RetryPolicy
from algotrade_ingestion.sources.vendors.treasury.par_yields import (
    TABLE,
    TreasuryParYields,
    parse_curve,
    tenor_of,
)
from tests.helpers.ingest_fakes import CountingLimiter, http_for
from tests.helpers.payloads import treasury as treasury_payloads


@pytest.mark.parametrize(
    ("header", "tenor"),
    [("1 Mo", "1M"), ("1.5 Month", "1.5M"), ("4 Mo", "4M"), ("1 Yr", "1Y"), ("30 Yr", "30Y")],
)
def test_headers_become_tenors(header: str, tenor: str) -> None:
    assert tenor_of(header) == tenor
    assert tenor_of("Date") is None


def test_parses_the_2025_format() -> None:
    frame, unknown = parse_curve(treasury_payloads.payload(2025))
    assert unknown == 0
    days = pd.to_datetime(frame["ts"], utc=True).dt.date
    assert sorted(set(days)) == [
        date(2025, 1, 2),
        date(2025, 1, 3),
        date(2025, 12, 29),
        date(2025, 12, 30),
        date(2025, 12, 31),
    ]
    last = frame[days == date(2025, 12, 31)]
    assert len(last) == 14  # every tenor incl. 1.5 Month
    assert last["tenor"].tolist()[:3] == ["1M", "1.5M", "2M"]  # ordered by days
    one_month = last.iloc[0]
    assert one_month["instrument_id"] == "RATE:UST-1M"
    assert (one_month["tenor_days"], one_month["rate_par"]) == (30, pytest.approx(0.0374))
    tau = 30 / 365
    assert one_month["rate_cont"] == pytest.approx(math.log(1 + 0.0374 * tau) / tau)
    # 1.5 Month started in Feb 2025: January rows leave it out instead of storing a gap.
    assert len(frame[days == date(2025, 1, 2)]) == 13


def test_parses_older_columns_and_empty_years() -> None:
    frame, _ = parse_curve(treasury_payloads.payload(2020))
    assert "4M" not in set(frame["tenor"]) and "2M" in set(frame["tenor"])
    assert frame[frame["tenor"] == "30Y"]["rate_par"].tolist() == pytest.approx([0.0166, 0.0165])
    empty, _ = parse_curve(b"")
    assert empty.empty and "rate_cont" in empty.columns


def test_unknown_columns_are_counted_and_bad_headers_rejected() -> None:
    frame, unknown = parse_curve(b'Date,"1 Mo","Mystery"\n01/02/2025,4.45,1.0\n,\n')
    assert (len(frame), unknown) == (1, 1)
    with pytest.raises(ValueError, match="header"):
        parse_curve(b"When,1 Mo\n01/02/2025,4.45\n")


def test_source_fetches_one_year_per_request_through_the_limiter() -> None:
    urls: list[str] = []
    limiter = CountingLimiter()

    def transport(url: str) -> bytes:
        urls.append(url)
        return treasury_payloads.payload(2025)

    source = TreasuryParYields(http_for(transport, RetryPolicy(tries=1), limiter))
    request = FetchRequest("2025")
    payload = source.fetch(request)
    assert "daily-treasury-rates.csv/2025/all" in urls[0] and "field_tdr_date_value=2025" in urls[0]
    assert limiter.waits == 1
    normalized = source.normalize(request, payload or b"")
    assert normalized is not None and normalized.session_date is None  # several dates
    assert len(normalized.tables[TABLE]) == 14 * 3 + 13 * 2
    weird = source.normalize(request, b'Date,"Odd"\n01/02/2025,1\n')
    assert weird is not None and weird.notes == {"unknown_columns": 1}
