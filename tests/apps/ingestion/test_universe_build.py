from datetime import UTC, date, datetime, timedelta

from algotrade.data import StoreReader
from algotrade.storage.backends.config_files import MemoryConfigStore
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.universe_build import (
    UniverseSettings,
    UniverseSources,
    build_universe,
    review_rows,
)
from algotrade_ingestion.pipeline import universe_settings
from algotrade_ingestion.sources.http import RetryPolicy
from algotrade_ingestion.sources.nasdaq_trader import NasdaqTraderSource
from algotrade_ingestion.sources.spy_holdings import SpyHoldingsSource
from tests import universe_fixture as fx

D1 = date(2026, 10, 1)
D2 = D1 + timedelta(days=1)
CLOCK = lambda: datetime(2026, 10, 2, 22, tzinfo=UTC)  # noqa: E731


def sources(nasdaq: bytes, other: bytes, options: bytes, spy: bytes) -> UniverseSources:
    files = {"nasdaqlisted": nasdaq, "otherlisted": other, "options": options}

    def transport(url: str) -> bytes:
        return next((v for k, v in files.items() if k in url), spy)

    return UniverseSources(
        NasdaqTraderSource(transport, lambda s: None, RetryPolicy(tries=1)),
        SpyHoldingsSource(transport, lambda s: None),
    )


DAY1 = sources(
    fx.nasdaq(
        [
            ("AAPL", "Apple Inc. - Common Stock", "N", "N"),
            ("ZTST", "Test Issue Co", "N", "Y"),
            ("TQQQ", "ProShares UltraPro QQQ", "Y", "N"),
            ("GONE", "Gone Corp Common Stock", "N", "N"),
        ]
    ),
    fx.other(
        [
            ("BRK.B", "Berkshire Hathaway Common Stock", "N", "N"),
            ("SPY", "SPDR S&P 500 ETF Trust", "P", "Y"),
            ("ABR$D", "Arbor Preferred Stock", "N", "N"),
            ("SOXL", "Direxion Daily Semiconductor Bull 3X ETF", "P", "Y"),
        ]
    ),
    fx.options(["AAPL", "SPY", "TQQQ"]),
    fx.spy(["AAPL", "BRK.B"]),
)
DAY2 = sources(
    fx.nasdaq(
        [
            ("AAPL", "Apple Inc. - Renamed Common Stock", "N", "N"),
            ("ZTST", "Test Issue Co", "N", "Y"),
            ("TQQQ", "ProShares UltraPro QQQ", "Y", "N"),
            ("NEWC", "New Co Common Stock", "N", "N"),
        ]
    ),
    fx.other(
        [
            ("BRK.B", "Berkshire Hathaway Common Stock", "N", "N"),
            ("SPY", "SPDR S&P 500 ETF Trust", "P", "Y"),
            ("ABR$D", "Arbor Preferred Stock", "N", "N"),
            ("SOXL", "Direxion Daily Semiconductor Bull 3X ETF", "P", "Y"),
        ]
    ),
    fx.options(["AAPL", "SPY", "TQQQ", "BRK.B"]),
    fx.spy(["AAPL", "NEWC"]),
)
SETTINGS = UniverseSettings(
    include_symbols=frozenset(),
    exclude_symbols=frozenset({"SPY"}),
    overrides=({"symbol": "TQQQ", "leverage": "3", "tracks": "Nasdaq-100"},),
)


def test_two_days_of_universe_builds() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    first = build_universe(writer, reader, DAY1, SETTINGS, D1, CLOCK)
    assert first.status is RunStatus.COMPLETE
    ref1 = reader.table("instruments/reference", D1).set_index("symbol")  # type: ignore[union-attr]
    assert ref1.loc["ABR$D", "security_type"] == "PREFERRED"
    assert bool(ref1.loc["AAPL", "optionable"]) and bool(ref1.loc["BRK.B", "in_sp500"])
    universe1 = set(reader.table("universe", D1)["symbol"])  # type: ignore[index]
    assert universe1 == {"AAPL", "BRK.B", "GONE", "SOXL", "TQQQ"}  # no test issue, preferred or SPY
    assert first.stats["leverage"] == {
        "not_etf": 5,
        "name_rule": 1,
        "needs_review": 1,
        "override": 1,
    }

    second = build_universe(writer, reader, DAY2, SETTINGS, D2, CLOCK)
    ref2 = reader.table("instruments/reference", D2).set_index("symbol")  # type: ignore[union-attr]
    assert ref2.loc["GONE", "status"] == "DELISTED"
    assert ref2.loc["GONE", "delisted_on"] == D2
    assert ref2.loc["AAPL", "first_seen"] == D1
    assert ref2.loc["NEWC", "first_seen"] == D2
    assert second.stats["events"]["reference_change"] == {
        "added": 1,
        "removed": 1,
        "renamed": 1,
        "optionable_changed": 1,
    }
    assert second.stats["events"]["index_change"] == {"sp500_added": 1, "sp500_removed": 1}
    index = reader.table("events/index_change", D2)
    assert index is not None and set(index["symbol"]) == {"NEWC", "BRK.B"}
    assert "GONE" not in set(reader.table("universe", D2)["symbol"])  # type: ignore[index]
    rows = review_rows(reader.table("instruments/reference", D2))  # type: ignore[arg-type]
    assert rows == [
        {
            "symbol": "SOXL",
            "leverage": "3",
            "tracks": "",
            "notes": "Direxion Daily Semiconductor Bull 3X ETF",
        }
    ]


def test_unmatched_index_members_make_the_run_partial() -> None:
    backend = MemoryBackend()
    odd = sources(
        fx.nasdaq([("AAPL", "Apple", "N", "N")]),
        fx.other([("B", "B Corp", "N", "N")]),
        fx.options(["AAPL"]),
        fx.spy(["MISSN"]),
    )
    record = build_universe(StoreWriter(backend), StoreReader(backend), odd, SETTINGS, D1, CLOCK)
    assert record.status is RunStatus.PARTIAL
    assert record.stats["sp500_unmatched"] == ["MISSN"]


def test_universe_settings_from_site_config() -> None:
    store = MemoryConfigStore(
        {("site", "settings", "universe"): {"source": "nasdaq_trader", "exclude_symbols": ["spy"]}},
        {"leveraged_etfs": [{"symbol": "TQQQ", "leverage": "3"}]},
    )
    mode, settings = universe_settings(store)
    assert (mode, settings.exclude_symbols) == ("nasdaq_trader", frozenset({"SPY"}))
    assert settings.overrides[0]["symbol"] == "TQQQ"
    assert universe_settings(MemoryConfigStore({}))[0] == "csv_import"


def test_review_row_sign_for_inverse_names() -> None:
    import pandas as pd  # noqa: PLC0415

    frame = pd.DataFrame(
        {
            "symbol": ["SQQQ", "NOX"],
            "name": ["ProShares UltraPro Short QQQ 3x", "Ultra Fund"],
            "leverage_source": "needs_review",
            "status": "ACTIVE",
        }
    )
    assert [r["leverage"] for r in review_rows(frame)] == ["-3", ""]


def test_an_empty_listing_file_fails_closed() -> None:
    import pytest  # noqa: PLC0415

    backend = MemoryBackend()
    empty = sources(
        fx.nasdaq([("AAPL", "Apple", "N", "N")]), fx.other([]), fx.options([]), fx.spy(["AAPL"])
    )
    with pytest.raises(ValueError, match="otherlisted had no rows"):
        build_universe(StoreWriter(backend), StoreReader(backend), empty, SETTINGS, D1, CLOCK)
