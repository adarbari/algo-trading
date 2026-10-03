"""Compute rollups for one session or a range of sessions (a backfill), point in time.

``compute_sessions`` loads each input once per chunk of up to ``CHUNK`` sessions (the whole
range for a nightly run; a two-year backfill in a few reads, with bounded memory), then for
each session hands ``compute`` only the rows on or before that session and types the
result by the declaration (``framework.columns``). The same code path serves one session
and a backfill, so a backfilled row equals the row computed on its own session.

``rollup_params`` reads every rollup's parameters from ``config/site/rollups.toml`` through
the one settings loader.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.config.site.settings import SiteDocuments, load_rollups
from algotrade.data import StoreReader
from algotrade.features.framework.columns import conform
from algotrade.features.framework.declaration import Rollup
from algotrade.features.framework.inputs import load_input

CHUNK = 126  # sessions per input load (half a year: ~2 GB of daily bars at most)


@dataclass(frozen=True)
class SessionResult:
    """One session of one rollup: the typed rows, or why there are none (``no_input``)."""

    session: date
    frame: pd.DataFrame | None
    no_input: str | None = None


def rollup_params(configs: SiteDocuments | None, rollups: Sequence[Rollup]) -> dict[str, Any]:
    """Each rollup's params (``rollups.toml`` over its defaults; defaults without a store)."""
    declared = {r.key: r.params for r in rollups}
    return load_rollups(configs, declared) if configs is not None else dict(declared)


def _check_point_in_time(rollup: Rollup, table: str, frame: pd.DataFrame, session: date) -> None:
    """Loaders return frames sorted by ``session_date``: the last row is the latest."""
    if "session_date" in frame.columns and len(frame):
        latest = frame["session_date"].iloc[-1]
        if latest > session:
            raise AssertionError(f"{rollup.key}: {table} rows from {latest} reached {session}")


def compute_sessions(
    reader: StoreReader,
    rollup: Rollup,
    sessions: Sequence[date],
    params: Any = None,
    chunk: int = CHUNK,
) -> Iterator[SessionResult]:
    """``rollup`` for each session in ``sessions`` (ascending), one result per session."""
    params = rollup.params if params is None else params
    for i in range(0, len(sessions), chunk):
        yield from _compute_chunk(reader, rollup, sessions[i : i + chunk], params)


def _compute_chunk(
    reader: StoreReader, rollup: Rollup, sessions: Sequence[date], params: Any
) -> Iterator[SessionResult]:
    lookbacks = {i.table: i.sessions_back(params) for i in rollup.inputs}
    loaded = {
        i.table: load_input(reader, i.table, sessions, lookbacks[i.table]) for i in rollup.inputs
    }
    for session in sessions:
        frames: dict[str, pd.DataFrame | None] = {}
        missing = []
        for spec in rollup.inputs:
            frame = loaded[spec.table].at(session, lookbacks[spec.table])
            if frame is None and spec.required:
                missing.append(spec.table)
            if frame is not None:
                _check_point_in_time(rollup, spec.table, frame, session)
            frames[spec.table] = frame
        if missing:
            yield SessionResult(session, None, f"no {', '.join(missing)} for {session}")
            continue
        out = rollup.compute(frames, session, params)
        yield SessionResult(session, conform(rollup.table, out, rollup.columns))


def compute_one(
    reader: StoreReader, rollup: Rollup, session: date, params: Any = None
) -> SessionResult:
    """``rollup`` for a single session."""
    return next(compute_sessions(reader, rollup, [session], params))


def by_key(rollups: Mapping[str, Rollup], only: Sequence[str] | None) -> list[Rollup]:
    """The rollups named in ``only`` (keys ``<name>@v<N>``; all when empty), in registry order."""
    if not only:
        return list(rollups.values())
    unknown = sorted(set(only) - set(rollups))
    if unknown:
        raise KeyError(f"unknown rollups {unknown}; known: {sorted(rollups)}")
    return [r for k, r in rollups.items() if k in only]
