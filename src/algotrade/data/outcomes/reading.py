"""Read forward outcomes (``outcomes/instrument/forward_returns@v2``, written by the ingestion
``outcomes`` task) for the start sessions a harness evaluates: one row per (instrument, start
session S, horizon, benchmark). A window not closed, or not computed, has no row: the caller
excludes it, never counts it a miss; an ``UNMEASURED`` row (a flagged bar in the window, ADR 0061;
``outcome_reason``) has no returns and is excluded the same way. ``as_of`` keeps only rows
known by then (row by row, not only by run)."""

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import FORWARD_RETURNS

OUTCOME_FIELDS = (
    "fwd_return", "fwd_excess_return", "fwd_max_return", "fwd_max_drawdown", "fwd_realised_vol",
    "outcome_status", "outcome_reason",
)  # fmt: skip
_KEY = ("instrument_id", "session_date", "horizon_sessions", "benchmark", "window_end")


def stored_sessions(reader: StoreReader) -> list[date]:
    """The start sessions with a stored outcome partition, ascending (empty: none stored)."""
    return list(reader.dates(FORWARD_RETURNS))


def missing_outcomes(sessions: Sequence[date]) -> MissingDataError:
    """The error of start ``sessions`` none of which has a stored outcome."""
    wanted = sorted(set(sessions))
    hint = f"run `algotrade-ingest run outcomes --from ... --to ...` past {wanted[-1]}"
    return MissingDataError(FORWARD_RETURNS, f"no outcomes for {wanted[0]}..{wanted[-1]}", hint)


def read_stored(
    reader: StoreReader,
    sessions: Sequence[date],
    as_of: datetime | None = None,
    instruments: Sequence[str] | None = None,
) -> pd.DataFrame | None:
    """The stored rows of the start ``sessions``' partitions, every horizon and benchmark (None:
    none stored). With ``as_of`` only the wanted partitions are read (a harness chunk's entry
    sessions are far from contiguous); without it the range read keeps the history copy's path
    (ADR 0060)."""
    wanted = sorted(set(sessions))
    if as_of is None:
        return reader.table_range(FORWARD_RETURNS, wanted[0], wanted[-1], as_of, instruments)
    stored = set(reader.dates(FORWARD_RETURNS))
    parts = [reader.table(FORWARD_RETURNS, d, as_of) for d in wanted if d in stored]
    parts = [p for p in parts if p is not None and not p.empty]
    if not parts:
        # the span semantics of the range read: a partition visible in it, wanted or not, means
        # stored but no rows; none visible (all after ``as_of``, or none stored) is "nothing"
        between = sorted(d for d in stored if wanted[0] <= d <= wanted[-1] and d not in set(wanted))
        for d in between:
            frame = reader.table(FORWARD_RETURNS, d, as_of)
            if frame is not None and not frame.empty:
                return pd.DataFrame(columns=[*_KEY, *OUTCOME_FIELDS, "knowledge_ts"])
        return None
    frame = pd.concat(parts, ignore_index=True)
    if instruments is not None:
        frame = frame[frame["instrument_id"].isin(set(instruments))].reset_index(drop=True)
    return frame


def select_outcomes(
    frame: pd.DataFrame,
    horizon: int,
    sessions: Sequence[date],
    benchmark: str = "SPY",
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """The ``horizon`` and ``benchmark`` rows of ``frame`` (``read_stored``) for the start
    ``sessions``, as ``read_outcomes`` returns them."""
    if "outcome_reason" not in frame.columns:  # a nullable column no row of the partitions set
        frame = frame.assign(outcome_reason=None)
    starts = pd.to_datetime(frame["session_date"]).dt.date
    keep = starts.isin(set(sessions)) & (frame["horizon_sessions"] == horizon)
    keep &= frame["benchmark"] == benchmark
    if as_of is not None:
        keep &= pd.to_datetime(frame["knowledge_ts"], utc=True) <= pd.Timestamp(as_of)
    out = frame.loc[keep, [*_KEY, *OUTCOME_FIELDS, "knowledge_ts"]]
    return out.sort_values(["session_date", "instrument_id"], kind="stable").reset_index(drop=True)


def read_outcomes(
    reader: StoreReader,
    horizon: int,
    sessions: Sequence[date],
    benchmark: str = "SPY",
    instruments: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """The ``horizon``-session outcomes over ``benchmark`` of the start ``sessions``: columns
    ``_KEY`` + ``OUTCOME_FIELDS`` + ``knowledge_ts``, sorted by (session_date, instrument_id).

    Raises ``MissingDataError`` when no outcome is stored for any of the sessions (the
    ``outcomes`` task has not run for them)."""
    wanted = sorted(set(sessions))
    if not wanted:
        return pd.DataFrame(columns=[*_KEY, *OUTCOME_FIELDS, "knowledge_ts"])
    frame = read_stored(reader, wanted, as_of, instruments)
    if frame is None:
        raise missing_outcomes(wanted)
    return select_outcomes(frame, horizon, wanted, benchmark, as_of)
