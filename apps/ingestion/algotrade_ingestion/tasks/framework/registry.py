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
from algotrade_ingestion.tasks.derived import rollups
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance import (
    golden,
    migrate_ids,
    purge,
    quality,
    retire_features,
)
from algotrade_ingestion.tasks.market import (
    bars,
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
from algotrade_sources.framework.base import (
    DirectorySource,
    FixtureSource,
    HoldingsSource,
    SessionSource,
)

type Params = Mapping[str, Any]
GOLDEN_DIR = Path("datasets/golden")
FIGI_REVIEW_OUT = Path("var/figi_review.csv")


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


def _shares(ctx: TaskContext, p: Params) -> RunRecord:
    sources = shares.SharesSources(
        ctx.sources["sec_company_facts"], ctx.settings.sec_facts_refresh_days
    )
    return shares.ingest_shares(ctx, sources, session_of(p), bool(p.get("force")), p.get("limit"))


HOLDINGS_ISSUERS = (
    "ssga_holdings",
    "ishares_holdings",
    "proshares_holdings",
    "sec_nport_holdings",
)  # priority order


def _holdings_issuers(ctx: TaskContext) -> list[HoldingsSource]:
    found = [ctx.sources[n] for n in HOLDINGS_ISSUERS if n in ctx.sources]
    return [s for s in found if isinstance(s, HoldingsSource)]


def _no_holdings_source(ctx: TaskContext) -> str | None:
    if not ctx.settings.vendor("etf_holdings").enabled:
        return "skipped: [etf_holdings] is disabled in sources.toml"
    if _holdings_issuers(ctx):
        return None
    reasons = sorted({ctx.unavailable.get(n, f"{n} is not configured") for n in HOLDINGS_ISSUERS})
    return f"skipped: {'; '.join(reasons)}"


def _etf_holdings(ctx: TaskContext, p: Params) -> RunRecord:
    issuers = _holdings_issuers(ctx)
    if not issuers:
        raise KeyError(f"task 'etf-holdings' needs one of the sources {list(HOLDINGS_ISSUERS)}")
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
        ctx, sources, session_of(p), bool(p.get("force")), limit, _symbols(p)
    )


def _earnings(ctx: TaskContext, p: Params) -> RunRecord:
    session = session_of(p)
    days = p.get("days") or ctx.settings.earnings_days
    start = p.get("start")
    if start is None:
        # Also the last week: those reports now carry the reported EPS and surprise, and
        # `last_earnings_date` stays current. An explicit --start is taken as given.
        back = ctx.settings.earnings_lookback_days
        start, days = session - timedelta(days=back), days + back
    return earnings.ingest_earnings(ctx, ctx.sources["nasdaq_earnings"], session, start, days=days)


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
        ctx,
        ctx.sources["cboe"],
        underlyings,
        session,
        option_chains.ChainJobConfig(workers, priority_symbols=ctx.settings.cboe_priority_symbols),
    )


def _rollups(ctx: TaskContext, p: Params) -> RunRecord:
    only = [k.strip() for k in str(p.get("only") or "").split(",") if k.strip()]
    return rollups.compute_rollups(ctx, session_of(p), p.get("start"), p.get("end"), only)


def _verify(ctx: TaskContext, p: Params) -> RunRecord:
    return verify.verify(ctx, session_of(p), _symbols(p))


def _symbols(p: Params) -> list[str]:
    return [s.strip() for s in str(p.get("symbols") or "").split(",") if s.strip()]


DESCRIPTION_SOURCES = (
    "massive_overview",
    "sec_fund_tickers",
    "sec_fund_objectives",
    "sec_fund_series",
)  # every source the task may read: the CLI builds only the ones a task declares


def _descriptions(ctx: TaskContext, p: Params) -> RunRecord:
    s = ctx.settings
    sources = descriptions.DescriptionSources(
        ctx.sources.get("massive_overview"),
        ctx.sources.get("sec_fund_tickers"),
        ctx.sources.get("sec_fund_objectives"),
        s.descriptions_per_night,
        s.descriptions_refresh_days,
        s.sec_fund_quarters,
        s.cboe_priority_symbols,
        ctx.sources.get("sec_fund_series"),
    )
    return descriptions.ingest_descriptions(
        ctx,
        sources,
        session_of(p),
        only=p.get("only"),
        limit=p.get("limit"),
        symbols=_symbols(p),
        force=bool(p.get("force")),
    )


def _no_description_source(ctx: TaskContext) -> str | None:
    """Workflows skip ``descriptions`` when neither Massive nor the SEC sources are built."""
    if any(name in ctx.sources for name in DESCRIPTION_SOURCES):
        return None
    reasons = sorted(
        {ctx.unavailable.get(n, f"{n} is not configured") for n in DESCRIPTION_SOURCES}
    )
    return f"skipped: {'; '.join(reasons)}"


def _ibkr(ctx: TaskContext) -> SessionSource:
    source = ctx.sources["ibkr"]
    if not isinstance(source, SessionSource):
        raise TypeError("ibkr must be a SessionSource (IB Gateway)")
    return source


def _ibkr_contracts(ctx: TaskContext, p: Params) -> RunRecord:
    return ibkr_contracts.resolve_contracts(
        ctx, _ibkr(ctx), session_of(p), _symbols(p), bool(p.get("force")), p.get("limit")
    )


def _ibkr_iv(ctx: TaskContext, p: Params) -> RunRecord:
    if p.get("start"):
        end = p.get("end") or session_of(p)
        source = _ibkr(ctx)
        return ibkr_iv.backfill_ivs(ctx, source, p["start"], end, _symbols(p), p.get("limit"))
    return ibkr_iv.nightly_ivs(ctx, _ibkr(ctx), session_of(p), _symbols(p))


def _gateway_down(ctx: TaskContext) -> str | None:
    """Workflows skip the IBKR tasks (with a WARN) when nothing listens on the gateway port."""
    source = ctx.sources.get("ibkr")
    reason = source.probe() if isinstance(source, SessionSource) else None
    return f"skipped: WARN: {reason}" if reason else None


def _quality(ctx: TaskContext, p: Params) -> RunRecord:
    return quality.run_quality(ctx, session_of(p))


def _purge(ctx: TaskContext, p: Params) -> RunRecord:
    return purge.purge(ctx, session_of(p), p.get("keep_days"), p.get("staging_keep_days"))


def _migrate_ids(ctx: TaskContext, p: Params) -> RunRecord:
    return migrate_ids.migrate_ids(ctx, dry_run=bool(p.get("dry_run")))


def _retire_features(ctx: TaskContext, p: Params) -> RunRecord:
    return retire_features.retire(ctx, session_of(p), str(p["group"]), bool(p.get("dry_run")))


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
            "shares",
            "shares outstanding from SEC company facts (incremental)",
            shares,
            ("instruments/shares",),
            _shares,
            sources=("sec_company_facts",),
            settings="sources.toml [sec_edgar] facts_refresh_days",
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
            ("holdings/etf",),
            _etf_holdings,
            optional_sources=HOLDINGS_ISSUERS,
            settings="sources.toml [etf_holdings]",
            params=(
                SESSION,
                Param("symbols", ("--symbols",), str, "comma-separated ETF tickers"),
                Param(
                    "force", ("--force",), None, "reread every covered fund, accepting what is read"
                ),
                Param("limit", ("--limit",), int, "read at most N funds this run"),
            ),
            skip=_no_holdings_source,
        ),
        Task(
            "descriptions",
            "descriptions: stocks from Massive (capped per night), ETFs from SEC prospectuses",
            descriptions,
            (descriptions.TABLE,),
            _descriptions,
            optional_sources=DESCRIPTION_SOURCES,
            settings="sources.toml [massive] descriptions_per_night, [sec_edgar] fund_quarters",
            params=(
                SESSION,
                Param("limit", ("--limit",), int, "ask Massive for at most N stocks this run"),
                Param("symbols", ("--symbols",), str, "comma-separated stocks (skips the ETFs)"),
                Param("only", ("--only",), str, "massive (stocks) or funds (ETFs)"),
                Param("force", ("--force",), None, "ask again even if described"),
            ),
            skip=_no_description_source,
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
            "rollups",
            "compute rollups for a session or backfill a range (--from/--to)",
            rollups,
            rollups.TABLES,
            _rollups,
            settings="rollups.toml",
            params=(
                SESSION,
                FROM,
                TO,
                Param("only", ("--only",), str, "comma-separated rollups, e.g. price_stats@v2"),
            ),
        ),
        Task(
            "verify",
            "compare the session's stored values with IBKR (IB Gateway, read-only market data)",
            verify,
            (verify.TABLE,),
            _verify,
            sources=("ibkr",),
            settings="verification.toml + sources.toml [ibkr]",
            params=(
                SESSION,
                Param("symbols", ("--symbols",), str, "comma-separated tickers (default: sample)"),
            ),
            skip=_gateway_down,
        ),
        Task(
            "ibkr-contracts",
            "IBKR contract ids (conid) of the optionable universe: new names, then monthly",
            ibkr_contracts,
            (ibkr_contracts.TABLE,),
            _ibkr_contracts,
            sources=("ibkr",),
            settings="sources.toml [ibkr] contracts_refresh_days, contracts_batch",
            params=(
                SESSION,
                Param("symbols", ("--symbols",), str, "comma-separated tickers (resolved now)"),
                Param("force", ("--force",), None, "re-resolve every contract"),
                Param("limit", ("--limit",), int, "resolve at most N contracts this run"),
            ),
            skip=_gateway_down,
        ),
        Task(
            "ibkr-iv",
            "IBKR implied / historical vol: nightly snapshot, or a resumable history backfill "
            "(--from/--to)",
            ibkr_iv,
            (ibkr_iv.TABLE,),
            _ibkr_iv,
            sources=("ibkr",),
            settings="sources.toml [ibkr] iv_batch, iv_history_days, iv_backfill_per_night",
            params=(
                SESSION,
                FROM,
                TO,
                Param("symbols", ("--symbols",), str, "comma-separated tickers"),
                Param("limit", ("--limit",), int, "backfill at most N underlyings this run"),
            ),
            skip=_gateway_down,
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
            "delete raw vendor responses, unfinished-run scratch and old live quotes after N days",
            purge,
            (),  # deletes raw files and scratch; produces no table
            _purge,
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
            _migrate_ids,
            params=(Param("dry_run", ("--dry-run",), None, "count only; write nothing"),),
        ),
        Task(
            "retire-features",
            "delete a superseded feature group's tables once its replacement covers them",
            retire_features,
            (),  # deletes a superseded table; produces none
            _retire_features,
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
