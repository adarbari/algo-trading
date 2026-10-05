"""Every source adapter honours the same contract (``sources/framework/base.py``).

Add each new vendor adapter to ``ADAPTERS`` with a canned payload; the checks below then
apply to it automatically.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from algotrade.data.resolver import SymbolResolver
from algotrade.storage.tables.schemas import COMMON, spec_for, validate_frame
from algotrade_ingestion.tasks.framework.run import stamp
from algotrade_sources.fixtures.files import GoldenFiles
from algotrade_sources.fixtures.source import GoldenCsvSource
from algotrade_sources.framework.base import FetchRequest, Source
from algotrade_sources.framework.http import RetryPolicy
from algotrade_sources.vendors.cboe.option_chains import CboeOptionsSource
from algotrade_sources.vendors.ibkr.gateway import GatewayConfig, IbkrMarketData
from algotrade_sources.vendors.ibkr.market_data import IbkrSource
from algotrade_sources.vendors.massive.bars import MassiveDailyBars
from algotrade_sources.vendors.massive.corporate_actions import MassiveCorporateActions
from algotrade_sources.vendors.massive.overview import MassiveOverview
from algotrade_sources.vendors.massive.tickers import MassiveTickers
from algotrade_sources.vendors.nasdaq.earnings import NasdaqEarningsSource
from algotrade_sources.vendors.nasdaq.symbol_directory import NasdaqTraderSource
from algotrade_sources.vendors.sec.company_facts import SecCompanyFacts
from algotrade_sources.vendors.sec.edgar import SecSubmissions, SecTickerMap
from algotrade_sources.vendors.sec.fund_objectives import SecFundObjectives, SecFundTickerMap
from algotrade_sources.vendors.ssga.spy_holdings import SpyHoldingsSource
from algotrade_sources.vendors.treasury.par_yields import TreasuryParYields
from tests.conftest import GOLDEN_DIR, REPO_ROOT
from tests.helpers.fake_ib import FakeIB
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import cboe as fx
from tests.helpers.payloads import massive as massive_payloads
from tests.helpers.payloads import nasdaq_earnings as earnings_payloads
from tests.helpers.payloads import sec as sec_payloads
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


def nasdaq_earnings() -> Adapter:
    payload = earnings_payloads.calendar([("AAPL", "time-after-hours")])
    return NasdaqEarningsSource(http_for(lambda url: payload)), FetchRequest("2026-10-05")


def massive_bars() -> Adapter:
    payload = massive_payloads.grouped(fx.SESSION, [("AAPL", 10.0, 11.0, 9.0, 10.5, 1000.0)])
    source = MassiveDailyBars(http_for(lambda url: payload))
    return source, FetchRequest(fx.SESSION.isoformat())


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


ADAPTERS: dict[str, Callable[[], Adapter]] = {
    "treasury": treasury,
    "massive_tickers": massive_tickers,
    "massive_overview": massive_overview,
    "sec_fund_tickers": sec_fund_tickers,
    "sec_fund_objectives": sec_fund_objectives,
    "sec_tickers": sec_tickers,
    "sec_submissions": sec_submissions,
    "sec_company_facts": sec_company_facts,
    "massive_bars": massive_bars,
    "massive_actions": massive_actions,
    "nasdaq_earnings": nasdaq_earnings,
    "cboe": cboe,
    "golden": golden,
    "ibkr": ibkr,
    "nasdaq_trader": nasdaq_trader,
    "spy_holdings": spy_holdings,
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
