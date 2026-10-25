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
from algotrade.storage.tables.edge_schemas import EDGE_VERDICT
from algotrade_ingestion.tasks.analyst import backfill as analyst_backfill
from algotrade_ingestion.tasks.analyst import probe as analyst_probe
from algotrade_ingestion.tasks.analyst import snapshot as analyst_snapshot
from algotrade_ingestion.tasks.derived import (
    history_copy,
    market_rollups,
    option_outcomes,
    outcomes,
    residual_returns,
    rollups,
)
from algotrade_ingestion.tasks.edges import picks as edge_picks
from algotrade_ingestion.tasks.edges import verdicts as edge_verdicts
from algotrade_ingestion.tasks.events import filing_text, filings, insider, ipo_lockups
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
from algotrade_ingestion.tasks.maintenance.compaction import task as compact_task
from algotrade_ingestion.tasks.market import (
    bars,
    bars_history,
    corporate_actions,
    earnings,
    etf_holdings,
    fund_nav,
    ibkr_iv,
    option_chains,
    rates,
)
from algotrade_ingestion.tasks.market.futures import curves as futures_curves
from algotrade_ingestion.tasks.market.volatility import vx_futures
from algotrade_ingestion.tasks.profile import descriptions
from algotrade_ingestion.tasks.reference import (
    company_details,
    ibkr_contracts,
    shares,
    universe_build,
    universe_import,
)
from algotrade_ingestion.tasks.screens import screen_runs_backfill, screen_values_recluster
from algotrade_ingestion.tasks.shorting import restamp, short_interest, short_volume
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
                    "etf_review_out",
                    ("--etf-review-out",),
                    Path,
                    "write ETFs whose category the rules could not settle (CSV)",
                ),
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
            "delisted-tickers",
            "Massive's delisted tickers (instruments/delisted_tickers); in no workflow",
            entries_reference.delisted_tickers,
            ("instruments/delisted_tickers",),
            entries_reference.run_delisted_tickers,
            sources=("massive_tickers",),
            settings="sources.toml [massive] [quality]",
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
            "tonight's FMP and Finnhub analyst data of a rotating slice of names, and Yahoo's for "
            "the names FMP refuses, appended to our own point-in-time history "
            "(analyst/estimate_snapshots); within [fmp] daily_budget and [yahoo] per_night",
            analyst_snapshot,
            ("analyst/estimate_snapshots",),
            analyst_snapshot.run,
            optional_sources=analyst_snapshot.SOURCES,
            skip=source_guards.no_analyst_source,
            settings="sources.toml [fmp] [finnhub] [yahoo]; events/scope.toml",
            params=(
                SESSION,
                Param("limit", ("--limit",), int, "ask at most N names of FMP and of Yahoo"),
            ),
        ),
        Task(
            "analyst-backfill",
            "Yahoo's analyst data of the whole stock population, one batch of [yahoo] "
            "backfill_batch names a run (resumable; quiet until the last session's nightly is "
            "complete; stops at the first 429); loop it with scripts/ops/yahoo_backfill.sh; in no "
            "workflow (ADR 0080 amendment 2026-10-23b)",
            analyst_backfill,
            ("analyst/estimate_snapshots",),
            analyst_backfill.run,
            sources=analyst_backfill.SOURCES,
            paced=analyst_backfill.paced,
            settings="sources.toml [yahoo]",
            params=(
                Param("session", ("--date",), date.fromisoformat, "ignored: the last closed one"),
                Param("limit", ("--limit",), int, "ask at most N names this batch"),
            ),
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
            sources=("sec_company_facts", "sec_filings"),
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
            "fund-nav",
            "daily NAV of closed-end funds from Tiingo's Nasdaq MFQS X<ticker>X series "
            "(events/fund_nav; --from 2004-01-01 backfills, the default is the last 10 days; "
            "in no workflow: the free tier cannot hold it nightly)",
            fund_nav,
            ("events/fund_nav",),
            entries_market.run_fund_nav,
            sources=("tiingo_nav", "tiingo_nav_tickers"),
            settings="sources.toml [tiingo]",
            params=(
                SESSION,
                FROM,
                TO,
                Param("symbols", ("--symbols",), str, "only these fund tickers (comma list)"),
                Param("limit", ("--limit",), int, "fetch at most N funds this run"),
                Param("force", ("--force",), None, "also funds already fetched for the window"),
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
            "insider",
            "SEC Form 4 / 4/A insider transactions (events/insider_transaction): --since backfills "
            "the quarterly bulk sets from that quarter (acceptance times from the issuers' "
            "submissions; resumable, --limit quarters, --force rereads), the default reads the "
            "days since the last clean walk from EDGAR's daily form index and each filing's XML",
            insider,
            (insider.TABLE,),
            entries_market.run_insider,
            sources=("sec_filings", "sec_form345_bulk", "sec_form4_xml", "sec_daily_index"),
            settings="sources.toml [sec_edgar]",
            params=(
                SESSION,
                Param(
                    "since",
                    ("--since",),
                    date.fromisoformat,
                    "backfill: the bulk quarters from the one holding this date (a quarter an "
                    "earlier run read is skipped); default: the daily walk",
                ),
                Param("until", ("--until",), date.fromisoformat, "backfill: last quarter's date"),
                Param("limit", ("--limit",), int, "backfill: read at most N quarters this run"),
                Param("force", ("--force",), None, "backfill: also quarters already read"),
            ),
        ),
        Task(
            "ipo-lockups",
            "IPO facts and lock-up expiry dates from EDGAR 424B4 final prospectuses "
            "(events/ipo_lockup): the prospectuses EDGAR full-text search lists for a month at a "
            "time, each read once (the submissions for the acceptance, the document for the "
            "terms); no --since reads the last 30 days (the nightly), --since 2005-01-01 is the "
            "backfill (resumable, --limit caps the prospectuses read)",
            ipo_lockups,
            (ipo_lockups.TABLE,),
            entries_market.run_ipo_lockups,
            sources=("sec_prospectus_search", "sec_filings", "sec_prospectus"),
            settings="sources.toml [sec_edgar]",
            params=(
                SESSION,
                Param(
                    "since",
                    ("--since",),
                    date.fromisoformat,
                    "first filing date (default: 30 days before the session; the backfill "
                    "starts 2005-01-01)",
                ),
                Param(
                    "until", ("--until",), date.fromisoformat, "last filing date (default --date)"
                ),
                Param("limit", ("--limit",), int, "read at most N prospectuses this run"),
            ),
        ),
        Task(
            "filing-text",
            "item sections of the 10-K / 10-Q of every filer, delisted too (events/filing_text: "
            "1, 1A, 3, 7, 7A, 9A of a 10-K; I-2, I-3, II-1, II-1A of a 10-Q); --from [--to] "
            "backfills a filing-date window (the filers of the SEC daily index; --limit CIKs a "
            "run, resumable; history from 2010: newest windows first), the default is the "
            "nightly increment of the CIKs due a report",
            filing_text,
            (filing_text.TABLE,),
            entries_market.run_filing_text,
            sources=("sec_filings", "sec_filing_text", "sec_daily_index"),
            stepped=("sec_filings", "sec_filing_text", "sec_daily_index"),
            settings="sources.toml [sec_edgar]",
            params=(
                SESSION,
                Param(
                    "start",
                    ("--from",),
                    date.fromisoformat,
                    "backfill: filings filed on or after this date (default: the nightly "
                    "increment of the CIKs due a report)",
                ),
                TO,
                Param("symbols", ("--symbols",), str, "only these tickers (default: every filer)"),
                Param(
                    "limit", ("--limit",), int, "backfill: at most N CIKs this run (default 100)"
                ),
                Param("items", ("--items",), str, "item ids kept, comma list (1A,7 / I-2,II-1A)"),
                Param(
                    "threads",
                    ("--threads",),
                    int,
                    "documents downloaded at once (default 10; 0: one at a time)",
                ),
                Param("procs", ("--procs",), int, "parse worker processes (default 4)"),
                Param(
                    "live_only",
                    ("--live-only",),
                    None,
                    "backfill only the filers that are operating companies of the session's "
                    "universe (the recorded filer list stays every filer)",
                ),
                Param("force", ("--force",), None, "fetch filings and CIKs already read again"),
                Param(
                    "allow_gap",
                    ("--allow-gap",),
                    str,
                    "backfill: weekdays (YYYY-MM-DD,...) with no daily index you verified SEC was "
                    "closed on",
                ),
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
            "vx-futures",
            "Cboe VIX futures by expiry (settle, volume, open interest): the nightly window, or a "
            "resumable history backfill of the expiries in --from/--to (2013 on)",
            vx_futures,
            (vx_futures.TABLE,),
            entries_market.run_vx_futures,
            sources=("cboe_vx",),
            settings="sources.toml [cboe_vx]",
            params=(SESSION, FROM, TO, Param("force", ("--force",), None, "rewrite stored")),
        ),
        Task(
            "short-interest",
            "FINRA short interest (twice a month, one request per settlement date) into "
            "events/short_interest; --from backfills (the API holds 2017-12-29 onward); no_ml",
            short_interest,
            ("events/short_interest",),
            short_interest.run,
            sources=(short_interest.SOURCE,),
            settings="sources.toml [finra]",
            params=(SESSION, FROM, TO, Param("force", ("--force",), None, "refetch stored dates")),
        ),
        Task(
            "short-volume",
            "FINRA Reg SHO daily short-sale volume (one request per trade date) into "
            "events/short_volume; the API serves a rolling year; no_ml",
            short_volume,
            ("events/short_volume",),
            short_volume.run,
            sources=(short_volume.SOURCE,),
            settings="sources.toml [finra]",
            params=(SESSION, FROM, TO, Param("force", ("--force",), None, "refetch stored dates")),
        ),
        Task(
            "restamp-known-from",
            "move the stored FINRA rows' known_from to the publication schedule without a "
            "refetch (ADR 0050 repair); values untouched",
            restamp,
            (),  # restates events/short_interest and short_volume, owned by their tasks
            entries_ops.run_restamp_known_from,
            params=(SESSION, Param("dry_run", ("--dry-run",), None, "count the rows only")),
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
            "option-outcomes",
            "chain P&L of the option windows a session closes (ADR 0053 amendment); forward-only",
            option_outcomes,
            option_outcomes.TABLES,
            entries_market.run_option_outcomes,
            settings="edges/*.toml (option_pnl structures, tenors, horizons)",
            params=(SESSION, FROM, TO),
        ),
        Task(
            "residual-returns",
            "factor-neutral forward returns of the windows a session closes (ADR 0053); "
            "--from/--to: window ends; needs factor_betas@v1 stored before each start session",
            residual_returns,
            residual_returns.TABLES,
            entries_market.run_residual_returns,
            settings="edges/*.toml (horizons of residual_return outcomes)",
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
            "futures-curves",
            "nightly futures curve snapshot per root (IBKR, read-only): the front contracts' "
            "last / prior settle / volume / open interest with expiry",
            futures_curves,
            (futures_curves.TABLE,),
            entries_ops.run_futures_curves,
            sources=("ibkr",),
            settings="sources.toml [ibkr] futures_roots, futures_front",
            params=(
                SESSION,
                Param("symbols", ("--symbols",), str, "comma-separated futures roots"),
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
            "compact-runs",
            "compact a merge table's per-partition run files value-exactly (ADR 0078)",
            compact_task,
            (),  # rewrites a table's run files in place; publishes nothing, no sequence moves
            entries_ops.run_compact_runs,
            settings="nightly.toml [compaction] and [resources] min_free_gb",
            params=(
                SESSION,
                Param(
                    "table",
                    ("--table",),
                    str,
                    "table to compact (a [compaction] one)",
                    required=True,
                ),
                FROM,
                TO,
                Param("limit", ("--limit",), int, "stop after N partitions were compacted"),
                Param(
                    "workers",
                    ("--workers",),
                    int,
                    "worker processes (default: nightly.toml [compaction] workers)",
                ),
                Param(
                    "beside_ingest",
                    ("--beside-ingest",),
                    None,
                    "do not stop for a held ingest lock: compact beside a nightly or a backfill",
                ),
                Param("dry_run", ("--dry-run",), None, "report the saving only; write nothing"),
                Param(
                    "verify",
                    ("--verify",),
                    None,
                    "with --dry-run: also verify the plan (slow), as a live run does",
                ),
            ),
        ),
        Task(
            "edge-picks",
            "store what every site edge took at a session in results/edge_picks (ADR 0081), by the "
            "harness's own pick rule (idempotent, resumable: a stored (edge, screener) is "
            "skipped; --from/--to backfill a window of sessions)",
            edge_picks,
            edge_picks.TABLES,
            entries_ops.run_edge_picks,
            skip=source_guards.no_config_store,
            params=(
                SESSION,
                FROM,
                TO,
                Param("edge", ("--edge",), str, "decide this one site edge only"),
            ),
        ),
        Task(
            "edge-verdicts",
            "store the headline of every site edge's canonical run in results/edge_verdict, the "
            "backfill of runs stored before it and the re-judge after the judge, verdict.toml or "
            "an edge document changed (idempotent, resumable: a run with a row under the current "
            "fingerprint is skipped; --limit caps the rows written)",
            edge_verdicts,
            (EDGE_VERDICT.name,),
            entries_ops.run_edge_verdicts,
            skip=source_guards.no_config_store,
            params=(
                Param("session", ("--date",), date.fromisoformat, "only runs ending this session"),
                Param("edge", ("--edge",), str, "judge this one site edge only"),
                FROM,
                TO,
                Param("limit", ("--limit",), int, "write at most N rows this run"),
                Param(
                    "dry_run", ("--dry-run",), None, "count what would be written; write nothing"
                ),
                Param(
                    "verify",
                    ("--verify",),
                    None,
                    "read-only check: judge current rows too, list differences, write nothing",
                ),
            ),
        ),
        Task(
            "screen-runs-backfill",
            "frame results/screen_runs and results/screen_picks for the rule-screen runs stored "
            "before them, from rule_screen and the run records (idempotent, resumable; --limit "
            "caps the runs framed)",
            screen_runs_backfill,
            ("results/screen_runs", "results/screen_picks"),
            entries_ops.run_screen_runs_backfill,
            params=(
                Param("session", ("--date",), date.fromisoformat, "frame this one session only"),
                FROM,
                TO,
                Param("limit", ("--limit",), int, "frame at most N runs this run"),
            ),
        ),
        Task(
            "screen-values-recluster",
            "rewrite the stored rule_screen and rule_screen_values files sorted by instrument_id "
            "in 8,192-row row groups, as new runs are written (idempotent, resumable, same run "
            "ids and knowledge_ts; --limit caps the runs rewritten)",
            screen_values_recluster,
            ("results/rule_screen", "results/rule_screen_values"),
            entries_ops.run_screen_values_recluster,
            params=(
                Param("session", ("--date",), date.fromisoformat, "rewrite this one session only"),
                FROM,
                TO,
                Param("limit", ("--limit",), int, "rewrite at most N runs this run"),
            ),
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
