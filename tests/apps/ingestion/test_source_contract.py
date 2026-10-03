"""Every source adapter honours the same contract (``sources/base.py``).

Add each new vendor adapter to ``ADAPTERS`` with a canned payload; the checks below then
apply to it automatically.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from algotrade.storage.schemas import COMMON, validate_frame
from algotrade_ingestion.jobs.common import stamp
from algotrade_ingestion.sources.base import FetchRequest, Source
from algotrade_ingestion.sources.cboe import CboeOptionsSource
from algotrade_ingestion.sources.http import RetryPolicy
from algotrade_ingestion.sources.nasdaq_trader import NasdaqTraderSource
from algotrade_ingestion.sources.spy_holdings import SpyHoldingsSource
from algotrade_ingestion.sources.synthetic.files import GoldenFiles
from algotrade_ingestion.sources.synthetic.source import GoldenCsvSource
from tests import cboe_fixture as fx
from tests import universe_fixture
from tests.conftest import GOLDEN_DIR

type Adapter = tuple[Source, FetchRequest]


def cboe() -> Adapter:
    payload = fx.payload("TEST")
    source = CboeOptionsSource(lambda url: payload, lambda s: None, RetryPolicy(tries=1))
    return source, FetchRequest("TEST", "EQ:TEST", fx.SESSION)


def golden() -> Adapter:
    return GoldenCsvSource(GoldenFiles(GOLDEN_DIR)), FetchRequest("bull_trend/BULL", "EQ:BULL")


def nasdaq_trader() -> Adapter:
    payload = universe_fixture.nasdaq([("AAPL", "Apple Inc. - Common Stock", "N", "N")])
    return NasdaqTraderSource(lambda url: payload, lambda s: None), FetchRequest("nasdaqlisted")


def spy_holdings() -> Adapter:
    payload = universe_fixture.spy(["AAPL"])
    return SpyHoldingsSource(lambda url: payload, lambda s: None), FetchRequest("SPY")


ADAPTERS: dict[str, Callable[[], Adapter]] = {
    "cboe": cboe,
    "golden": golden,
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
        assert not any(c in frame.columns for c in COMMON), "jobs add point-in-time columns"
        session = normalized.session_date or fx.SESSION
        validate_frame(table, stamp(frame, session, fx.CLOCK_TS, source.name, "run-1"))


def test_missing_key_is_none_not_an_error(tmp_path: Path) -> None:
    source = GoldenCsvSource(GoldenFiles(tmp_path))
    assert source.fetch(FetchRequest("nope/NOPE")) is None
    assert source.fetch(FetchRequest("no-symbol")) is None


def test_cboe_requires_instrument_id() -> None:
    source, request = cboe()
    payload = source.fetch(request)
    assert payload is not None
    with pytest.raises(ValueError, match="instrument_id"):
        source.normalize(FetchRequest("TEST"), payload)
