"""Task entries for verification, descriptions, IBKR, quality and maintenance tasks (ADR 0019)."""

from algotrade.core.time.calendar import sessions_ending
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.derived import history_copy
from algotrade_ingestion.tasks.framework import source_guards
from algotrade_ingestion.tasks.framework.params import Params, session_of, symbols
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance import (
    bar_quality,
    golden,
    migrate_ids,
    purge,
    quality,
    retire_features,
)
from algotrade_ingestion.tasks.market import (
    ibkr_iv,
)
from algotrade_ingestion.tasks.profile import descriptions
from algotrade_ingestion.tasks.reference import (
    ibkr_contracts,
)
from algotrade_ingestion.tasks.verification import verify
from algotrade_sources.framework.base import (
    FixtureSource,
)


def run_verify(ctx: TaskContext, p: Params) -> RunRecord:
    return verify.verify(ctx, session_of(p), symbols(p))


def run_descriptions(ctx: TaskContext, p: Params) -> RunRecord:
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
        symbols=symbols(p),
        force=bool(p.get("force")),
    )


def run_ibkr_contracts(ctx: TaskContext, p: Params) -> RunRecord:
    return ibkr_contracts.resolve_contracts(
        ctx,
        source_guards.ibkr_source(ctx),
        session_of(p),
        symbols(p),
        bool(p.get("force")),
        p.get("limit"),
    )


def run_ibkr_iv(ctx: TaskContext, p: Params) -> RunRecord:
    if p.get("start"):
        end = p.get("end") or session_of(p)
        source = source_guards.ibkr_source(ctx)
        return ibkr_iv.backfill_ivs(ctx, source, p["start"], end, symbols(p), p.get("limit"))
    return ibkr_iv.nightly_ivs(ctx, source_guards.ibkr_source(ctx), session_of(p), symbols(p))


def run_ibkr_iv_repair(ctx: TaskContext, p: Params) -> RunRecord:
    if not p.get("start"):
        raise ValueError("ibkr-iv-repair needs --from (the first session to check)")
    return ibkr_iv.repair_ivs(ctx, p["start"], p.get("end") or session_of(p))


def run_quality(ctx: TaskContext, p: Params) -> RunRecord:
    return quality.run_quality(ctx, session_of(p))


def run_bar_quality(ctx: TaskContext, p: Params) -> RunRecord:
    session = session_of(p)
    start = p.get("start") or sessions_ending(session, bar_quality.TRAILING_SESSIONS)[0]
    ids = symbols(p, "only")
    return bar_quality.run_bar_quality(
        ctx, session, start, p.get("end"), list(ids) if ids else None
    )


def run_history_copy(ctx: TaskContext, p: Params) -> RunRecord:
    return history_copy.build_copies(ctx, session_of(p))


def run_purge(ctx: TaskContext, p: Params) -> RunRecord:
    return purge.purge(ctx, session_of(p), p.get("keep_days"), p.get("staging_keep_days"))


def run_migrate_ids(ctx: TaskContext, p: Params) -> RunRecord:
    return migrate_ids.migrate_ids(ctx, dry_run=bool(p.get("dry_run")))


def run_retire_features(ctx: TaskContext, p: Params) -> RunRecord:
    return retire_features.retire(ctx, session_of(p), str(p["group"]), bool(p.get("dry_run")))


def run_golden_load(ctx: TaskContext, p: Params) -> RunRecord:
    # ``golden_dir`` chose the directory when the registry built the fixture source.
    source = ctx.sources["synthetic"]
    if not isinstance(source, FixtureSource):
        raise TypeError("synthetic must be a FixtureSource (the golden CSVs)")
    return golden.load_golden(ctx, source)
