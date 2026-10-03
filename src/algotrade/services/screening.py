"""Use case: run a registered screener for a session date and save an audited result."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd

from algotrade.engines.screening.runner import (
    DEFAULT_MIN_COVERAGE,
    RunCoverage,
    ScreenRun,
    run_screen,
)
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


def run_screener(
    reader: StoreReader,
    writer: ResultWriter,
    name: str,
    session_date: date,
    now: datetime | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> ScreenOutcome:
    now = now or datetime.now(UTC)
    screener = create_screener(name)
    universe = load_universe(reader, session_date)
    view = feature_view(reader, screener.requires, session_date, universe.instruments)
    run = run_screen(screener, view, list(universe.frame["instrument_id"]), min_coverage)
    if universe.is_stale(session_date) and run.coverage is RunCoverage.COMPLETE:
        run = ScreenRun(
            run.screener,
            run.rows,
            run.universe_rows,
            run.unique_instruments,
            run.duplicates_removed,
            RunCoverage.UNIVERSE_INCOMPLETE,
        )
    run_id = new_run_id(f"screen-{name}", session_date, now)
    audit = {
        **run.audit(),
        "universe_snapshot": universe.snapshot_date.isoformat(),
        "universe_version": universe.version,
        "universe_last_verified": universe.last_verified.isoformat()
        if universe.last_verified
        else None,
        "universe_rows_loaded": universe.rows_loaded,
    }
    if run.rows:
        writer.write_result(name, session_date, run_id, rows_frame(run, session_date, run_id, now))
    status = RunStatus.COMPLETE if run.coverage is RunCoverage.COMPLETE else RunStatus.PARTIAL
    writer.save_run(
        RunRecord(run_id, f"screen-{name}", session_date, now, status, now, stats=audit)
    )
    return ScreenOutcome(run_id, session_date, run, universe, audit)
