"""Task entries for reference and listing tasks: universe, company details, shares (ADR 0019)."""

from datetime import date
from pathlib import Path

from algotrade.config.site.settings import load_universe
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework import source_guards
from algotrade_ingestion.tasks.framework.params import Params, session_of, symbols
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.listings import index_membership, listing_history, winners_sample
from algotrade_ingestion.tasks.market import (
    etf_holdings,
)
from algotrade_ingestion.tasks.reference import (
    company_details,
    shares,
    universe_build,
    universe_import,
)
from algotrade_sources.framework.base import (
    DirectorySource,
)


def run_universe_build(ctx: TaskContext, p: Params) -> RunRecord:
    assert ctx.configs is not None
    settings = load_universe(ctx.configs)
    trader = ctx.sources["nasdaq_trader"]
    if not isinstance(trader, DirectorySource):
        raise TypeError("nasdaq_trader must be a DirectorySource (listing + options files)")
    sources = universe_build.UniverseSources(
        trader,
        ctx.sources["spy_holdings"],
        ctx.sources.get("massive_tickers"),
    )
    record = universe_build.build_universe(
        ctx, sources, settings, session_of(p), bool(p.get("accept_sp500"))
    )
    if p.get("review_out"):
        universe_build.write_review(ctx.reader, session_of(p), p["review_out"])
        record.stats["review_out"] = str(p["review_out"])
    if p.get("figi_review_out"):
        path = Path(p["figi_review_out"])
        rows = universe_build.write_figi_review(ctx.reader, session_of(p), path)
        record.stats["figi_review_out"] = {"path": str(path), "rows": rows}
    return record


def run_universe_mode(ctx: TaskContext) -> str | None:
    mode = load_universe(ctx.configs).source if ctx.configs is not None else "csv_import"
    return None if mode == "nasdaq_trader" else f"skipped: {mode} mode"


def run_universe_csv(ctx: TaskContext, p: Params) -> RunRecord:
    files = [universe_import.UniverseFile(Path(p["stocks"]), "STOCK")]
    if p.get("etfs"):
        files.append(universe_import.UniverseFile(Path(p["etfs"]), "ETF"))
    return universe_import.import_universe(ctx, files, str(p["version"]), session_of(p))


def run_company_details(ctx: TaskContext, p: Params) -> RunRecord:
    sources = company_details.CompanySources(
        ctx.sources["sec_tickers"], ctx.sources["sec_submissions"], ctx.settings.sec_refresh_days
    )
    return company_details.ingest_company_details(
        ctx, sources, session_of(p), bool(p.get("force")), p.get("limit")
    )


def run_listing_history(ctx: TaskContext, p: Params) -> RunRecord:
    return listing_history.ingest_listing_history(
        ctx, ctx.sources["tiingo_listings"], session_of(p), ctx.sources.get("tiingo_meta")
    )


def run_index_membership(ctx: TaskContext, p: Params) -> RunRecord:
    return index_membership.ingest_index_membership(
        ctx, ctx.sources["sp500_history"], session_of(p)
    )


def run_winners_sample(ctx: TaskContext, p: Params) -> RunRecord:
    return winners_sample.ingest_winners_sample(
        ctx,
        ctx.sources["tiingo_prices"],
        session_of(p),
        Path(p["report"]) if p.get("report") else None,
        p.get("seed") or winners_sample.DEFAULT_SEED,
        p.get("limit"),
    )


def run_shares(ctx: TaskContext, p: Params) -> RunRecord:
    facts = ctx.sources["sec_company_facts"]
    sources = shares.SharesSources(
        facts,
        ctx.settings.sec_facts_refresh_days,
        ctx.settings.sec_statements_backfill_per_night,
        ctx.settings.sec_statements_priority_min_adv_usd,
        getattr(facts, "statements_tags_date", date.min),
    )
    return shares.ingest_shares(ctx, sources, session_of(p), bool(p.get("force")), p.get("limit"))


def run_etf_holdings(ctx: TaskContext, p: Params) -> RunRecord:
    issuers = source_guards.holdings_issuers(ctx)
    if not issuers:
        raise KeyError(
            f"task 'etf-holdings' needs one of the sources {list(source_guards.HOLDINGS_ISSUERS)}"
        )
    sources = etf_holdings.HoldingsSources(
        issuers,
        ctx.settings.etf.refresh_days,
        ctx.settings.etf.keep_top,
        ctx.settings.etf.fallback_scope,
        fallback_min_adv_usd=ctx.settings.etf.fallback_min_adv_usd,
    )
    limit = p.get("limit")
    if limit is None and p.get("nightly") and ctx.settings.etf.per_night > 0:
        limit = ctx.settings.etf.per_night  # the nightly reads a slice a night (per_night)
    return etf_holdings.ingest_etf_holdings(
        ctx, sources, session_of(p), bool(p.get("force")), limit, symbols(p)
    )
