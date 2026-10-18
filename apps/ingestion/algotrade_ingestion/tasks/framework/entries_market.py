"""Task entries for market data: earnings, bars, filings, rates, chains, rollups, macro (ADR 19)."""

from datetime import timedelta

from algotrade.config.site.events.releases import load_macro_releases
from algotrade.config.site.settings import load_macro
from algotrade.core.time.calendar import sessions_between
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.derived import market_rollups, outcomes, rollups
from algotrade_ingestion.tasks.events import filings
from algotrade_ingestion.tasks.framework.params import Params, session_of, symbols
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.macro import calendar as macro_calendar
from algotrade_ingestion.tasks.macro import series as macro_series
from algotrade_ingestion.tasks.market import (
    bars,
    bars_history,
    corporate_actions,
    earnings,
    fund_nav,
    option_chains,
    rates,
)


def run_earnings(ctx: TaskContext, p: Params) -> RunRecord:
    session = session_of(p)
    source = ctx.sources["nasdaq_earnings"]
    if p.get("history_from"):
        end = p.get("history_to") or session
        return earnings.backfill_earnings(ctx, source, session, p["history_from"], end)
    days = p.get("days") or ctx.settings.earnings_days
    start = p.get("start")
    if start is None:
        # Also the last week: those reports now carry the reported EPS and surprise, and
        # `last_earnings_date` stays current. An explicit --start is taken as given.
        back = ctx.settings.earnings_lookback_days
        start, days = session - timedelta(days=back), days + back
    return earnings.ingest_earnings(ctx, source, session, start, days=days)


def run_bars(ctx: TaskContext, p: Params) -> RunRecord:
    session = session_of(p)
    # Exchange sessions in the window; an explicit non-session date is fetched as asked.
    sessions = sessions_between(p.get("start") or session, p.get("end") or session) or [session]
    return bars.ingest_daily_bars(ctx, ctx.sources["massive_bars"], sessions, bool(p.get("force")))


def run_bars_history(ctx: TaskContext, p: Params) -> RunRecord:
    assert ctx.configs is not None  # the scope list is read from the site configs
    # The scope (the list, fund references, with --include-tiers the tier names) is resolved by
    # the task through ``services.events``; --symbols only adds to it.
    since = p.get("since") or bars_history.DEFAULT_SINCE
    return bars_history.ingest_bars_history(
        ctx,
        ctx.sources["tiingo_prices"],
        symbols(p),
        since,
        p.get("until") or session_of(p),
        bool(p.get("force")),
        p.get("limit"),
        bool(p.get("include_tiers")),
        p.get("fill"),
        bool(p.get("from_listings")),
    )


def run_fund_nav(ctx: TaskContext, p: Params) -> RunRecord:
    return fund_nav.ingest_fund_nav(
        ctx,
        ctx.sources["tiingo_nav"],
        ctx.sources["tiingo_nav_tickers"],
        p.get("end") or session_of(p),
        p.get("start"),
        symbols(p),
        bool(p.get("force")),
        p.get("limit"),
    )


def run_filings(ctx: TaskContext, p: Params) -> RunRecord:
    # The names are the session's universe without funds, resolved by the task; --symbols
    # narrows them.
    return filings.ingest_filings(
        ctx,
        ctx.sources["sec_filings"],
        session_of(p),
        symbols(p),
        p.get("since"),
        p.get("limit"),
        ctx.sources["sec_daily_index"],
    )


def run_rates(ctx: TaskContext, p: Params) -> RunRecord:
    end = p.get("end") or session_of(p)
    start = p.get("start") or end - timedelta(ctx.settings.treasury_lookback_days - 1)
    return rates.ingest_rates(ctx, ctx.sources["treasury"], start, end, bool(p.get("force")))


def run_corporate_actions(ctx: TaskContext, p: Params) -> RunRecord:
    session = session_of(p)
    before, after = ctx.settings.actions_window
    start = p.get("start") or session + timedelta(before)
    end = p.get("end") or session + timedelta(after)
    source = ctx.sources["massive_corporate_actions"]
    return corporate_actions.ingest_corporate_actions(ctx, source, session, start, end)


def run_chains(ctx: TaskContext, p: Params) -> RunRecord:
    session = session_of(p)
    symbols = [s for s in str(p.get("symbols") or "").split(",") if s.strip()]
    underlyings = option_chains.select_underlyings(ctx.reader, session, symbols)
    workers = int(p.get("workers") or ctx.settings.cboe_workers)
    return option_chains.ingest_option_chains(
        ctx,
        ctx.sources["cboe"],
        underlyings,
        session,
        option_chains.ChainJobConfig(
            workers,
            priority_symbols=ctx.settings.cboe_priority_symbols,
            probe=bool(p.get("probe")),  # the nightly, while the step may still WAIT
            probe_max_stale_share=2 * ctx.settings.max_chain_stale_share,
        ),
    )


def run_rollups(ctx: TaskContext, p: Params) -> RunRecord:
    return rollups.compute_rollups(
        ctx, session_of(p), p.get("start"), p.get("end"), symbols(p, "only")
    )


def run_market_rollups(ctx: TaskContext, p: Params) -> RunRecord:
    return market_rollups.compute_market_rollups(
        ctx, session_of(p), p.get("start"), p.get("end"), symbols(p, "only")
    )


def run_outcomes(ctx: TaskContext, p: Params) -> RunRecord:
    return outcomes.compute_outcomes(ctx, session_of(p), p.get("start"), p.get("end"))


def run_macro(ctx: TaskContext, p: Params) -> RunRecord:
    assert ctx.configs is not None
    return macro_series.ingest_macro(
        ctx, load_macro(ctx.configs), session_of(p), symbols(p, "only"), p.get("since")
    )


def run_macro_calendar(ctx: TaskContext, p: Params) -> RunRecord:
    assert ctx.configs is not None
    return macro_calendar.ingest_macro_calendar(
        ctx, load_macro_releases(ctx.configs), session_of(p), symbols(p, "only")
    )
