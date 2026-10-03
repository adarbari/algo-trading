"""Job handlers the library provides. Apps add their own (e.g. ingestion's ``nightly``).

Resources expected in ``JobContext.resources``: ``reader`` (StoreReader), ``configs``
(ConfigStore) and, for jobs that save results, ``writer`` (ResultWriter).
"""

from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from algotrade.engines.screening.runner import RunCoverage
from algotrade.services.backtests import run_configured_backtest
from algotrade.services.configs import resolve_config
from algotrade.services.exports import run_exports
from algotrade.services.jobs.runner import JobContext, JobHandler
from algotrade.services.screening import run_screener


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
    )
    return {
        "config": config.config.id,
        "config_hash": config.hash,
        "selection": outcome.selection.as_dict(),
        "metrics": outcome.result.metrics.as_dict(),
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


LIBRARY_HANDLERS: Mapping[str, JobHandler] = {"backtest": backtest_job, "screen": screen_job}
