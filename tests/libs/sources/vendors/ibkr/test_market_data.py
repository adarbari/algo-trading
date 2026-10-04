"""``IbkrSource``: a session source whose answers are saved as JSON and replayed by
``normalize`` into frames, one request kind per key."""

import json
from datetime import date

import pandas as pd
import pytest

from algotrade_sources.framework.base import (
    FetchRequest,
    SessionSource,
    Source,
    opened,
)
from algotrade_sources.vendors.ibkr.gateway import GatewayConfig, IbkrMarketData
from algotrade_sources.vendors.ibkr.market_data import (
    IbkrSource,
    option_key,
    parse_key,
)
from tests.helpers.fake_ib import FakeIB

SESSION = date(2026, 10, 2)


def source(fake: FakeIB, sessions: int = 2) -> IbkrSource:
    gateway = IbkrMarketData(GatewayConfig("127.0.0.1", 4002, 1), ib_factory=lambda: fake)
    return IbkrSource(gateway, sessions)


def fake() -> FakeIB:
    bars = [(date(2026, 10, d), 10.0, 11.0, 9.0, 10.5, 1e6) for d in (1, 2)]
    return FakeIB(
        bars={"AAPL": bars},
        iv={"AAPL": bars},
        dividends={"AAPL": (1.0, 250.0)},
        expirations=["20261120", "20261218"],
        strikes=[230.0, 235.0],
        quotes={("20261120", 230.0, "C"): (5.0, 5.2)},
    )


def test_is_a_session_source_opened_and_always_closed() -> None:
    ib = fake()
    src = source(ib)
    assert isinstance(src, Source) and isinstance(src, SessionSource)
    with pytest.raises(RuntimeError), opened(src):
        assert "client.isReady" in ib.calls
        raise RuntimeError("boom")
    assert ib.calls[-1] == "disconnect"


def test_every_kind_round_trips_through_raw_json() -> None:
    ib = fake()
    src = source(ib)
    src.open()
    keys = {
        "bars__AAPL": "bars",
        "iv__AAPL": "iv",
        "div__AAPL": "div",
        option_key("AAPL", date(2026, 11, 20), "C", 230.0): "option",
    }
    for key, kind in keys.items():
        request = FetchRequest(key, "EQ:AAPL", SESSION)
        payload = src.fetch(request)
        assert payload is not None and json.loads(payload)["session"] == "2026-10-02"
        normalized = src.normalize(request, payload)
        assert normalized is not None and normalized.tables == {}
        assert not normalized.parsed[kind].empty, key
    bars = src.normalize(
        FetchRequest("bars__AAPL"), src.fetch(FetchRequest("bars__AAPL", None, SESSION)) or b""
    )
    assert bars is not None and list(bars.parsed["bars"]["date"]) == [date(2026, 10, 1), SESSION]
    request = FetchRequest("option_params__AAPL", "EQ:AAPL", SESSION)
    params = src.normalize(request, src.fetch(request) or b"")
    assert params is not None
    assert list(params.parsed["expirations"]["expiration"]) == [
        date(2026, 11, 20),
        date(2026, 12, 18),
    ]
    assert list(params.parsed["strikes"]["strike"]) == [230.0, 235.0]


@pytest.mark.allow_localhost
def test_probe_reports_an_unreachable_gateway() -> None:
    src = IbkrSource(IbkrMarketData(GatewayConfig("127.0.0.1", 1, 1)))
    assert (src.probe() or "").startswith("IB Gateway not reachable on 127.0.0.1:1")


def test_enrichment_kinds_round_trip_through_raw_json() -> None:
    ib = FakeIB(
        bars={"AAPL": [(date(2026, 10, 1), 1.0, 1.0, 1.0, 1.0, 0.0)]},
        iv={"AAPL": [(d, 0.2, 0.2, 0.2, 0.2, 0.0) for d in (date(2026, 9, 30), SESSION)]},
        hv={"AAPL": [(SESSION, 0.1, 0.1, 0.1, 0.1, 0.0)]},
        vols={"AAPL": (0.3, 0.25)},
    )
    src = IbkrSource(
        IbkrMarketData(GatewayConfig("127.0.0.1", 4002, 1, stream_wait_s=0.01),
                       ib_factory=lambda: ib)
    )  # fmt: skip
    src.open()

    def parsed(key: str, kind: str) -> pd.DataFrame:
        request = FetchRequest(key, None, SESSION)
        normalized = src.normalize(request, src.fetch(request) or b"")
        assert normalized is not None
        return normalized.parsed[kind]

    contracts = parsed("contracts__AAPL+ZZZZ", "contracts").set_index("symbol")
    assert contracts.loc["AAPL", "conid"] == 1004 and pd.isna(contracts.loc["ZZZZ", "conid"])
    hist = parsed("volhist__AAPL__1004__2026-10-01", "volhist")
    assert list(hist["date"]) == [SESSION]  # from the start date only
    assert hist.loc[0, "iv30_ibkr"] == 0.2 and hist.loc[0, "hv30_ibkr"] == 0.1
    vols = parsed("vols__AAPL:1004+ZZZZ:", "vols").set_index("symbol")
    assert vols.loc["AAPL", "iv30_ibkr"] == 0.3 and not vols.loc["ZZZZ", "listed"]


@pytest.mark.parametrize(
    "key",
    ["orders/AAPL", "bars", "option/AAPL/2026-11-20", "x/Y", "volhist__AAPL", "bars__A__B"],
)
def test_unknown_keys_are_rejected(key: str) -> None:
    with pytest.raises(ValueError, match="unknown IBKR request key"):
        parse_key(key)


def test_quotes_key_fetches_an_expiry_at_strikes_and_normalises_a_frame() -> None:
    ib = FakeIB(quotes={("20261120", 230.0, "C"): (5.0, 5.2)})
    src = source(ib)
    request = FetchRequest("quotes__AAPL__2026-11-20__230.0+235.0", None, None)
    with opened(src):
        payload = src.fetch(request)
    assert payload is not None
    normalized = src.normalize(request, payload)
    assert normalized is not None
    frame = normalized.parsed["quotes"]
    assert list(frame.columns)[:4] == ["strike", "right", "listed", "conid"]
    assert frame["listed"].tolist() == [True, False, False, False]
    assert frame.loc[0, "bid"] == 5.0 and pd.isna(frame.loc[1, "bid"])
    assert parse_key(request.key) == ("quotes", ["AAPL", "2026-11-20", "230.0+235.0"])
