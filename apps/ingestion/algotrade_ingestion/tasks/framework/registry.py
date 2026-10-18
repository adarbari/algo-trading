"""The ingestion task registry: every task declared ONCE (ADR 0019).

A ``Task`` names what it writes (must match the ``[[table]]`` producers in
``architecture/tables.toml``), the sources it needs from ``TaskContext.sources``, the
site settings section it reads, its parameters (which the CLI turns into flags) and its
``run(ctx, params)`` entry. Defaults that come from settings (corporate-actions window,
earnings days, chain workers) are applied here, so the CLI and nightly cannot drift.

``algotrade-ingest <task>`` and ``algotrade-ingest run <task>`` both dispatch here; the
nightly workflow is an ordered list of these names (``workflows/nightly/nightly.py``).
"""

from datetime import date
from pathlib import Path

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.analyst import probe as analyst_probe
from algotrade_ingestion.tasks.analyst import snapshot as analyst_snapshot
from algotrade_ingestion.tasks.derived import history_copy, market_rollups, outcomes, rollups
from algotrade_ingestion.tasks.events import filings
from algotrade_ingestion.tasks.framework import (
    entries_market,
    entries_ops,
    entries_reference,
    source_guards,
)
from algotrade_ingestion.tasks.framework.params import (
    FROM,
    SESSION,
    TO,
    Param,
    Params,
    Task,
    session_of,
)
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.listings import index_membership, listing_history, winners_sample
from algotrade_ingestion.tasks.macro import calendar as macro_calendar
from algotrade_ingestion.tasks.macro import series as macro_series
from algotrade_ingestion.tasks.maintenance import (
    bar_quality,
    golden,
    migrate_ids,
    purge,
    quality,
    retire_features,
)
from algotrade_ingestion.tasks.market import (
    bars,
    bars_history,
    corporate_actions,
    earnings,
    etf_holdings,
    ibkr_iv,
    option_chains,
    rates,
)
from algotrade_ingestion.tasks.profile import descriptions
from algotrade_ingestion.tasks.reference import (
    company_details,
    ibkr_contracts,
    shares,
    universe_build,
    universe_import,
)
from algotrade_ingestion.tasks.verification import verify

__all__ = (
    "FROM",
    "SESSION",
    "TASKS",
    "TO",
    "Param",
    "Params",
    "Task",
    "run_task",
    "session_of",
    "task",
)

GOLDEN_DIR = Path("datasets/golden")
FIGI_REVIEW_OUT = Path("var/figi_review.csv")


# ----------------------------------------------------------------------------- the registry

UNIVERSE_TABLES = (
    "universe",
    "instruments/reference",
    "instruments/symbol_history",
    "instruments/id_map",
    "events/reference_change",
    "events/index_change",
)

TASKS: dict[str, Task] = {
    t.name: t
    for t in (
        Task(
            "universe-build",
            "build the universe from Nasdaq Trader + SPY holdings",
            universe_build,
            UNIVERSE_TABLES,
            entries_reference.run_universe_build,
            sources=("nasdaq_trader", "spy_holdings"),
            optional_sources=("massive_tickers",),
            settings="universe.toml",
            params=(
                SESSION,
                Param("review_out", ("--review-out",), Path, "write leverage candidates (CSV)"),
                Param(
                    "accept_sp500",
                    ("--accept-sp500",),
                    None,
                    "apply an S&P 500 list that differs a lot from the last snapshot",
                ),
                Param(
                    "figi_review_out",
                    ("--figi-review-out",),
                    Path,
                    "write FIGI disagreements to review (CSV)",
                    default=FIGI_REVIEW_OUT,
                ),
            ),
            skip=entries_reference.run_universe_mode,
        ),
        Task(
            "universe",
            "import the monthly master universe CSVs",
            universe_import,
            ("universe", "instruments/reference"),
            entries_reference.run_universe_csv,
            params=(
                SESSION,
                Param("stocks", ("--stocks",), Path, "stock universe CSV", required=True),
                Param("etfs", ("--etfs",), Path, "ETF universe CSV"),
                Param("version", ("--version",), str, "universe version label", required=True),
            ),
        ),
        Task(
            "company-details",
            "company details from SEC EDGAR (incremental)",
            company_details,
            ("instruments/company",),
            entries_reference.run_company_details,
            sources=("sec_tickers", "sec_submissions"),
            settings="sources.toml [sec_edgar]",
            params=(
                SESSION,
                Param("force", ("--force",), None, "refetch every company"),
                Param("limit", ("--limit",), int, "fetch at most N companies this run"),
            ),
        ),
        Task(
            "listing-history",
            "every US stock / ETF Tiingo ever listed, with its dates "
            "(instruments/listing_history); in no workflow until the owner has read a real pull",
            listing_history,
            ("instruments/listing_history",),
            entries_reference.run_listing_history,
            sources=("tiingo_listings", "tiingo_meta"),
            settings="sources.toml [tiingo]",
            params=(SESSION,),
        ),
        Task(
            "analyst-probe",
            "which analyst endpoints the FMP and Finnhub keys may call (analyst/vendor_access); "
            "one request per endpoint, in no workflow",
            analyst_probe,
            ("analyst/vendor_access",),
            analyst_probe.run,
            optional_sources=analyst_probe.SOURCES,
            settings="sources.toml [fmp]",
            params=(SESSION,),
        ),
        Task(
            "analyst-snapshot",
            "tonight's FMP and Finnhub analyst data of a rotating slice of names, appended to our "
            "own point-in-time history (analyst/estimate_snapshots); within [fmp] daily_budget",
            analyst_snapshot,
            ("analyst/estimate_snapshots",),
            analyst_snapshot.run,
            optional_sources=analyst_snapshot.SOURCES,
            skip=source_guards.no_analyst_source,
            settings="sources.toml [fmp] [finnhub]; events/scope.toml",
            params=(SESSION, Param("limit", ("--limit",), int, "ask at most N names of FMP")),
        ),
        Task(
            "index-membership",
            "S&P 500 membership intervals since 1996 from fja05680/sp500 "
            "(instruments/index_membership); in no workflow until the owner has read a real pull",
            index_membership,
            ("instruments/index_membership",),
            entries_reference.run_index_membership,
            sources=("sp500_history",),
            settings="sources.toml [sp500_history]",
            params=(SESSION,),
        ),
        Task(
            "winners-sample",
            "Tiingo daily bars from 2010 for a seeded 200-name sample (100 delisted by year, 50 "
            "live, 50 hand-listed winners) and its coverage report (var/logs); writes no table "
            "(resumable; 72 s a name on the free tier)",
            winners_sample,
            (),
            entries_reference.run_winners_sample,
            sources=("tiingo_prices",),
            settings="sources.toml [tiingo]",
            params=(
                SESSION,
                Param("report", ("--report",), str, "coverage report path (default var/logs)"),
                Param("seed", ("--seed",), int, "sampling seed (default fixed: same names)"),
                Param("limit", ("--limit",), int, "fetch at most N names this run"),
            ),
        ),
        Task(
            "shares",
            "shares, financials and statement lines from SEC company facts (incremental)",
            shares,
            ("instruments/shares", "instruments/statements"),
            entries_reference.run_shares,
            sources=("sec_company_facts",),
            settings="sources.toml [sec_edgar] facts_refresh_days, statements_backfill_per_night",
            params=(
                SESSION,
                Param("force", ("--force",), None, "refetch every company"),
                Param("limit", ("--limit",), int, "fetch at most N companies this run"),
            ),
        ),
        Task(
            "etf-holdings",
            "what each ETF holds, from the issuers' daily files and SEC N-PORT (incremental)",
            etf_holdings,
            ("holdings/etf", "holdings/etf_shares"),
            entries_reference.run_etf_holdings,
            optional_sources=source_guards.HOLDINGS_ISSUERS,
            settings="sources.toml [etf_holdings]",
            params=(
                SESSION,
                Param("symbols", ("--symbols",), str, "comma-separated ETF tickers"),
                Param(
                    "force", ("--force",), None, "reread every covered fund, accepting what is read"
                ),
                Param("limit", ("--limit",), int, "read at most N funds this run"),
            ),
            skip=source_guards.no_holdings_source,
        ),
        Task(
            "descriptions",
            "descriptions: stocks from Massive (capped per night), ETFs from SEC prospectuses",
            descriptions,
            (descriptions.TABLE,),
            entries_ops.run_descriptions,
            optional_sources=source_guards.DESCRIPTION_SOURCES,
            settings="sources.toml [massive] descriptions_per_night, [sec_edgar] fund_quarters",
            params=(
                SESSION,
                Param("limit", ("--limit",), int, "ask Massive for at most N stocks this run"),
                Param("symbols", ("--symbols",), str, "comma-separated stocks (skips the ETFs)"),
                Param("only", ("--only",), str, "massive (stocks) or funds (ETFs)"),
                Param("force", ("--force",), None, "ask again even if described"),
            ),
            skip=source_guards.no_description_source,
        ),
        Task(
            "earnings",
            "store the Nasdaq earnings calendar as events, or a resumable history backfill "
            "(--from/--to)",
            earnings,
            ("events/earnings",),
            entries_market.run_earnings,
            sources=("nasdaq_earnings",),
            settings="sources.toml [nasdaq_earnings]",
            params=(
                SESSION,
                Param("start", ("--start",), date.fromisoformat, "first date (default: --date)"),
                Param("days", ("--days",), int, "calendar days (default: sources.toml)"),
                Param("history_from", ("--from",), date.fromisoformat, "backfill: first day"),
                Param("history_to", ("--to",), date.fromisoformat, "backfill: last day"),
            ),
        ),
        Task(
            "bars",
            "unadjusted daily bars from Massive (resumable backfill)",
            bars,
            ("bars/1d",),
            entries_market.run_bars,
            sources=("massive_bars",),
            settings="sources.toml [massive]",
            params=(SESSION, FROM, TO, Param("force", ("--force",), None, "re-fetch stored")),
        ),
        Task(
            "bars-history",
            "unadjusted daily bars from Tiingo since 2018 for the scope list and its funds' "
            "references (resumable backfill: 50 requests an hour on the free tier)",
            bars_history,
            ("bars/1d", "events/split", "events/bar_flag"),
            entries_market.run_bars_history,
            sources=("tiingo_prices",),
            settings="sources.toml [tiingo]; events/scope.toml",
            params=(
                SESSION,
                Param("since", ("--since",), date.fromisoformat, "first session (default 2018)"),
                Param("until", ("--until",), date.fromisoformat, "last session (default --date)"),
                Param("symbols", ("--symbols",), str, "tickers on top of the scope list"),
                Param("limit", ("--limit",), int, "fetch at most N names this run"),
                Param("force", ("--force",), None, "also names already fetched for the window"),
                Param(
                    "fill",
                    ("--fill",),
                    int,
                    "also the N most useful names of the universe without history (optionable, "
                    "then IV30, then dollar volume), within [tiingo] monthly_symbol_budget",
                ),
                Param(
                    "from_listings",
                    ("--from-listings",),
                    None,
                    "the names are the listings of the universe over since..until (by "
                    "permaTicker; a reused ticker without one is never fetched), not the scope "
                    "list",
                ),
                Param(
                    "include_tiers",
                    ("--include-tiers",),
                    None,
                    "also the tier A / B short-put names (hundreds: needs Tiingo's Power tier)",
                ),
            ),
        ),
        Task(
            "filings",
            "SEC event filings (8-K with items, NT 10-K/10-Q, SC TO-I, Form 25, 424B4, Form 10) of "
            "every operating company in the universe (events/filing) and "
            "their Item 2.02 results releases as earnings rows (sec_8k); --since backfills per "
            "CIK (resumable, --limit), the default reads the days since the latest stored "
            "filing from EDGAR's daily form index",
            filings,
            (filings.TABLE, filings.EARNINGS),
            entries_market.run_filings,
            sources=("sec_filings", "sec_daily_index"),
            settings="sources.toml [sec_edgar] [quality]",
            params=(
                SESSION,
                Param(
                    "since",
                    ("--since",),
                    date.fromisoformat,
                    "backfill: every CIK from this date (one already covered is skipped); "
                    "default: the days since the latest stored filing, else 2018",
                ),
                Param("symbols", ("--symbols",), str, "only these tickers (default: the universe)"),
                Param("limit", ("--limit",), int, "per-CIK reads: fetch at most N CIKs this run"),
            ),
        ),
        Task(
            "rates",
            "Treasury par yield curve: risk-free rates by tenor (one request per year)",
            rates,
            ("rates/treasury",),
            entries_market.run_rates,
            sources=("treasury",),
            settings="sources.toml [treasury] lookback_days",
            params=(SESSION, FROM, TO, Param("force", ("--force",), None, "rewrite stored")),
        ),
        Task(
            "corporate-actions",
            "splits and dividends from Massive",
            corporate_actions,
            ("events/split", "events/dividend"),
            entries_market.run_corporate_actions,
            sources=("massive_corporate_actions",),
            settings="sources.toml [massive] corporate_actions_window",
            params=(SESSION, FROM, TO),
        ),
        Task(
            "chains",
            "option chains from the Cboe delayed feed",
            option_chains,
            ("chains/underlying_quotes", "chains/option_quotes", "chains/status"),
            entries_market.run_chains,
            sources=("cboe",),
            settings="sources.toml [cboe]",
            params=(
                SESSION,
                Param("workers", ("--workers",), int, "parallel requests (default: sources.toml)"),
                Param("symbols", ("--symbols",), str, "comma-separated subset of the universe"),
            ),
        ),
        Task(
            "macro",
            "economic series and index levels (FRED / ALFRED, published files) with vintages",
            macro_series,
            (macro_series.TABLE,),
            entries_market.run_macro,
            optional_sources=("fred", "published"),
            settings="macro.toml + sources.toml [fred] [published] [quality]",
            params=(
                SESSION,
                Param("only", ("--only",), str, "comma-separated series keys, e.g. UNRATE"),
                Param(
                    "since",
                    ("--since",),
                    date.fromisoformat,
                    "first observation date (a backfill; default: all history)",
                ),
            ),
        ),
        Task(
            "macro-calendar",
            "the macro release calendar (FRED release dates, ISM by rule): past and scheduled",
            macro_calendar,
            (macro_calendar.TABLE,),
            entries_market.run_macro_calendar,
            optional_sources=("fred_release_dates",),
            settings="events/releases.toml + sources.toml [fred] [quality]",
            params=(
                SESSION,
                Param("only", ("--only",), str, "comma-separated release keys, e.g. CPI,FOMC"),
            ),
        ),
        Task(
            "rollups",
            "compute rollups for a session or backfill a range (--from/--to)",
            rollups,
            rollups.TABLES,
            entries_market.run_rollups,
            settings="rollups.toml",
            params=(
                SESSION,
                FROM,
                TO,
                Param("only", ("--only",), str, "comma-separated rollups, e.g. price_stats@v2"),
            ),
        ),
        Task(
            "market-rollups",
            "compute the market-entity rollups (ADR 0047) for a session or backfill a range",
            market_rollups,
            market_rollups.TABLES,
            entries_market.run_market_rollups,
            settings="rollups.toml",
            params=(
                SESSION,
                FROM,
                TO,
                Param(
                    "only", ("--only",), str, "comma-separated market rollups, e.g. market_trend@v2"
                ),
            ),
        ),
        Task(
            "outcomes",
            "forward outcomes of the windows a session closes (ADR 0053); --from/--to: window ends",
            outcomes,
            outcomes.TABLES,
            entries_market.run_outcomes,
            settings="edges/*.toml (horizons, benchmarks)",
            params=(SESSION, FROM, TO),
        ),
        Task(
            "verify",
            "compare the session's stored values with IBKR (IB Gateway, read-only market data)",
            verify,
            (verify.TABLE,),
            entries_ops.run_verify,
            sources=("ibkr",),
            settings="verification.toml + sources.toml [ibkr]",
            params=(
                SESSION,
                Param("symbols", ("--symbols",), str, "comma-separated tickers (default: sample)"),
            ),
            skip=source_guards.gateway_down,
        ),
        Task(
            "ibkr-contracts",
            "IBKR contract ids (conid) of the optionable universe: new names, then monthly",
            ibkr_contracts,
            (ibkr_contracts.TABLE,),
            entries_ops.run_ibkr_contracts,
            sources=("ibkr",),
            settings="sources.toml [ibkr] contracts_refresh_days, contracts_batch",
            params=(
                SESSION,
                Param("symbols", ("--symbols",), str, "comma-separated tickers (resolved now)"),
                Param("force", ("--force",), None, "re-resolve every contract"),
                Param("limit", ("--limit",), int, "resolve at most N contracts this run"),
            ),
            skip=source_guards.gateway_down,
        ),
        Task(
            "ibkr-iv",
            "IBKR implied / historical vol: nightly snapshot, or a resumable history backfill "
            "(--from/--to)",
            ibkr_iv,
            (ibkr_iv.TABLE,),
            entries_ops.run_ibkr_iv,
            sources=("ibkr",),
            settings="sources.toml [ibkr] iv_batch, iv_history_days, iv_backfill_per_night",
            params=(
                SESSION,
                FROM,
                TO,
                Param("symbols", ("--symbols",), str, "comma-separated tickers"),
                Param("limit", ("--limit",), int, "backfill at most N underlyings this run"),
            ),
            skip=source_guards.gateway_down,
        ),
        Task(
            "ibkr-iv-repair",
            "null the stored IBKR vols outside their declared range, with the reason "
            "(no request to IB); then rollups --only ibkr_iv@v1 over the range",
            ibkr_iv,
            (ibkr_iv.TABLE,),
            entries_ops.run_ibkr_iv_repair,
            params=(
                SESSION,
                Param("start", ("--from",), date.fromisoformat, "first session (needed)"),
                Param("end", ("--to",), date.fromisoformat, "last session (default: --date)"),
            ),
        ),
        Task(
            "quality",
            "run the data-quality checks for a session",
            quality,
            (),
            entries_ops.run_quality,
            settings="sources.toml [quality]",
            params=(SESSION,),
        ),
        Task(
            "bar-quality",
            "flag stored daily bars that cannot be right (a close below the floor, bad OHLC, an "
            "unexplained jump) in events/bar_flag; reads are the stored bars of --from..--to",
            bar_quality,
            ("events/bar_flag",),
            entries_ops.run_bar_quality,
            settings="sources.toml [quality] min_bar_close, max_bar_jump, split_window_sessions, "
            "max_bad_bar_share",
            params=(
                SESSION,
                FROM,
                TO,
                Param("only", ("--only",), str, "instrument ids (comma separated)"),
            ),
        ),
        Task(
            "history-copy",
            "bring the derived history copies (read-optimised, one file per year) up to date",
            history_copy,
            (),  # derived files beside the tables, not a table (ADR 0060)
            entries_ops.run_history_copy,
            settings="nightly.toml [history_copy]",
            params=(SESSION,),
            skip=history_copy.skip_reason,
        ),
        Task(
            "purge-raw",
            "delete raw vendor responses, unfinished-run scratch and old live quotes after N days",
            purge,
            (),  # deletes raw files and scratch; produces no table
            entries_ops.run_purge,
            settings=(
                "sources.toml raw_retention_days (+ per section), staging_retention_days,"
                " live_retention_days"
            ),
            params=(
                Param("session", ("--date",), date.fromisoformat, "reference date"),
                Param(
                    "keep_days",
                    ("--keep-days",),
                    int,
                    "raw files, every source (default: per source, sources.toml)",
                ),
                Param(
                    "staging_keep_days",
                    ("--staging-keep-days",),
                    int,
                    "unfinished-run scratch (default: sources.toml)",
                ),
            ),
        ),
        Task(
            "migrate-ids",
            "rewrite stored ids per instruments/id_map (new runs)",
            migrate_ids,
            (),  # rewrites any table as a new run; produces none
            entries_ops.run_migrate_ids,
            params=(Param("dry_run", ("--dry-run",), None, "count only; write nothing"),),
        ),
        Task(
            "retire-features",
            "delete a superseded feature group's tables once its replacement covers them",
            retire_features,
            (),  # deletes a superseded table; produces none
            entries_ops.run_retire_features,
            params=(
                Param("session", ("--date",), date.fromisoformat, "run date (default: last)"),
                Param(
                    "group",
                    ("--group",),
                    str,
                    "superseded group, e.g. price_stats@v1",
                    required=True,
                ),
                Param("dry_run", ("--dry-run",), None, "report sessions and sizes only"),
            ),
        ),
        Task(
            "golden-load",
            "load the golden CSVs into the store (a fixture store, never production)",
            golden,
            ("bars/1d", "instruments/reference", "instruments/shares", "universe", golden.CATALOG),
            entries_ops.run_golden_load,
            sources=("synthetic",),
            params=(Param("golden_dir", ("--golden-dir",), Path, default=GOLDEN_DIR),),
        ),
    )
}


def task(name: str) -> Task:
    if name not in TASKS:
        raise KeyError(f"unknown task {name!r}; known: {sorted(TASKS)}")
    return TASKS[name]


def run_task(name: str, ctx: TaskContext, params: Params) -> RunRecord:
    """Run one task. Missing required sources fail here, before any work."""
    spec = task(name)
    missing = [s for s in spec.sources if s not in ctx.sources]
    if missing:
        raise KeyError(f"task {name!r} needs sources {missing}")
    return spec.run(ctx, params)
