"""The ingestion task registry: every task declared ONCE (ADR 0019).

A ``Task`` names what it writes (must match the ``[[table]]`` producers in
``architecture/ownership.toml``), the sources it needs from ``TaskContext.sources``, the
site settings section it reads, its parameters (which the CLI turns into flags) and its
``run(ctx, params)`` entry. Defaults that come from settings (corporate-actions window,
earnings days, chain workers) are applied here, so the CLI and nightly cannot drift.

``algotrade-ingest <task>`` and ``algotrade-ingest run <task>`` both dispatch here; the
nightly workflow is an ordered list of these names (``workflows/nightly/nightly.py``).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

from algotrade.config.site.settings import load_universe
from algotrade.core.time.calendar import sessions_between
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.sources.framework.base import DirectorySource, FixtureSource
from algotrade_ingestion.tasks.derived import features
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance import golden, migrate_ids, purge, quality
from algotrade_ingestion.tasks.market import (
    bars,
    corporate_actions,
    earnings,
    option_chains,
    rates,
)
from algotrade_ingestion.tasks.reference import company_details, universe_build, universe_import

type Params = Mapping[str, Any]
GOLDEN_DIR = Path("datasets/golden")


@dataclass(frozen=True)
class Param:
    """One task parameter; ``flags`` are its CLI spelling. ``kind=None`` is an on/off flag."""

    name: str
    flags: tuple[str, ...]
    kind: Callable[[str], Any] | None = str
    help: str = ""
    required: bool = False
    default: Any = None


@dataclass(frozen=True)
class Task:
    name: str
    description: str
    module: ModuleType  # the module that produces ``tables``
    tables: tuple[str, ...]
    run: Callable[[TaskContext, Params], RunRecord]
    sources: tuple[str, ...] = ()  # required, by name in ``TaskContext.sources``
    optional_sources: tuple[str, ...] = ()
    settings: str | None = None  # the config/site section it reads
    params: tuple[Param, ...] = ()
    # Workflows (nightly) skip the task when this returns a reason; explicit runs ignore it.
    skip: Callable[[TaskContext], str | None] | None = None


SESSION = Param("session", ("--date",), date.fromisoformat, "session (default: last session)")
FROM = Param("start", ("--from",), date.fromisoformat, "window start")
TO = Param("end", ("--to",), date.fromisoformat, "window end")


def session_of(params: Params) -> date:
    session = params.get("session")
    if not isinstance(session, date):
        raise ValueError("task parameter 'session' (a date) is required")
    return session


# ----------------------------------------------------------------------------- entries


def _universe_build(ctx: TaskContext, p: Params) -> RunRecord:
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
    record = universe_build.build_universe(ctx, sources, settings, session_of(p))
    if p.get("review_out"):
        universe_build.write_review(ctx.reader, session_of(p), p["review_out"])
        record.stats["review_out"] = str(p["review_out"])
    return record


def _universe_mode(ctx: TaskContext) -> str | None:
    mode = load_universe(ctx.configs).source if ctx.configs is not None else "csv_import"
    return None if mode == "nasdaq_trader" else f"skipped: {mode} mode"


def _universe_csv(ctx: TaskContext, p: Params) -> RunRecord:
    files = [universe_import.UniverseFile(Path(p["stocks"]), "STOCK")]
    if p.get("etfs"):
        files.append(universe_import.UniverseFile(Path(p["etfs"]), "ETF"))
    return universe_import.import_universe(ctx, files, str(p["version"]), session_of(p))


def _company_details(ctx: TaskContext, p: Params) -> RunRecord:
    sources = company_details.CompanySources(
        ctx.sources["sec_tickers"], ctx.sources["sec_submissions"], ctx.settings.sec_refresh_days
    )
    return company_details.ingest_company_details(
        ctx, sources, session_of(p), bool(p.get("force")), p.get("limit")
    )


def _earnings(ctx: TaskContext, p: Params) -> RunRecord:
    days = p.get("days") or ctx.settings.earnings_days
    return earnings.ingest_earnings(
        ctx, ctx.sources["nasdaq_earnings"], session_of(p), p.get("start"), days=days
    )


def _bars(ctx: TaskContext, p: Params) -> RunRecord:
    session = session_of(p)
    # Exchange sessions in the window; an explicit non-session date is fetched as asked.
    sessions = sessions_between(p.get("start") or session, p.get("end") or session) or [session]
    return bars.ingest_daily_bars(ctx, ctx.sources["massive_bars"], sessions, bool(p.get("force")))


def _rates(ctx: TaskContext, p: Params) -> RunRecord:
    end = p.get("end") or session_of(p)
    start = p.get("start") or end - timedelta(ctx.settings.treasury_lookback_days - 1)
    return rates.ingest_rates(ctx, ctx.sources["treasury"], start, end, bool(p.get("force")))


def _corporate_actions(ctx: TaskContext, p: Params) -> RunRecord:
    session = session_of(p)
    before, after = ctx.settings.actions_window
    start = p.get("start") or session + timedelta(before)
    end = p.get("end") or session + timedelta(after)
    source = ctx.sources["massive_corporate_actions"]
    return corporate_actions.ingest_corporate_actions(ctx, source, session, start, end)


def _chains(ctx: TaskContext, p: Params) -> RunRecord:
    session = session_of(p)
    symbols = [s for s in str(p.get("symbols") or "").split(",") if s.strip()]
    underlyings = option_chains.select_underlyings(ctx.reader, session, symbols)
    workers = int(p.get("workers") or ctx.settings.cboe_workers)
    return option_chains.ingest_option_chains(
        ctx, ctx.sources["cboe"], underlyings, session, option_chains.ChainJobConfig(workers)
    )


def _features(ctx: TaskContext, p: Params) -> RunRecord:
    return features.compute_option_liquidity(ctx, session_of(p))


def _quality(ctx: TaskContext, p: Params) -> RunRecord:
    return quality.run_quality(ctx, session_of(p))


def _purge(ctx: TaskContext, p: Params) -> RunRecord:
    return purge.purge(ctx, session_of(p), p.get("keep_days"), p.get("staging_keep_days"))


def _migrate_ids(ctx: TaskContext, p: Params) -> RunRecord:
    return migrate_ids.migrate_ids(ctx, dry_run=bool(p.get("dry_run")))


def _golden_load(ctx: TaskContext, p: Params) -> RunRecord:
    # ``golden_dir`` chose the directory when the registry built the fixture source.
    source = ctx.sources["synthetic"]
    if not isinstance(source, FixtureSource):
        raise TypeError("synthetic must be a FixtureSource (the golden CSVs)")
    return golden.load_golden(ctx, source)


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
            _universe_build,
            sources=("nasdaq_trader", "spy_holdings"),
            optional_sources=("massive_tickers",),
            settings="universe.toml",
            params=(
                SESSION,
                Param("review_out", ("--review-out",), Path, "write leverage candidates (CSV)"),
            ),
            skip=_universe_mode,
        ),
        Task(
            "universe",
            "import the monthly master universe CSVs",
            universe_import,
            ("universe", "instruments/reference"),
            _universe_csv,
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
            _company_details,
            sources=("sec_tickers", "sec_submissions"),
            settings="sources.toml [sec_edgar]",
            params=(
                SESSION,
                Param("force", ("--force",), None, "refetch every company"),
                Param("limit", ("--limit",), int, "fetch at most N companies this run"),
            ),
        ),
        Task(
            "earnings",
            "store the Nasdaq earnings calendar as events",
            earnings,
            ("events/earnings",),
            _earnings,
            sources=("nasdaq_earnings",),
            settings="sources.toml [nasdaq_earnings]",
            params=(
                SESSION,
                Param("start", ("--start",), date.fromisoformat, "first date (default: --date)"),
                Param("days", ("--days",), int, "calendar days (default: sources.toml)"),
            ),
        ),
        Task(
            "bars",
            "unadjusted daily bars from Massive (resumable backfill)",
            bars,
            ("bars/1d",),
            _bars,
            sources=("massive_bars",),
            settings="sources.toml [massive]",
            params=(SESSION, FROM, TO, Param("force", ("--force",), None, "re-fetch stored")),
        ),
        Task(
            "rates",
            "Treasury par yield curve: risk-free rates by tenor (one request per year)",
            rates,
            ("rates/treasury",),
            _rates,
            sources=("treasury",),
            settings="sources.toml [treasury] lookback_days",
            params=(SESSION, FROM, TO, Param("force", ("--force",), None, "rewrite stored")),
        ),
        Task(
            "corporate-actions",
            "splits and dividends from Massive",
            corporate_actions,
            ("events/split", "events/dividend"),
            _corporate_actions,
            sources=("massive_corporate_actions",),
            settings="sources.toml [massive] corporate_actions_window",
            params=(SESSION, FROM, TO),
        ),
        Task(
            "chains",
            "option chains from the Cboe delayed feed",
            option_chains,
            ("chains/underlying_quotes", "chains/option_quotes", "chains/status"),
            _chains,
            sources=("cboe",),
            settings="sources.toml [cboe]",
            params=(
                SESSION,
                Param("workers", ("--workers",), int, "parallel requests (default: sources.toml)"),
                Param("symbols", ("--symbols",), str, "comma-separated subset of the universe"),
            ),
        ),
        Task(
            "features",
            "compute nightly features (option_liquidity@v1)",
            features,
            (features.TABLE,),
            _features,
            params=(SESSION,),
        ),
        Task(
            "quality",
            "run the data-quality checks for a session",
            quality,
            (),
            _quality,
            settings="sources.toml [quality]",
            params=(SESSION,),
        ),
        Task(
            "purge-raw",
            "delete raw vendor responses and unfinished-run scratch older than N days",
            purge,
            (),  # deletes raw files and scratch; produces no table
            _purge,
            settings="sources.toml raw_retention_days, staging_retention_days",
            params=(
                Param("session", ("--date",), date.fromisoformat, "reference date"),
                Param("keep_days", ("--keep-days",), int, "raw files (default: sources.toml)"),
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
            _migrate_ids,
            params=(Param("dry_run", ("--dry-run",), None, "count only; write nothing"),),
        ),
        Task(
            "golden-load",
            "load the golden CSVs into the store (a fixture store, never production)",
            golden,
            ("bars/1d", "instruments/reference", golden.CATALOG),
            _golden_load,
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
