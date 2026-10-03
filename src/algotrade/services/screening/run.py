"""Use case: run a registered screener for a session date and save an audited result."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd

from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.data.reference import Universe, load_universe
from algotrade.engines.screening.runner import RunCoverage, ScreenRun, run_screen
from algotrade.services.features import config_features
from algotrade.services.selection import select
from algotrade.services.views import feature_view
from algotrade.storage.runs import start_run
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.strategies.screeners.registry import create_screener


def run_job_name(config_id: str, user: str) -> str:
    """The run-record ``job`` of a screen of ``config_id`` for ``user``."""
    return f"screen-{config_id}-{user}"


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
    screening = config.screening
    screener = create_screener(config.config.impl, **dict(config.config.params))
    universe = load_universe(reader, session_date)
    selected = select(reader, config.selection, session_date, features=config_features(config))
    view = feature_view(reader, screener.requires, session_date, selected.instruments)
    run = run_screen(screener, view, list(selected.instruments), screening.min_coverage)
    if selected.empty:
        run = _with_coverage(run, RunCoverage.EMPTY_SELECTION)
    elif run.coverage is RunCoverage.COMPLETE and universe.is_stale(
        session_date, screening.max_universe_age_days
    ):
        run = _with_coverage(run, RunCoverage.UNIVERSE_INCOMPLETE)
    user = config.user.user_id
    record = start_run(run_job_name(config.config.id, user), session_date, now)
    run_id = record.run_id
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
        # The universe came from a snapshot after the session: results carry survivorship bias.
        "universe_pre_snapshot": universe.pre_snapshot,
    }
    if run.rows:
        frame = rows_frame(run, session_date, run_id, now)
        frame["user_id"], frame["config_id"], frame["config_hash"] = (
            user,
            config.config.id,
            config.hash,
        )
        writer.write_result(config.config.impl, session_date, run_id, frame)
    complete = run.coverage is RunCoverage.COMPLETE
    writer.save_run(record.finish(now, complete=complete, stats=audit))
    return ScreenOutcome(run_id, session_date, run, universe, audit)
