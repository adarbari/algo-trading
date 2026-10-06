"""Compute feature groups for one session or a range of sessions (a backfill), point in time.

``compute_sessions`` loads each input once per chunk of up to ``CHUNK`` sessions (the whole
range for a nightly run; a two-year backfill in a few reads, with bounded memory), then for
each session hands ``compute`` only the rows on or before that session and types the
result by the declaration (``framework.columns``). The same code path serves one session
and a backfill, so a backfilled row equals the row computed on its own session.

Inputs are asked of ``algotrade.data`` by table name (``data.feature_inputs.load_input``).
A group that reads another group's output gets it the same way: from the store
(the ``rollups`` task computes in dependency order and writes each session before the next
rollup runs), or from ``produced``, frames computed in this process and not written
(``compute_in_memory``: a read-only evaluation of a chain of rollups).

A market-entity group (ADR 0047) describes the whole market: its ``compute`` must return
exactly one row, ``instrument_id = market_id("US")`` (``MARKET``); anything else fails the
group loudly (``DataValidationError``), never a silently wrong or duplicated row.

``rollup_params`` reads every rollup's parameters from ``config/site/rollups.toml`` through
the one settings loader.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.config.site.settings import SiteDocuments, load_rollups
from algotrade.core.model.errors import DataValidationError
from algotrade.core.model.instruments import market_id
from algotrade.data import StoreReader
from algotrade.data.feature_inputs import Produced, load_input
from algotrade.features.framework.columns import conform
from algotrade.features.framework.declaration import FeatureGroup
from algotrade.features.framework.graph import dependency_order

CHUNK = 126  # sessions per input load (half a year: ~2 GB of daily bars at most)
MARKET = market_id("US")  # the one row of a market-entity group (ADR 0047)


@dataclass(frozen=True)
class SessionResult:
    """One session of one rollup: the typed rows, or why there are none (``no_input``)."""

    session: date
    frame: pd.DataFrame | None
    no_input: str | None = None


def rollup_params(configs: SiteDocuments | None, rollups: Sequence[FeatureGroup]) -> dict[str, Any]:
    """Each rollup's params (``rollups.toml`` over its defaults; defaults without a store)."""
    declared = {r.key: r.params for r in rollups}
    return load_rollups(configs, declared) if configs is not None else dict(declared)


def _check_point_in_time(
    rollup: FeatureGroup, table: str, frame: pd.DataFrame, session: date
) -> None:
    """Loaders return frames sorted by ``session_date`` (``day`` for a window input): the last
    row is the latest."""
    for column in ("session_date", "day"):
        if column in frame.columns and len(frame):
            latest = frame[column].iloc[-1]
            later = latest > pd.Timestamp(session) if column == "day" else latest > session
            if later:
                raise AssertionError(f"{rollup.key}: {table} rows from {latest} reached {session}")


def _check_entity_rows(rollup: FeatureGroup, frame: pd.DataFrame, session: date) -> None:
    """A market group returns exactly one row, the ``MARKET`` row."""
    if rollup.entity != "market":
        return
    ids = [str(i) for i in frame["instrument_id"]] if "instrument_id" in frame.columns else []
    if ids != [MARKET]:
        raise DataValidationError(
            rollup.table,
            [f"{rollup.key} on {session}: a market group returns one {MARKET} row, got {ids}"],
        )


def compute_sessions(
    reader: StoreReader,
    rollup: FeatureGroup,
    sessions: Sequence[date],
    params: Any = None,
    chunk: int = CHUNK,
    produced: Produced | None = None,
) -> Iterator[SessionResult]:
    """``rollup`` for each session in ``sessions`` (ascending), one result per session.
    ``produced``: rows of other rollups computed in this process (they win over stored)."""
    params = rollup.params if params is None else params
    for i in range(0, len(sessions), chunk):
        yield from _compute_chunk(reader, rollup, sessions[i : i + chunk], params, produced)


def _compute_chunk(
    reader: StoreReader,
    rollup: FeatureGroup,
    sessions: Sequence[date],
    params: Any,
    produced: Produced | None,
) -> Iterator[SessionResult]:
    lookbacks = {i.key: i.sessions_back(params) for i in rollup.inputs}
    loaded = {
        i.key: load_input(
            reader, i.table, sessions, lookbacks[i.key], produced, i.ids, i.symbols, i.windows
        )
        for i in rollup.inputs
    }
    for session in sessions:
        frames: dict[str, pd.DataFrame | None] = {}
        missing = []
        for spec in rollup.inputs:
            frame = loaded[spec.key].at(session, lookbacks[spec.key])
            if frame is None and spec.required:
                missing.append(spec.table)
            if frame is not None:
                _check_point_in_time(rollup, spec.key, frame, session)
            frames[spec.key] = frame
        if missing:
            yield SessionResult(session, None, f"no {', '.join(missing)} for {session}")
            continue
        if all(f is None for f in frames.values()):  # every input optional, none has rows
            yield SessionResult(session, None, f"no input for {session}")
            continue
        out = rollup.compute(frames, session, params)
        _check_entity_rows(rollup, out, session)
        yield SessionResult(session, conform(rollup.table, out, rollup.columns))


def compute_one(
    reader: StoreReader, rollup: FeatureGroup, session: date, params: Any = None
) -> SessionResult:
    """``rollup`` for a single session."""
    return next(compute_sessions(reader, rollup, [session], params))


def compute_in_memory(
    reader: StoreReader,
    rollups: Sequence[FeatureGroup],
    sessions: Sequence[date],
    params: Mapping[str, Any] | None = None,
) -> dict[str, list[SessionResult]]:
    """Every rollup in ``rollups`` for ``sessions``, in dependency order, WITHOUT writing:
    each rollup reads the frames the earlier ones produced here (stored rows otherwise).
    Holds every result in memory: for evaluation and tests, not backfills."""
    produced: dict[str, dict[date, pd.DataFrame | None]] = {}
    out: dict[str, list[SessionResult]] = {}
    for rollup in dependency_order(rollups, stored_ok=True):
        p = (params or {}).get(rollup.key)
        results = list(compute_sessions(reader, rollup, sessions, p, produced=produced))
        produced[rollup.table] = {r.session: r.frame for r in results}
        out[rollup.key] = results
    return out


def by_key(rollups: Mapping[str, FeatureGroup], only: Sequence[str] | None) -> list[FeatureGroup]:
    """The rollups named in ``only`` (keys ``<name>@v<N>``; all when empty), in registry order
    (dependency order: ``features.site``)."""
    if not only:
        return list(rollups.values())
    unknown = sorted(set(only) - set(rollups))
    if unknown:
        raise KeyError(f"unknown rollups {unknown}; known: {sorted(rollups)}")
    return [r for k, r in rollups.items() if k in only]
