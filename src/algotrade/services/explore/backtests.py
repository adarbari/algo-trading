"""Saved backtest runs: the list (per strategy config, the user's and the site's) and one
run's detail: metrics, selection audit, data versions, rebalances, equity curve and fills."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.config.user import SITE_USER
from algotrade.services.backtests.run import EQUITY, FILLS, run_job_name
from algotrade.services.explore.configs import config_list
from algotrade.services.explore.store import NotFoundError, ReadStore, records
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import result_table

JOB_PREFIX = "backtest-"


@dataclass(frozen=True)
class BacktestSummary:
    run_id: str
    config_id: str
    user: str
    status: str
    start: str | None
    end: date
    started_at: datetime
    finished_at: datetime | None
    metrics: dict[str, Any]


def _summary(run: RunRecord) -> BacktestSummary:
    stats = run.stats
    return BacktestSummary(
        run_id=run.run_id,
        config_id=str(stats.get("config_id", "")),
        user=str(stats.get("user", "")),
        status=run.status.value,
        start=stats.get("start"),
        end=run.session_date,
        started_at=run.started_at,
        finished_at=run.finished_at,
        metrics=dict(stats.get("metrics") or {}),
    )


def backtest_runs(store: ReadStore) -> list[BacktestSummary]:
    """Every saved run of every strategy config the user sees, newest first."""
    owners = list(dict.fromkeys([store.user.user_id, SITE_USER]))
    ids = sorted({c.config_id for c in config_list(store) if c.kind in ("strategy", None)})
    runs = [r for i in ids for o in owners for r in store.reader.runs(run_job_name(i, o))]
    return [_summary(r) for r in sorted(runs, key=lambda r: r.started_at, reverse=True)]


@dataclass(frozen=True)
class BacktestDetail:
    summary: BacktestSummary
    config_hash: str | None
    selection: dict[str, Any]
    data: dict[str, Any]  # as_of, data_versions, reference_snapshot, survivorship_bias
    rebalances: list[dict[str, Any]]
    equity: list[dict[str, Any]]  # ts, equity, gross_exposure
    fills: list[dict[str, Any]]  # ts, instrument_id, side, quantity, price, commission


def _result(store: ReadStore, name: str, run: RunRecord) -> pd.DataFrame:
    """The run's rows of ``results/<name>`` (read as of the run: a later run with the same
    end date replaces the partition)."""
    frame = store.reader.table(result_table(name), run.session_date, as_of=run.started_at)
    if frame is None:
        return pd.DataFrame()
    return frame[frame["run_id"] == run.run_id].sort_values("ts", kind="stable")


def backtest_detail(store: ReadStore, run_id: str) -> BacktestDetail:
    try:
        run = store.reader.run(run_id)
    except ValueError as exc:
        raise NotFoundError(f"run {run_id!r}: {exc}") from exc
    if run is None or not run.job.startswith(JOB_PREFIX):
        raise NotFoundError(f"no backtest run {run_id!r}")
    stats = run.stats
    keep = ("instrument_id", "user_id", "config_id", "config_hash")
    equity = _result(store, EQUITY, run)
    fills = _result(store, FILLS, run)
    return BacktestDetail(
        summary=_summary(run),
        config_hash=stats.get("config_hash"),
        selection=dict(stats.get("selection") or {}),
        data={
            k: stats.get(k)
            for k in ("as_of", "data_versions", "reference_snapshot", "survivorship_bias")
        },
        rebalances=list((stats.get("rebalance") or {}).get("evaluations") or []),
        equity=records(equity, keep),
        fills=records(fills, keep[1:]),
    )
