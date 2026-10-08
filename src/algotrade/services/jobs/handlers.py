"""Job kinds the library provides. Apps add their own (e.g. ingestion's ``nightly``).

Resources expected in ``JobContext.resources``: ``reader`` (``algotrade.data.StoreReader``),
``configs`` (ConfigStore) and, to save results, ``writer`` (ResultWriter).

Identity: a backtest or screen job is the same job when the *resolved config* (its hash),
the dates and the user are the same, so editing a config and resubmitting runs again.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from algotrade.config.edges.loading import load_edges
from algotrade.config.site.settings import load_sources
from algotrade.core.model.errors import ConfigurationError
from algotrade.engines.screening.runner import RunCoverage
from algotrade.services.backtests.run import run_configured_backtest
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.results import (
    edge_eval_frame,
    records,
    survivorship,
    write_edge_eval,
)
from algotrade.services.jobs.runner import JobContext, JobKind
from algotrade.services.screening.exports import run_exports
from algotrade.services.screening.run import run_screener


def _config_hash(params: Mapping[str, Any], ctx: JobContext) -> str:
    resolved = resolve_config(
        ctx.resources["configs"], params["config"], ctx.user, params.get("overrides")
    )
    return resolved.hash


def backtest_identity(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    return {
        "config_hash": _config_hash(params, ctx),
        "start": params["start"],
        "end": params["end"],
    }


def backtest_job(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    """params: ``config`` (id), ``start``, ``end`` (ISO dates), optional ``overrides``."""
    config = resolve_config(
        ctx.resources["configs"], params["config"], ctx.user, params.get("overrides")
    )
    outcome = run_configured_backtest(
        ctx.resources["reader"],
        config,
        date.fromisoformat(params["start"]),
        date.fromisoformat(params["end"]),
        ctx.resources.get("writer"),
    )
    return {
        "config": config.config.id,
        "config_hash": config.hash,
        "run_id": outcome.run_id,
        "selection": outcome.selection.as_dict(),
        **outcome.data_stats(),
        "metrics": outcome.result.metrics.as_dict(),
    }


def screen_identity(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    return {
        "config_hash": _config_hash(params, ctx),
        "session": params["session"],
        "export_dir": params.get("export_dir"),
    }


def screen_job(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    """params: ``config`` (id), ``session`` (ISO date), optional ``export_dir``."""
    config = resolve_config(ctx.resources["configs"], params["config"], ctx.user)
    outcome = run_screener(
        ctx.resources["reader"],
        ctx.resources["writer"],
        config,
        date.fromisoformat(params["session"]),
        sources=load_sources(ctx.resources["configs"]),
    )
    exports = (
        run_exports(outcome, config, Path(params["export_dir"])) if params.get("export_dir") else ()
    )
    return {
        **outcome.audit,
        "run_id": outcome.run_id,
        "exports": [str(p) for p in exports],
        "_partial": outcome.run.coverage is not RunCoverage.COMPLETE,
    }


def edge_eval_job(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    """params: ``edge`` (id), ``start``, ``end`` (ISO dates), optional ``as_of`` (ISO instant:
    the outcomes known by then; default now). The harness's rows land in ``results/edge_eval``."""
    configs, now = ctx.resources["configs"], datetime.now(UTC)
    edges = {e.id: e for e in load_edges(configs, ctx.user.user_id)}
    if params["edge"] not in edges:
        raise ConfigurationError(f"unknown edge {params['edge']!r}; known: {sorted(edges)}")
    as_of = datetime.fromisoformat(params["as_of"]) if params.get("as_of") else now
    evaluation = evaluate_edge(
        ctx.resources["reader"],
        ctx.resources["writer"],
        configs,
        ctx.user,
        edges[params["edge"]],
        date.fromisoformat(params["start"]),
        date.fromisoformat(params["end"]),
        as_of,
    )
    record = write_edge_eval(ctx.resources["writer"], evaluation, now)
    rows = edge_eval_frame(evaluation, record.run_id, now)
    return {
        "edge": evaluation.edge_id,
        "run_id": record.run_id,
        "run_hash": evaluation.run_hash,
        "as_of": as_of.isoformat(),
        "trials": evaluation.trials,
        "universe_snapshot": evaluation.snapshot.isoformat() if evaluation.snapshot else None,
        "survivorship": {str(h): list(v) for h, v in survivorship(evaluation).items()},
        "unclosed_sessions": {str(h): n for h, n in evaluation.unclosed_sessions.items()},
        "rows": records(rows),
    }


LIBRARY_HANDLERS: Mapping[str, JobKind] = {
    "backtest": JobKind(backtest_job, backtest_identity),
    "screen": JobKind(screen_job, screen_identity),
    "edge-eval": JobKind(edge_eval_job),
}
