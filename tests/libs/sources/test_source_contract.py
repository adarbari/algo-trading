"""Every source adapter honours the same contract (``sources/framework/base.py``).

Add each new vendor adapter to ``ADAPTERS`` with a canned payload; the checks below then
apply to it automatically.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from algotrade.data.resolver import SymbolResolver
from algotrade.storage.tables.schemas import COMMON, KNOWN_FROM, spec_for, validate_frame
from algotrade_ingestion.tasks.framework.run import stamp
from algotrade_sources.fixtures.files import GoldenFiles
from algotrade_sources.fixtures.source import GoldenCsvSource
from algotrade_sources.framework.base import FetchRequest, Source
from algotrade_sources.framework.http import RetryPolicy
from algotrade_sources.framework.series import SeriesRequest
from algotrade_sources.vendors.cboe.option_chains import CboeOptionsSource
from algotrade_sources.vendors.fred.observations import FredObservations
from algotrade_sources.vendors.fred.releases import FredReleaseDates, ReleaseRequest
from algotrade_sources.vendors.ibkr.gateway import GatewayConfig, IbkrMarketData
from algotrade_sources.vendors.ibkr.market_data import IbkrSource
from algotrade_sources.vendors.ishares.etf_holdings import IsharesHoldings
from algotrade_sources.vendors.massive.bars import MassiveDailyBars
from algotrade_sources.vendors.massive.corporate_actions import MassiveCorporateActions
from algotrade_sources.vendors.massive.overview import MassiveOverview
from algotrade_sources.vendors.massive.tickers import MassiveTickers
from algotrade_sources.vendors.nasdaq.earnings import NasdaqEarningsSource
from algotrade_sources.vendors.nasdaq.symbol_directory import NasdaqTraderSource
from algotrade_sources.vendors.proshares.etf_holdings import ProsharesHoldings
from algotrade_sources.vendors.published.csv_series import PublishedSeries
from algotrade_sources.vendors.sec.company_facts import SecCompanyFacts
from algotrade_sources.vendors.sec.edgar import SecSubmissions, SecTickerMap
from algotrade_sources.vendors.sec.fund_objectives import (
    SecFundObjectives,
    SecFundSeries,
    SecFundTickerMap,
)
from algotrade_sources.vendors.sec.nport_holdings import NportHoldings
from algotrade_sources.vendors.sec.submissions import FilingsRequest, SecFilings
from algotrade_sources.vendors.ssga.etf_holdings import SsgaHoldings
from algotrade_sources.vendors.ssga.spy_holdings import SpyHoldingsSource
from algotrade_sources.vendors.tiingo.prices import TiingoDailyPrices
from algotrade_sources.vendors.treasury.par_yields import TreasuryParYields
from tests.conftest import GOLDEN_DIR, REPO_ROOT
from tests.helpers.fake_ib import FakeIB
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import cboe as fx
from tests.helpers.payloads import fred as fred_payloads
from tests.helpers.payloads import massive as massive_payloads
from tests.helpers.payloads import nasdaq_earnings as earnings_payloads
from tests.helpers.payloads import published as published_payloads
from tests.helpers.payloads import sec as sec_payloads
from tests.helpers.payloads import tiingo as tiingo_payloads
from tests.helpers.payloads import treasury as treasury_payloads
from tests.helpers.payloads import universe as universe_payloads

type Adapter = tuple[Source, FetchRequest]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources"


def cboe() -> Adapter:
    payload = fx.payload("TEST")
    source = CboeOptionsSource(http_for(lambda url: payload, RetryPolicy(tries=1)))
    return source, FetchRequest("TEST", "EQ:TEST", fx.SESSION)


def ibkr() -> Adapter:
    bars = [(fx.SESSION, 10.0, 11.0, 9.0, 10.5, 1e6)]
    fake = FakeIB(bars={"AAPL": bars})
    gateway = IbkrMarketData(GatewayConfig("127.0.0.1", 4002, 1), ib_factory=lambda: fake)
    source = IbkrSource(gateway)
    source.open()  # a session source: tasks open it (base.opened)
    return source, FetchRequest("bars__AAPL", "EQ:AAPL", fx.SESSION)


def golden() -> Adapter:
    return GoldenCsvSource(GoldenFiles(GOLDEN_DIR)), FetchRequest("bull_trend/BULL", "EQ:BULL")


def nasdaq_trader() -> Adapter:
    payload = universe_payloads.nasdaq([("AAPL", "Apple Inc. - Common Stock", "N", "N")])
    return NasdaqTraderSource(http_for(lambda url: payload)), FetchRequest("nasdaqlisted")


def spy_holdings() -> Adapter:
    payload = universe_payloads.spy(["AAPL"])
    return SpyHoldingsSource(http_for(lambda url: payload)), FetchRequest("SPY")


def ssga_holdings() -> Adapter:
    files = FIXTURES / "ssga"
    payloads = {"fundfinder": (files / "fundfinder.json").read_bytes()}
    xlk = (files / "holdings-daily-us-en-xlk.xlsx").read_bytes()
    source = SsgaHoldings(
        http_for(lambda url: payloads["fundfinder"] if "fundfinder" in url else xlk)
    )
    return source, FetchRequest("XLK")


def ishares_holdings() -> Adapter:
    files = FIXTURES / "ishares"
    screener = (files / "product-screener.json").read_bytes()
    ivv = (files / "IVV_latest-holdings.csv").read_bytes()
    source = IsharesHoldings(http_for(lambda url: screener if "screener" in url else ivv))
    return source, FetchRequest("IVV")


def proshares_holdings() -> Adapter:
    sample = (FIXTURES / "proshares" / "psdlyhld_sample.csv").read_bytes()
    return ProsharesHoldings(http_for(lambda url: sample)), FetchRequest("UVXY")


def sec_nport_holdings() -> Adapter:
    files = FIXTURES / "sec"
    funds = (files / "company_tickers_mf.json").read_bytes()
    submissions = (files / "submissions_vanguard_index_funds.json").read_bytes()
    header = (files / "nport_header_0000036405-26-000480.html").read_bytes()
    report = (files / "nport_total_stock_market_trimmed.xml").read_bytes()

    def transport(url: str) -> bytes:
        if "company_tickers_mf" in url:
            return funds
        if "submissions" in url:
            return submissions
        return header if url.endswith("index-headers.html") else report

    return NportHoldings(http_for(transport)), FetchRequest("VTI")


def nasdaq_earnings() -> Adapter:
    payload = earnings_payloads.calendar([("AAPL", "time-after-hours")])
    return NasdaqEarningsSource(http_for(lambda url: payload)), FetchRequest("2026-10-05")


def massive_bars() -> Adapter:
    payload = massive_payloads.grouped(fx.SESSION, [("AAPL", 10.0, 11.0, 9.0, 10.5, 1000.0)])
    source = MassiveDailyBars(http_for(lambda url: payload))
    return source, FetchRequest(fx.SESSION.isoformat())


def tiingo_prices() -> Adapter:
    source = TiingoDailyPrices(http_for(lambda url: tiingo_payloads.sample()))
    return source, FetchRequest("AAPL:2020-08-27:2020-11-06")


def massive_actions() -> Adapter:
    payload = massive_payloads.page(
        [{"ticker": "NVDA", "execution_date": "2026-09-30", "split_from": 1, "split_to": 10}]
    )
    source = MassiveCorporateActions(http_for(lambda url: payload))
    return source, FetchRequest("splits:2026-09-01:2026-10-31")


def massive_tickers() -> Adapter:
    payload = massive_payloads.page(
        [{"ticker": "AAPL", "type": "CS", "composite_figi": "BBG000B9XRY4"}]
    )
    source = MassiveTickers(http_for(lambda url: payload))
    return source, FetchRequest("active")


def massive_overview() -> Adapter:
    payload = (FIXTURES / "massive" / "overview_KO.json").read_bytes()
    return MassiveOverview(http_for(lambda url: payload)), FetchRequest("KO")


def sec_fund_tickers() -> Adapter:
    payload = (FIXTURES / "sec" / "company_tickers_mf_sample.json").read_bytes()
    return SecFundTickerMap(http_for(lambda url: payload)), FetchRequest("fund_tickers")


def sec_fund_objectives() -> Adapter:
    payload = (FIXTURES / "sec" / "rr1_2026q2_sample.zip").read_bytes()
    return SecFundObjectives(http_for(lambda url: payload)), FetchRequest("2026q2")


def sec_fund_series() -> Adapter:
    series = (FIXTURES / "sec" / "investment_company_series_class_sample.csv").read_bytes()
    return SecFundSeries(http_for(lambda url: series)), FetchRequest("2026")


def sec_tickers() -> Adapter:
    payload = sec_payloads.tickers([(320193, "Apple Inc.", "AAPL", "Nasdaq")])
    return SecTickerMap(http_for(lambda url: payload)), FetchRequest("tickers")


def sec_submissions() -> Adapter:
    payload = sec_payloads.submissions(320193, "Apple Inc.")
    return SecSubmissions(http_for(lambda url: payload)), FetchRequest("320193")


def sec_company_facts() -> Adapter:
    payload = (FIXTURES / "sec" / "companyfacts_CIK0000320193.json").read_bytes()
    return SecCompanyFacts(http_for(lambda url: payload)), FetchRequest("320193")


def treasury() -> Adapter:
    payload = treasury_payloads.payload(2025)
    return TreasuryParYields(http_for(lambda url: payload)), FetchRequest("2025")


def fred() -> Adapter:
    request = SeriesRequest("GDP_REAL", code="GDPC1")
    return FredObservations(http_for(lambda url: fred_payloads.payload())), request


def fred_release_dates() -> Adapter:
    payload = (FIXTURES / "fred" / "release_dates_10_cpi.json").read_bytes()
    return FredReleaseDates(http_for(lambda url: payload)), ReleaseRequest("10")


def sec_filings() -> Adapter:
    payload = (FIXTURES / "sec" / "submissions_CIK0000723125.json").read_bytes()
    return SecFilings(http_for(lambda url: payload)), FilingsRequest("723125")


def published() -> Adapter:
    request = SeriesRequest(
        "SPX", url="https://stooq.com/q/d/l/?s=^spx&i=d", date_column="Date", value_column="Close"
    )
    return PublishedSeries(http_for(lambda url: published_payloads.STOOQ)), request


ADAPTERS: dict[str, Callable[[], Adapter]] = {
    "fred": fred,
    "fred_release_dates": fred_release_dates,
    "sec_filings": sec_filings,
    "published": published,
    "treasury": treasury,
    "massive_tickers": massive_tickers,
    "massive_overview": massive_overview,
    "sec_fund_tickers": sec_fund_tickers,
    "sec_fund_objectives": sec_fund_objectives,
    "sec_fund_series": sec_fund_series,
    "sec_tickers": sec_tickers,
    "sec_submissions": sec_submissions,
    "sec_company_facts": sec_company_facts,
    "massive_bars": massive_bars,
    "tiingo_prices": tiingo_prices,
    "massive_actions": massive_actions,
    "nasdaq_earnings": nasdaq_earnings,
    "cboe": cboe,
    "golden": golden,
    "ibkr": ibkr,
    "nasdaq_trader": nasdaq_trader,
    "spy_holdings": spy_holdings,
    "ssga_holdings": ssga_holdings,
    "ishares_holdings": ishares_holdings,
    "proshares_holdings": proshares_holdings,
    "sec_nport_holdings": sec_nport_holdings,
}


@pytest.fixture(params=sorted(ADAPTERS))
def adapter(request: pytest.FixtureRequest) -> Adapter:
    return ADAPTERS[request.param]()


def test_implements_protocol(adapter: Adapter) -> None:
    source, _ = adapter
    assert isinstance(source, Source)
    assert source.name and source.dataset


def test_normalized_tables_satisfy_storage_schemas(adapter: Adapter) -> None:
    source, request = adapter
    payload = source.fetch(request)
    assert payload is not None
    normalized = source.normalize(request, payload)
    assert normalized is not None and (normalized.tables or normalized.parsed)
    for table, frame in normalized.tables.items():
        assert not any(c in frame.columns for c in COMMON), "tasks add point-in-time columns"
        # Vendor-ticker tables carry ``symbol``; the task resolves ids (ADR 0018).
        assert "instrument_id" in frame.columns or "symbol" in frame.columns
        resolved = frame if "instrument_id" in frame.columns else SymbolResolver().resolve(frame)[0]
        spec = spec_for(table)
        if not spec.open_ended and spec.column("symbol") is None:  # e.g. bars: the task drops it
            resolved = resolved.drop(columns="symbol", errors="ignore")
        session = normalized.session_date or fx.SESSION
        if KNOWN_FROM in spec.required:  # the task sets it, like the stamps (ADR 0050)
            assert KNOWN_FROM not in resolved.columns, "tasks decide known_from"
            resolved = resolved.assign(**{KNOWN_FROM: session})
        validate_frame(table, stamp(resolved, session, fx.CLOCK_TS, source.name, "run-1"))


def test_missing_key_is_none_not_an_error(tmp_path: Path) -> None:
    source = GoldenCsvSource(GoldenFiles(tmp_path))
    assert source.fetch(FetchRequest("nope/NOPE")) is None
    assert source.fetch(FetchRequest("no-symbol")) is None


def test_golden_requires_instrument_id() -> None:
    source, request = golden()
    payload = source.fetch(request)
    assert payload is not None
    with pytest.raises(ValueError, match="instrument_id"):
        source.normalize(FetchRequest(request.key), payload)


def test_cboe_requires_instrument_id() -> None:
    source, request = cboe()
    payload = source.fetch(request)
    assert payload is not None
    with pytest.raises(ValueError, match="instrument_id"):
        source.normalize(FetchRequest("TEST"), payload)
