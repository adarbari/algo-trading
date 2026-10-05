"""The etf-holdings task over the three issuer adapters and recorded responses (no network)."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.data.funds.holdings import etf_holdings
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.market.etf_holdings import (
    HoldingsSources,
    active_etfs,
    assign,
    ingest_etf_holdings,
)
from algotrade_sources.framework.base import HoldingsSource
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.ishares.etf_holdings import IsharesHoldings, no_file
from algotrade_sources.vendors.proshares.etf_holdings import ProsharesHoldings
from algotrade_sources.vendors.sec.nport_holdings import NportHoldings
from algotrade_sources.vendors.ssga.etf_holdings import SsgaHoldings
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.stored_frames import stamped

DAY = date(2026, 10, 2)
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources"
SSGA, ISHARES, SEC = FIXTURES / "ssga", FIXTURES / "ishares", FIXTURES / "sec"
PROSHARES = FIXTURES / "proshares" / "psdlyhld_sample.csv"
KINDS = {
    "XLK": "ETF", "IVV": "ETF", "IWM": "ETF", "SLV": "ETF", "VTI": "ETF", "QQQ": "ETF",
    "AGG": "ETF", "OLD": "ETF", "ETNX": "ETN", "VUG": "ETF",
    "NVDA": "COMMON_STOCK", "AAPL": "COMMON_STOCK", "MSFT": "COMMON_STOCK",
}  # fmt: skip


NOW = [datetime(2026, 10, 2, 22, tzinfo=UTC)]


def clock() -> datetime:
    """Every call is a second later, so runs get their own ids and knowledge times."""
    NOW[0] += timedelta(seconds=1)
    return NOW[0]


def ssga(down: bool = False, files: Mapping[str, bytes] | None = None) -> SsgaHoldings:
    """``files``: fund file name (``xlk.xlsx``) -> bytes served instead of the recorded one."""

    def transport(url: str) -> bytes:
        if down:
            raise HttpError(500)
        if "fundfinder" in url:
            return (SSGA / "fundfinder.json").read_bytes()
        name = url.rsplit("-", 1)[1]
        return (files or {}).get(name) or (SSGA / f"holdings-daily-us-en-{name}").read_bytes()

    return SsgaHoldings(http_for(transport, RetryPolicy(tries=1)))


def ishares() -> IsharesHoldings:
    def transport(url: str) -> bytes:
        if "product-screener" in url:
            return (ISHARES / "product-screener.json").read_bytes()
        slug = {"sp-500": "IVV", "russell-2000": "IWM", "bond-market": "AGG", "eafe": "EFA"}
        found = [fund for part, fund in slug.items() if part in url]
        if not found:
            raise HttpError(400)  # the silver trust: no file
        return (ISHARES / f"{found[0]}_latest-holdings.csv").read_bytes()

    return IsharesHoldings(http_for(transport, RetryPolicy(tries=1, not_found=no_file)))


def nport() -> NportHoldings:
    def transport(url: str) -> bytes:
        files = {
            "company_tickers_mf": SEC / "company_tickers_mf.json",
            "submissions": SEC / "submissions_vanguard_index_funds.json",
            "index-headers": SEC / "nport_header_0000036405-26-000480.html",
            "primary_doc": SEC / "nport_total_stock_market_trimmed.xml",
        }
        return next(path for part, path in files.items() if part in url).read_bytes()

    return NportHoldings(http_for(transport, RetryPolicy(tries=1)))


def world(
    keep_top: int = 100,
    refresh_days: int = 7,
    scope: str = "optionable",
    geared: tuple[str, ...] = (),
) -> tuple[StoreWriter, HoldingsSources]:
    writer = StoreWriter(MemoryBackend())
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "EQ", "security_type": kind,
         "multiplier": 1.0, "status": "DELISTED" if s == "OLD" else "ACTIVE",
         "optionable": s != "VUG", "is_leveraged": s in geared}
        for s, kind in KINDS.items()
    ]  # fmt: skip
    writer.write_table("instruments/reference", DAY, "ref", stamped(rows, DAY, "ref"))
    sources = HoldingsSources([ssga(), ishares(), nport()], refresh_days, keep_top, scope, False)
    return writer, sources  # the recorded files are trimmed, so their weights do not add up


def run(
    writer: StoreWriter,
    sources: HoldingsSources,
    session: date = DAY,
    force: bool = False,
    limit: int | None = None,
    only: tuple[str, ...] = (),
) -> RunRecord:
    ctx = task_ctx(writer, clock=clock)
    return ingest_etf_holdings(ctx, sources, session, force, limit, only)


def holdings(writer: StoreWriter, symbol: str, on: date = DAY) -> pd.DataFrame:
    return etf_holdings(StoreReader(writer._backend), f"EQ:{symbol}", on)


def test_the_universe_etfs_are_active_etfs_only() -> None:
    reference = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B", "EQ:C", "EQ:D"],
            "symbol": ["A", "B", "C", "D"],
            "security_type": ["ETF", "ETN", "ETF", "COMMON_STOCK"],
            "status": ["ACTIVE", "ACTIVE", "DELISTED", "ACTIVE"],
        }
    )
    assert list(active_etfs(reference)["symbol"]) == ["A"]


def test_a_fund_is_read_from_the_first_issuer_that_lists_it() -> None:
    first, second = ssga(), ishares()
    listed = {first.name: {"XLK", "BOTH"}, second.name: {"BOTH", "IVV"}}
    owner = assign(["BOTH", "IVV", "XLK", "NONE"], [first, second], listed)
    assert {s: o.name for s, o in owner.items()} == {
        "BOTH": first.name, "IVV": second.name, "XLK": first.name,
    }  # fmt: skip
    assert all(isinstance(o, HoldingsSource) for o in owner.values())


def test_every_issuer_reads_its_funds_and_the_stats_say_what_is_covered() -> None:
    writer, sources = world()
    record = run(writer, sources)
    assert record.status is RunStatus.COMPLETE  # a fund with no file is not a failure
    stats = record.stats
    assert stats["etfs"] == 8  # OLD is delisted, ETNX is an ETN
    assert stats["covered"] == {"ssga_holdings": 1, "ishares_holdings": 4, "sec_nport": 2}
    assert (stats["out_of_scope"], stats["uncovered"]) == (1, 0)  # VUG: N-PORT, not optionable
    assert (stats["read"], stats["no_file"], stats["failed_count"]) == (5, 2, 0)
    assert record.items["SLV"].startswith("NO_FILE")  # the silver trust answers 400
    assert record.items["QQQ"].startswith("NO_FILE")  # N-PORT lists it, no filing in the list
    assert record.items["XLK"] == "OK: 12 lines as of 2026-10-01"


def test_rows_are_ranked_trimmed_counted_and_linked_to_the_universe() -> None:
    writer, sources = world(keep_top=3)
    run(writer, sources)
    xlk = holdings(writer, "XLK")
    assert list(xlk["rank"]) == [1, 2, 3] and set(xlk["holdings_count"]) == {12}
    assert list(xlk["holding_symbol"]) == ["NVDA", "AAPL", "MSFT"]
    assert list(xlk["holding_id"]) == ["EQ:NVDA", "EQ:AAPL", "EQ:MSFT"]
    assert set(xlk["as_of"]) == {date(2026, 10, 1)} and set(xlk["source"]) == {"ssga_holdings"}
    assert xlk["weight"].is_monotonic_decreasing
    assert xlk["weight"].iloc[0] == pytest.approx(0.1547, abs=1e-4)


def test_lines_outside_the_universe_keep_their_name_only() -> None:
    writer, sources = world(keep_top=3)
    run(writer, sources)
    iwm = holdings(writer, "IWM")
    assert list(iwm["holding_symbol"]) == ["XTSLA", "TWST", "MOG.A"]  # the issuer's tickers
    assert iwm["holding_id"].isna().all()  # none of them is in this universe
    assert set(iwm["source"]) == {"ishares_holdings"}


def test_a_fund_without_tickers_is_linked_through_cusips_other_issuers_printed() -> None:
    writer, sources = world(keep_top=3)
    run(writer, sources)
    vti = holdings(writer, "VTI")
    assert list(vti["holding_name"]) == ["NVIDIA Corp", "Apple Inc", "Microsoft Corp"]
    assert list(vti["holding_symbol"]) == ["NVDA", "AAPL", "MSFT"]  # N-PORT printed none
    assert list(vti["holding_id"]) == ["EQ:NVDA", "EQ:AAPL", "EQ:MSFT"]
    assert set(vti["as_of"]) == {date(2026, 6, 30)} and set(vti["holdings_count"]) == {5}


def test_bond_lines_have_no_instrument_to_link() -> None:
    writer, sources = world()
    run(writer, sources)
    agg = holdings(writer, "AGG")
    assert len(agg) == 5 and agg["holding_id"].isna().all() and agg["holding_symbol"].isna().all()
    assert agg["identifier"].iloc[0] == "066922519"


def test_funds_are_not_reread_inside_their_window_and_n_port_waits_longer() -> None:
    writer, sources = world()
    run(writer, sources)
    again = run(writer, sources)  # the same night: nothing is due, funds with no file included
    assert again.stats["requested"] == 0 and again.stats["rows"] == 0
    week = run(writer, sources, DAY + timedelta(days=8))
    daily = {"XLK", "IVV", "IWM", "AGG", "SLV"}  # daily files, and a fund with no file
    assert daily <= set(week.items)  # all due a window later (the N-PORT funds wait for 30 days)
    quarterly = run(writer, sources, DAY + timedelta(days=9))
    assert "VTI" not in quarterly.items or "VTI" in week.items  # read at most once per 30 days
    month = run(writer, sources, DAY + timedelta(days=62))
    assert "VTI" in month.items


def test_a_reread_stores_another_run_and_readers_see_one_set_of_rows() -> None:
    writer, sources = world()
    run(writer, sources)
    run(writer, sources, DAY + timedelta(days=8), force=True)
    after = holdings(writer, "XLK", DAY + timedelta(days=8))
    assert len(after) == 12 and set(after["as_of"]) == {date(2026, 10, 1)}
    assert len(holdings(writer, "XLK", DAY)) == 12


def test_an_issuer_whose_directory_fails_makes_the_run_partial_not_empty() -> None:
    writer, _ = world()
    sources = HoldingsSources([ssga(down=True), ishares(), nport()], 7, 100, "optionable", False)
    record = run(writer, sources)
    assert record.status is RunStatus.PARTIAL
    assert record.items["directory:ssga_holdings"].startswith("FETCH_ERROR")
    assert record.stats["covered"]["ssga_holdings"] == 0 and record.stats["uncovered"] == 1
    assert holdings(writer, "XLK").empty and not holdings(writer, "IVV").empty


def test_tickers_and_limit_narrow_a_run() -> None:
    writer, sources = world()
    only = run(writer, sources, only=("xlk", "ivv"))
    assert sorted(k for k in only.items if not k.startswith("directory")) == ["IVV", "XLK"]
    writer2, sources2 = world()
    limited = run(writer2, sources2, limit=1)
    assert limited.stats["requested"] == 1 and limited.stats["deferred_by_limit"] == 6


def test_the_fallback_scope_decides_which_funds_n_port_is_read_for() -> None:
    everything = run(*world(scope="all"))
    assert everything.stats["covered"]["sec_nport"] == 3 and everything.stats["out_of_scope"] == 0
    nothing = run(*world(scope="off"))
    assert nothing.stats["covered"]["sec_nport"] == 0 and nothing.stats["out_of_scope"] == 3
    assert "VTI" not in nothing.items


def write_adv(writer: StoreWriter, adv: Mapping[str, float]) -> None:
    """``price_stats`` rows on the session before ``DAY`` (the nightly rolls up after this step)."""
    day = DAY - timedelta(days=1)
    rows = [{"instrument_id": f"EQ:{s}", "adv_usd_20d": v, "close": 50.0} for s, v in adv.items()]
    writer.write_table("rollups/instrument/price_stats@v2", day, "r", stamped(rows, day, "r"))


def test_the_liquid_scope_adds_funds_that_trade_enough_to_the_optionable_ones() -> None:
    writer, sources = world(scope="liquid")
    write_adv(writer, {"VUG": 9_000_000.0, "VTI": 10.0, "QQQ": 10.0})  # VUG: N-PORT, not optionable
    record = run(writer, sources)
    assert record.stats["fallback_scope"] == "liquid" and record.stats["out_of_scope"] == 0
    assert record.status is RunStatus.COMPLETE
    assert "VUG" in record.items  # asked of N-PORT (the recorded trust has no filing for it)
    quiet_writer, quiet = world(scope="liquid")
    write_adv(quiet_writer, {"VUG": 4_999_999.0})  # just under the default $5M
    quiet_run = run(quiet_writer, quiet)
    assert quiet_run.stats["out_of_scope"] == 1 and "VUG" not in quiet_run.items
    assert quiet_run.status is RunStatus.COMPLETE
    low_writer, low = world(scope="liquid")
    write_adv(low_writer, {"VUG": 4_999_999.0})
    lowered = run(low_writer, replace(low, fallback_min_adv_usd=1_000_000.0))
    assert lowered.stats["out_of_scope"] == 0 and "VUG" in lowered.items


def test_the_liquid_scope_without_price_stats_reads_the_optionable_funds_and_says_so() -> None:
    writer, sources = world(scope="liquid")  # no rollups stored yet (a new store)
    record = run(writer, sources)
    assert record.stats["out_of_scope"] == 1 and "VUG" not in record.items
    assert record.stats["fallback_adv_missing"] is True
    assert (
        record.status is RunStatus.COMPLETE
    )  # not a fault of this run: the nightly rolls up later
    writer2, sources2 = world(scope="liquid")
    write_adv(writer2, {"VUG": 1.0})
    assert run(writer2, sources2).stats["fallback_adv_missing"] is False


def test_force_rereads_covered_funds() -> None:
    writer, sources = world()
    run(writer, sources)
    forced = run(writer, sources, force=True)
    assert forced.stats["requested"] == 7


def test_proshares_funds_are_read_from_the_issuers_daily_file_with_the_sum_checked() -> None:
    """VIXY is long-only: its weights add up to 100% and pass the check. UVXY is leveraged and
    SVXY inverse: their sums are not 100%, which the check skips for geared funds."""
    writer = StoreWriter(MemoryBackend())
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "EQ", "security_type": "ETF",
         "multiplier": 1.0, "status": "ACTIVE", "optionable": True,
         "is_leveraged": s == "UVXY", "is_inverse": s == "SVXY"}
        for s in ("VIXY", "UVXY", "SVXY")
    ]  # fmt: skip
    writer.write_table("instruments/reference", DAY, "ref", stamped(rows, DAY, "ref"))
    proshares = ProsharesHoldings(
        http_for(lambda url: PROSHARES.read_bytes(), RetryPolicy(tries=1))
    )
    sources = HoldingsSources([proshares], 7, 100, "liquid", True)  # the weight-sum check is on
    record = run(writer, sources)
    assert record.status is RunStatus.COMPLETE, record.stats["failed"]
    assert record.stats["covered"] == {"proshares_holdings": 3}
    assert all(record.items[s].startswith("OK") for s in ("VIXY", "UVXY", "SVXY"))
    vixy = holdings(writer, "VIXY")
    assert set(vixy["source"]) == {"proshares_holdings"} and vixy["weight"].sum() == pytest.approx(
        1
    )
    assert holdings(writer, "SVXY")["weight"].min() < 0
