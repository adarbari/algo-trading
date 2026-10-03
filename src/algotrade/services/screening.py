"""Use case: run a registered screener for a session date and save an audited result."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd

from algotrade.config.resolve import ResolvedConfig
from algotrade.core.errors import ConfigurationError
from algotrade.engines.screening.runner import RunCoverage, ScreenRun, run_screen
from algotrade.services.selection import select
from algotrade.services.views import Universe, feature_view, load_universe
from algotrade.storage.readers import StoreReader
from algotrade.storage.result_writer import ResultWriter
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.strategies.screeners.registry import create_screener


@dataclass(frozen=True)
class ScreenOutcome:
    run_id: str
    session_date: date
    run: ScreenRun
    universe: Universe
    audit: dict[str, object]


def rows_frame(run: ScreenRun, session_date: date, run_id: str, now: datetime) -> pd.DataFrame:
    records = [
        {
            "instrument_id": r.instrument_id,
            "decision": r.decision.value,
            "score": r.score,
            "reasons": "; ".join(r.reasons),
            **r.values,
        }
        for r in run.rows
    ]
    frame = pd.DataFrame.from_records(records)
    frame["session_date"] = session_date
    frame["knowledge_ts"] = pd.Timestamp(now)
    frame["source"] = f"screener:{run.screener}"
    frame["run_id"] = run_id
    return frame


def _with_coverage(run: ScreenRun, coverage: RunCoverage) -> ScreenRun:
    return ScreenRun(
        run.screener,
        run.rows,
        run.universe_rows,
        run.unique_instruments,
        run.duplicates_removed,
        coverage,
    )


def run_screener(
    reader: StoreReader,
    writer: ResultWriter,
    config: ResolvedConfig,
    session_date: date,
    now: datetime | None = None,
) -> ScreenOutcome:
    """Select -> screen -> audit -> save, for one resolved screener config and user."""
    now = now or datetime.now(UTC)
    if config.config.kind != "screener":
        raise ConfigurationError(f"{config.config.id} is a {config.config.kind}, not a screener")
    if config.selection is None:
        raise ConfigurationError(f"{config.config.id}: a screener needs a selection")
    screening = config.settings["screening"]
    screener = create_screener(config.config.impl, **dict(config.config.params))
    universe = load_universe(reader, session_date)
    selected = select(reader, config.selection, session_date)
    view = feature_view(reader, screener.requires, session_date, selected.instruments)
    run = run_screen(screener, view, list(selected.instruments), float(screening["min_coverage"]))
    if selected.empty:
        run = _with_coverage(run, RunCoverage.EMPTY_SELECTION)
    elif run.coverage is RunCoverage.COMPLETE and universe.is_stale(
        session_date, int(screening["max_universe_age_days"])
    ):
        run = _with_coverage(run, RunCoverage.UNIVERSE_INCOMPLETE)
    user = config.user.user_id
    run_id = new_run_id(f"screen-{config.config.id}-{user}", session_date, now)
    audit = {
        **run.audit(),
        "user": user,
        "config_id": config.config.id,
        "config_hash": config.hash,
        "config_layers": list(config.layers),
        "selection": selected.as_dict(),
        "universe_snapshot": universe.snapshot_date.isoformat(),
        "universe_version": universe.version,
        "universe_last_verified": universe.last_verified.isoformat()
        if universe.last_verified
        else None,
        "universe_rows_loaded": universe.rows_loaded,
    }
    if run.rows:
        frame = rows_frame(run, session_date, run_id, now)
        frame["user_id"], frame["config_id"], frame["config_hash"] = (
            user,
            config.config.id,
            config.hash,
        )
        writer.write_result(config.config.impl, session_date, run_id, frame)
    status = RunStatus.COMPLETE if run.coverage is RunCoverage.COMPLETE else RunStatus.PARTIAL
    job = f"screen-{config.config.id}-{user}"
    writer.save_run(RunRecord(run_id, job, session_date, now, status, now, stats=audit))
    return ScreenOutcome(run_id, session_date, run, universe, audit)
