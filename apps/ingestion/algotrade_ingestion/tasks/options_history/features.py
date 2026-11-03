"""The ``option-history-features`` task (ADR 0088 decision 11, F7): the chain feature groups
(``data.option_history.splice.CHAIN_GROUPS``) for the sessions of the bought history before the
Cboe cutover, written to the history root under the same names (licence personal).

``algotrade-ingest run option-history-features --from D --to D [--force]``. The groups are the
site's own, computed by the same pure ``compute`` through the same runner (``compute_sessions``):
only the reader differs. ``HistoryChainReader`` is the splice with the three chain tables of a
history session (``chains/option_quotes``, ``chains/underlying_quotes``, ``chains/status``) built
from the history's quotes (``chain_frames``: the vendor's IV and delta are never fed in as Cboe's);
every other input is the main store's (the Treasury curve, dividend yield, earnings) and a group
that reads another's rows (``iv_history`` over ``iv30``) reads them from the history root, so a
group is committed before the next starts. Everything is under the history store's own lock and
``recover_unpublished`` against it (the importer's rule: the nightly keeps running).

A session with a group's partition already stored is skipped unless ``--force``. A session with no
history quotes is not a session of the range. Single-name rows rest on the importer's strict
as-of-session ``underlying_id`` (a name with none has no row, counted by the importer); the ids of
dead names wait on PR #968's listing history.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.data.chains import (
    CHAIN_STATUS,
    FIRST_CBOE_CHAIN_SESSION,
    OPTION_QUOTES,
    UNDERLYING_QUOTES,
)
from algotrade.data.option_history import reading
from algotrade.data.option_history.chain_frames import (
    chain_option_quotes,
    chain_status,
    chain_underlying_quotes,
)
from algotrade.data.option_history.splice import CHAIN_GROUPS, PERSONAL, SplicedReader
from algotrade.data.option_history.store import open_history
from algotrade.features.framework.runner import compute_sessions, rollup_params
from algotrade.features.site import site_features
from algotrade.services.jobs.exclusive import INGEST_TREE_LOCK, exclusive_run
from algotrade.storage.runs import RunRecord, RunStatus, published, start_run
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.paths.option_outcomes import SITE
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext, recover_unpublished
from algotrade_ingestion.tasks.options_history.outcomes import Pacing, locked

TASK = "option-history-features"
SOURCE = "option_history_features"
CHAIN_TABLES = (OPTION_QUOTES, UNDERLYING_QUOTES, CHAIN_STATUS)
SHOWN = 5


@dataclass(frozen=True)
class HistoryFeatureOptions:
    url: str | None = None  # the history store (default: ALGOTRADE_OPTION_HISTORY_URL)
    start: date | None = None
    end: date | None = None
    force: bool = False
    batch: int = 250  # sessions per committed run (about a year)


class HistoryChainReader(SplicedReader):
    """The splice plus the chain tables of a history session, built from the history's quotes."""

    def _clone(self, own_run: str | None, pin: int | None) -> "HistoryChainReader":
        return HistoryChainReader(self._backend, self._history, own_run, pin, self.reads)

    def table(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Any = None,
    ) -> pd.DataFrame | None:
        if table not in CHAIN_TABLES:
            return super().table(table, session_date, as_of, instruments)
        quotes = reading.option_quotes(self._history, session_date)
        if quotes is None:
            return None
        self.reads.append((table, session_date))
        if table == OPTION_QUOTES:
            frame = chain_option_quotes(quotes)
        elif table == CHAIN_STATUS:
            frame = chain_status(quotes)
        else:
            under = reading.underlying_quotes(self._history, session_date)
            frame = chain_underlying_quotes(under, quotes)
        if instruments is not None:
            key = "underlying_id" if table == OPTION_QUOTES else "instrument_id"
            frame = frame[frame[key].isin(list(instruments))]
        return frame.reset_index(drop=True)

    def has_partition(self, table: str, day: date) -> bool:
        if table in CHAIN_TABLES:
            return self._history.has_partition(reading.QUOTES, day)
        return super().has_partition(table, day)


def history_sessions(history: StoreReader, options: HistoryFeatureOptions) -> list[date]:
    """The history sessions of the range, before the cutover."""
    if options.start is None or options.end is None:
        raise ConfigurationError("option-history-features needs --from and --to")
    found = [
        s
        for s in reading.sessions(history)
        if options.start <= s <= min(options.end, FIRST_CBOE_CHAIN_SESSION - timedelta(days=1))
    ]
    if not found:
        raise ConfigurationError(
            f"no history session in {options.start}..{options.end} before "
            f"{FIRST_CBOE_CHAIN_SESSION}"
        )
    return found


def stored_imports(writer: StoreWriter, key: str) -> dict[str, str]:
    """Session (ISO) -> the import run its stored ``key`` partition was computed from."""
    found: dict[str, str] = {}
    for record in writer.runs_for(f"{TASK}:{key}"):
        if published(record):
            found.update(record.stats.get(key, {}).get("import_runs", {}))
    return found


def compute_history_features(
    ctx: TaskContext,
    today: date,
    options: HistoryFeatureOptions,
    open_store: Callable[[str | None], Backend] = open_history,
    pacing: Pacing | None = None,
) -> RunRecord:
    """Each chain group over the range in batches of ``options.batch`` sessions, one committed run
    per (group, batch) in the history store, in group order -> the last batch's record. A batch
    that raised FAILs its run and stops the rest (a later group would read its missing rows); what
    committed before it stays, and a re-run resumes after it."""
    pacing = pacing or Pacing()
    backend = open_store(options.url)
    writer, history = StoreWriter(backend), StoreReader(backend)
    sessions = history_sessions(history, options)
    imports = {s.isoformat(): reading.session_run(history, s) for s in sessions}
    configs = ctx.configs or SITE
    groups = site_features(configs).groups
    params = rollup_params(configs, list(groups.values()))
    record: RunRecord | None = None
    carried: dict[str, Any] = {"no_id_rows": _no_id_rows(history, imports)}
    for key in CHAIN_GROUPS:
        group = groups[key]
        held = stored_imports(writer, key)
        todo = [
            s
            for s in sessions
            if options.force or not _current(history, group.table, s, held, imports)
        ]
        stats: dict[str, Any] = {
            "sessions": 0,
            "rows": 0,
            "no_input": 0,
            "no_input_sessions": [],
            "seconds": 0.0,
        }
        stats.update(skipped=len(sessions) - len(todo), licence=PERSONAL, history_partitions_read=0)
        for i in range(0, len(todo), options.batch):
            chunk = todo[i : i + options.batch]
            open_store(options.url)  # the drive is still mounted and marked (HistoryUnavailable)
            reader = HistoryChainReader(ctx.writer.backend, history)
            hctx = replace(ctx, writer=writer, reader=reader)
            started = time.monotonic()
            with locked(ctx.writer.backend, INGEST_TREE_LOCK, pacing), exclusive_run(backend):
                recover_unpublished(writer, ctx.clock())
                with IngestRun(hctx, f"{TASK}:{key}", chunk[-1]) as run:
                    run.stats.update(carried)
                    rows = written = 0
                    missing: list[str] = []
                    for result in compute_sessions(run.reader, group, chunk, params[key]):
                        if result.frame is None:
                            missing.append(result.session.isoformat())
                            continue
                        run.write(group.table, result.frame, SOURCE, session=result.session)
                        rows, written = rows + len(result.frame), written + 1
                    stats["sessions"] += written
                    stats["rows"] += rows
                    stats["no_input"] += len(missing)
                    stats["no_input_sessions"] = [*stats["no_input_sessions"], *missing][:SHOWN]
                    stats["seconds"] = round(stats["seconds"] + time.monotonic() - started, 2)
                    stats["history_partitions_read"] += len(reader.reads)
                    run.stats[key] = {
                        **stats,
                        "import_runs": {s.isoformat(): imports[s.isoformat()] for s in chunk},
                    }
            record = run.record
        carried[key] = dict(stats)
        if record is not None:
            record.stats.update(carried)
    if record is None:  # nothing to compute: every session already current
        record = start_run(TASK, today, ctx.clock())
        record.status, record.finished_at = RunStatus.COMPLETE, ctx.clock()
        record.stats.update(carried)
    return record


def _current(
    history: StoreReader,
    table: str,
    day: date,
    held: dict[str, str],
    imports: dict[str, str | None],
) -> bool:
    """Whether ``table`` holds ``day`` computed from the import now stored for it."""
    return (
        history.has_partition(table, day) and held.get(day.isoformat()) == imports[day.isoformat()]
    )


def _no_id_rows(history: StoreReader, imports: dict[str, str | None]) -> int:
    """The option rows the importer left out for want of an ``underlying_id`` (its own counts):
    names a feature row cannot exist for, so a single-name history is read with that in view."""
    total = 0
    for run_id in imports.values():
        found = history.run(run_id) if run_id else None
        total += int(found.stats.get("null_underlying_rows", 0)) if found else 0
    return total
