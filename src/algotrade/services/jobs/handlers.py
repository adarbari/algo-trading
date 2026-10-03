"""Job kinds the library provides. Apps add their own (e.g. ingestion's ``nightly``).

Resources expected in ``JobContext.resources``: ``reader`` (StoreReader), ``configs``
(ConfigStore) and, to save results, ``writer`` (ResultWriter).

Identity: a backtest or screen job is the same job when the *resolved config* (its hash),
the dates and the user are the same, so editing a config and resubmitting runs again.
"""

from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from algotrade.engines.screening.runner import RunCoverage
from algotrade.services.backtests import run_configured_backtest
from algotrade.services.configs import resolve_config
from algotrade.services.exports import run_exports
from algotrade.services.jobs.runner import JobContext, JobKind
from algotrade.services.screening import run_screener


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
        "data_versions": outcome.versions,
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


LIBRARY_HANDLERS: Mapping[str, JobKind] = {
    "backtest": JobKind(backtest_job, backtest_identity),
    "screen": JobKind(screen_job, screen_identity),
}
