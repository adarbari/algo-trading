from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from algotrade.config.site.settings import load_universe
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.reference.universe_build import (
    UniverseSettings,
    UniverseSources,
    build_universe,
    check_sp500,
    review_rows,
)
from algotrade_sources.framework.http import RetryPolicy
from algotrade_sources.vendors.nasdaq.symbol_directory import NasdaqTraderSource
from algotrade_sources.vendors.ssga.spy_holdings import SpyHoldingsSource
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import universe as fx

D1 = date(2026, 10, 1)
D2 = D1 + timedelta(days=1)
CLOCK = lambda: datetime(2026, 10, 2, 22, tzinfo=UTC)  # noqa: E731


def sources(nasdaq: bytes, other: bytes, options: bytes, spy: bytes) -> UniverseSources:
    files = {"nasdaqlisted": nasdaq, "otherlisted": other, "options": options}

    def transport(url: str) -> bytes:
        return next((v for k, v in files.items() if k in url), spy)

    return UniverseSources(
        NasdaqTraderSource(http_for(transport, RetryPolicy(tries=1))),
        SpyHoldingsSource(http_for(transport)),
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
            ("SCHO", "Schwab Short-Term U.S. Treasury ETF", "P", "Y"),
            ("HDGE", "Ranger Equity Bear Bear ETF", "P", "Y"),
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
            ("SCHO", "Schwab Short-Term U.S. Treasury ETF", "P", "Y"),
            ("HDGE", "Ranger Equity Bear Bear ETF", "P", "Y"),
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
    first = build_universe(task_ctx(writer, reader, CLOCK), DAY1, SETTINGS, D1)
    assert first.status is RunStatus.COMPLETE
    ref1 = reader.table("instruments/reference", D1).set_index("symbol")  # type: ignore[union-attr]
    assert ref1.loc["ABR$D", "security_type"] == "PREFERRED"
    assert bool(ref1.loc["AAPL", "optionable"]) and bool(ref1.loc["BRK.B", "in_sp500"])
    universe1 = set(reader.table("universe", D1)["symbol"])  # type: ignore[index]
    # no test issue, preferred or SPY
    assert universe1 == {"AAPL", "BRK.B", "GONE", "SOXL", "TQQQ", "SCHO", "HDGE"}
    assert first.stats["leverage"] == {
        "override": 1,  # TQQQ
        "name_parsed": 1,  # SOXL: "Bull 3X"
        "name_rule": 2,  # SPY (no marker), SCHO ("Short-Term" excluded)
        "needs_review": 1,  # HDGE: "Bear", no stated leverage
        "not_etf": 5,
    }
    assert ref1.loc["SOXL", "leverage"] == 3.0 and ref1.loc["SOXL", "leverage_source"] == (
        "name_parsed"
    )

    second = build_universe(task_ctx(writer, reader, CLOCK), DAY2, SETTINGS, D2)
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
        {"symbol": "HDGE", "leverage": "", "tracks": "", "notes": "Ranger Equity Bear Bear ETF"}
    ]


def test_unmatched_index_members_make_the_run_partial() -> None:
    backend = MemoryBackend()
    odd = sources(
        fx.nasdaq([("AAPL", "Apple", "N", "N")]),
        fx.other([("B", "B Corp", "N", "N")]),
        fx.options(["AAPL"]),
        fx.spy(["MISSN"]),
    )
    record = build_universe(
        task_ctx(StoreWriter(backend), StoreReader(backend), CLOCK), odd, SETTINGS, D1
    )
    assert record.status is RunStatus.PARTIAL
    assert record.stats["sp500_unmatched"] == ["MISSN"]


def test_universe_settings_from_site_config() -> None:
    store = MemoryConfigStore(
        {("site", "settings", "universe"): {"source": "nasdaq_trader", "exclude_symbols": ["spy"]}},
        {"leveraged_etfs": [{"symbol": "TQQQ", "leverage": "3"}]},
    )
    settings = load_universe(store)
    assert (settings.source, settings.exclude_symbols) == ("nasdaq_trader", frozenset({"SPY"}))
    assert settings.overrides[0]["symbol"] == "TQQQ"
    assert load_universe(MemoryConfigStore({})).source == "csv_import"


def test_review_rows_list_only_active_unknown_leverage() -> None:
    import pandas as pd  # noqa: PLC0415

    frame = pd.DataFrame(
        {
            "symbol": ["HDGE", "OLD", "SOXL"],
            "name": ["Ranger Equity Bear Bear ETF", "Old Bear Fund", "Direxion Bull 3X"],
            "leverage_source": ["needs_review", "needs_review", "name_parsed"],
            "status": ["ACTIVE", "DELISTED", "ACTIVE"],
        }
    )
    assert review_rows(frame) == [
        {"symbol": "HDGE", "leverage": "", "tracks": "", "notes": "Ranger Equity Bear Bear ETF"}
    ]


def sp500_world() -> tuple[
    StoreWriter, StoreReader, list[str], Callable[[list[str]], UniverseSources]
]:
    names = [f"A{a}{b}" for a in "ABCDEFGHIJ" for b in "ABCDEFGHIJKL"]  # 120 listed stocks
    listed = fx.nasdaq([(n, f"{n} Common Stock", "N", "N") for n in names])
    backend = MemoryBackend()

    def day(members: list[str]) -> UniverseSources:
        return sources(
            listed, fx.other([("SPY", "SPDR", "P", "Y")]), fx.options([names[0]]), fx.spy(members)
        )

    return StoreWriter(backend), StoreReader(backend), names, day


def flags(reader: StoreReader, session: date) -> set[str]:
    reference = reader.table("instruments/reference", session)
    assert reference is not None
    return set(reference.loc[reference["in_sp500"].astype(bool), "symbol"])


def test_a_cut_short_sp500_list_keeps_the_membership_and_does_not_fail_the_build() -> None:
    """The first guard raised, so the whole universe build was FAILED (no reference, no universe,
    no listings that day) with no way to accept a real change. Now only the membership holds."""
    writer, reader, names, day = sp500_world()

    def build(members: list[str], session: date, accept: bool = False) -> RunRecord:
        return build_universe(
            task_ctx(writer, reader, CLOCK), day(members), SETTINGS, session, accept
        )

    assert build(names, D1).stats["sp500_members"] == len(names)
    short = build(names[:100], D2)  # 20 of 120 gone: not an index change
    assert short.status is RunStatus.PARTIAL and "20 left, 0 joined" in short.stats["sp500_held"]
    assert short.stats["sp500_members"] == 100  # what the file said
    assert flags(reader, D2) == set(names)  # the flags are as they were
    assert reader.table("events/index_change", D2) is None  # no removal events
    assert reader.table("universe", D2) is not None  # everything else was built
    ok = build(names[:110], D2 + timedelta(days=1))  # 10 of 120: a plausible change
    assert ok.stats["events"]["index_change"] == {"sp500_removed": 10}
    assert ok.status is RunStatus.COMPLETE and flags(reader, D2 + timedelta(days=1)) == set(
        names[:110]
    )


def test_accept_sp500_applies_a_large_change() -> None:
    writer, reader, names, day = sp500_world()
    build_universe(task_ctx(writer, reader, CLOCK), day(names), SETTINGS, D1)
    accepted = build_universe(
        task_ctx(writer, reader, CLOCK), day(names[:100]), SETTINGS, D2, accept_sp500=True
    )
    assert accepted.status is RunStatus.COMPLETE and "sp500_held" not in accepted.stats
    assert accepted.stats["events"]["index_change"] == {"sp500_removed": 20}
    assert flags(reader, D2) == set(names[:100])


def test_the_registry_task_takes_the_accept_flag() -> None:
    from algotrade_ingestion.tasks.framework.registry import TASKS  # noqa: PLC0415

    flags_of = {f for param in TASKS["universe-build"].params for f in param.flags}
    assert "--accept-sp500" in flags_of


def members(count: int, start: int = 0) -> set[str]:
    return {f"M{i:03d}" for i in range(start, start + count)}


def reference_of(symbols: set[str]) -> pd.DataFrame:
    return pd.DataFrame({"symbol": sorted(symbols), "in_sp500": True})


def test_the_sp500_check_compares_with_the_last_snapshot() -> None:
    assert check_sp500(members(3), None) is None  # the first build has nothing to compare with
    assert check_sp500(members(1), reference_of(members(50))) is None  # test-sized: no index list
    real = reference_of(members(500))
    assert check_sp500(members(500), real) is None
    assert check_sp500(members(500, 8), real) is None  # 8 swapped: a quarterly rebalance
    assert check_sp500(members(488), real) is None  # 12 gone: the limit
    assert check_sp500(members(500), pd.DataFrame({"instrument_id": []})) is None  # no flags yet


def test_the_sp500_check_flags_a_cut_short_file_or_a_big_change() -> None:
    real = reference_of(members(500))
    cut = check_sp500(members(455), real)  # 45 gone: the 10% band let this through
    assert cut is not None and "45 left" in cut[0] and cut[1] == members(500)
    assert check_sp500(members(487), real) is not None  # 13 gone: more than a day's change
    assert check_sp500(members(500, 15), real) is not None  # 15 in, 15 out
    assert check_sp500(members(440), real) is not None  # under 90%


def test_an_empty_listing_file_fails_closed() -> None:
    import pytest  # noqa: PLC0415

    backend = MemoryBackend()
    empty = sources(
        fx.nasdaq([("AAPL", "Apple", "N", "N")]), fx.other([]), fx.options([]), fx.spy(["AAPL"])
    )
    with pytest.raises(ValueError, match="otherlisted had no rows"):
        build_universe(
            task_ctx(StoreWriter(backend), StoreReader(backend), CLOCK), empty, SETTINGS, D1
        )


def test_registry_task_builds_and_writes_the_review_file(tmp_path: Path) -> None:
    from algotrade_ingestion.tasks.framework.registry import run_task  # noqa: PLC0415

    backend = MemoryBackend()
    ctx = task_ctx(
        StoreWriter(backend),
        clock=CLOCK,
        sources={"nasdaq_trader": DAY1.nasdaq_trader, "spy_holdings": DAY1.spy_holdings},
    )
    ctx.configs = MemoryConfigStore({("site", "settings", "universe"): {"source": "nasdaq_trader"}})
    out = tmp_path / "review" / "leveraged.csv"
    record = run_task("universe-build", ctx, {"session": D1, "review_out": out})
    assert record.stats["review_out"] == str(out)
    assert out.read_text().startswith("symbol,leverage,tracks,notes")
