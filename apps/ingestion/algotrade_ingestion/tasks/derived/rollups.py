"""The ``rollups`` task: compute every due rollup (``features.site``: the code groups and the
materialised expression features) for a session, or a named subset, or backfill them over a
range of sessions.

Each rollup runs through the framework (``features.framework.runner``): its inputs are read
once for the whole range through ``algotrade.data``, then each session's row uses only data
on or before that session, and is written to that session's partition of
``rollups/instrument/<name>@v<N>``. A rollup whose required input has nothing for a session
(no chains before chains were collected, no bars on a missing day) writes nothing for it and
reports the session under ``no_input``; that is not a failure, except for a rollup named with
``--only`` that computed nothing at all (the run is PARTIAL). A rollup that raises is a
failed item (PARTIAL) and the others still run.

Rollups run in dependency order (``FeatureSet.groups``): a rollup that reads another
rollup's table runs after it and reads what it just wrote (stored rows for sessions it did
not write). When a rollup fails, the rollups that read it in this run are not computed (a
failed item each, naming the dependency), so they never read a stale or partial input.

``TABLES`` (what the task may write) comes from the site config at import (``config_dir``):
a materialised expression feature adds its table (``rollups/instrument/<name>@v<N>``).
"""

import time
from collections.abc import Sequence
from datetime import date
from functools import partial
from typing import Any

from algotrade.config.env import config_dir
from algotrade.core.time.calendar import sessions_between
from algotrade.features.framework.declaration import FeatureGroup
from algotrade.features.framework.graph import dependents
from algotrade.features.framework.runner import by_key, compute_sessions, rollup_params
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import (
    FAILURES,
    IngestRun,
    TaskContext,
    status_label,
)

TASK = "rollups"
SOURCE = "rollups"
SITE = FileConfigStore(config_dir())  # the features when the task has no config store
TABLES = tuple(r.table for r in site_features(SITE).groups.values())
SHOWN = 5  # no-input sessions listed per rollup in the run stats


def _one(
    run: IngestRun, rollup: FeatureGroup, sessions: Sequence[date], params: Any, named: bool
) -> str:
    started = time.monotonic()
    rows, written, no_input = 0, 0, []
    for result in compute_sessions(run.reader, rollup, sessions, params):
        if result.frame is None:
            no_input.append(result.session.isoformat())
            continue
        run.write(rollup.table, result.frame, SOURCE, session=result.session)
        rows, written = rows + len(result.frame), written + 1
    run.stats[rollup.key] = {
        "sessions": written,
        "rows": rows,
        "no_input": len(no_input),
        "no_input_sessions": no_input[:SHOWN],
        "seconds": round(time.monotonic() - started, 2),
    }
    if not written:
        if named:
            run.partial(f"{rollup.key}: no input for any session")
        return "NO_INPUT"
    return f"OK: {written} sessions, {rows} rows"


def compute_rollups(
    ctx: TaskContext,
    session: date,
    start: date | None = None,
    end: date | None = None,
    only: Sequence[str] = (),
) -> RunRecord:
    """Rollups for ``session``, or for every exchange session in ``start..end``."""
    sessions = sessions_between(start, end or session) if start else [session]
    if not sessions:
        raise ValueError(f"no exchange session in {start}..{end or session}")
    groups = site_features(ctx.configs or SITE).groups
    rollups = by_key(groups, only)
    params = rollup_params(ctx.configs, list(groups.values()))  # validates the whole file
    with IngestRun(ctx, TASK, sessions[-1]) as run:
        run.stats["range"] = [sessions[0].isoformat(), sessions[-1].isoformat(), len(sessions)]
        blocked: dict[str, str] = {}
        for rollup in rollups:
            if rollup.key in blocked:
                run.fail(rollup.key, f"not computed: {blocked[rollup.key]} failed", "FAILED")
                continue
            work = partial(_one, run, rollup, sessions, params[rollup.key], bool(only))
            if status_label(run.attempt(rollup.key, work)) in FAILURES:
                blocked.update(dict.fromkeys(dependents(rollups, rollup.key), rollup.key))
        run.stats["failed"] = run.failures()
    return run.record
