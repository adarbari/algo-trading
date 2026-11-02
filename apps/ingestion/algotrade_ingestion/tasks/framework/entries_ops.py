"""Task entries for verification, descriptions, IBKR, quality and maintenance tasks (ADR 0019)."""

from algotrade.core.time.calendar import sessions_ending
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.derived import history_copy
from algotrade_ingestion.tasks.edges import picks as edge_picks
from algotrade_ingestion.tasks.edges import verdicts as edge_verdicts
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
from algotrade_ingestion.tasks.maintenance.compaction import task as compact_task
from algotrade_ingestion.tasks.market import (
    ibkr_iv,
)
from algotrade_ingestion.tasks.market.futures import curves as futures_curves
from algotrade_ingestion.tasks.profile import descriptions
from algotrade_ingestion.tasks.reference import (
    ibkr_contracts,
)
from algotrade_ingestion.tasks.screens import screen_runs_backfill, screen_values_recluster
from algotrade_ingestion.tasks.shorting import restamp
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


def run_futures_curves(ctx: TaskContext, p: Params) -> RunRecord:
    return futures_curves.nightly_curves(
        ctx, source_guards.ibkr_source(ctx), session_of(p), symbols(p)
    )


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


def run_edge_picks(ctx: TaskContext, p: Params) -> RunRecord:
    """``--date D`` is the one session (the nightly's); ``--from`` / ``--to`` a window."""
    options = edge_picks.Options(p.get("start"), p.get("end"), p.get("edge"))
    return edge_picks.store_picks(ctx, session_of(p), options)


def run_edge_verdicts(ctx: TaskContext, p: Params) -> RunRecord:
    """The window is ``--from`` / ``--to`` on a run's range end, or ``--date D`` for [D, D]; no
    flag is every site edge. The post-session step passes ``all_edges``: its ``session`` is not a
    window (an edge not evaluated tonight still has its canonical run)."""
    start, end = p.get("start"), p.get("end")
    if p.get("session") and not (start or end or p.get("all_edges")):
        start = end = p["session"]
    options = edge_verdicts.Options(
        start, end, p.get("limit"), bool(p.get("dry_run")), bool(p.get("verify")),
        bool(p.get("expect_same")),
    )  # fmt: skip
    return edge_verdicts.rejudge_edges(ctx, options, p.get("edge"))


def run_screen_runs_backfill(ctx: TaskContext, p: Params) -> RunRecord:
    """``--date D`` is the window [D, D]; no flag at all is every stored session."""
    start, end = p.get("start"), p.get("end")
    if p.get("session") and not (start or end):
        start = end = p["session"]
    return screen_runs_backfill.backfill_screen_runs(ctx, start, end, p.get("limit"))


def run_screen_values_recluster(ctx: TaskContext, p: Params) -> RunRecord:
    """``--date D`` is the window [D, D]; no flag at all is every stored session."""
    start, end = p.get("start"), p.get("end")
    if p.get("session") and not (start or end):
        start = end = p["session"]
    return screen_values_recluster.recluster_screen_values(ctx, start, end, p.get("limit"))


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


def run_restamp_known_from(ctx: TaskContext, p: Params) -> RunRecord:
    return restamp.restamp(ctx, session_of(p), dry_run=bool(p.get("dry_run")))


def run_compact_runs(ctx: TaskContext, p: Params) -> RunRecord:
    return compact_task.compact(
        ctx,
        session_of(p),
        str(p["table"]),
        p.get("start"),
        p.get("end"),
        p.get("limit"),
        bool(p.get("dry_run")),
        verify=bool(p.get("verify")),
        workers=p.get("workers"),
        beside_ingest=bool(p.get("beside_ingest")),
    )
