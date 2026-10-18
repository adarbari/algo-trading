"""Read residual returns (``outcomes/instrument/residual_returns@v1``, written by the ingestion
``residual-returns`` task; ADR 0053 amendment, EB H11) for the start sessions a harness evaluates,
and attach them to the forward outcomes of one horizon. Quarantined with ``reading.py``: only the
edge harness imports it.

A forward row with no residual row is UNMEASURED with the reason ``NO_RESIDUAL_ROW`` (the task has
not run for its window): never a zero, never the excess return in its place. ``as_of`` keeps only
rows known by then (row by row)."""

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import RESIDUAL_RETURNS, UNMEASURED

RESIDUAL_FIELDS = ("fwd_residual_return", "residual_status", "residual_reason")
NO_RESIDUAL_ROW = "NO_RESIDUAL_ROW"
_STORED = (
    "instrument_id", "session_date", "horizon_sessions", "fwd_residual_return", "outcome_status",
    "outcome_reason", "knowledge_ts",
)  # fmt: skip


def read_residuals(
    reader: StoreReader, sessions: Sequence[date], as_of: datetime | None = None
) -> pd.DataFrame | None:
    """The stored residual rows of the start ``sessions``' partitions, every horizon (None: none
    stored). Only the wanted partitions are read."""
    wanted = sorted(set(sessions))
    if not wanted:
        return None
    stored = set(reader.dates(RESIDUAL_RETURNS))
    parts = [reader.table(RESIDUAL_RETURNS, d, as_of) for d in wanted if d in stored]
    parts = [p for p in parts if p is not None and not p.empty]
    if not parts:
        return None
    frame = pd.concat(parts, ignore_index=True)
    if "outcome_reason" not in frame.columns:
        frame = frame.assign(outcome_reason=None)
    return frame[list(_STORED)]


def attach_residuals(
    frame: pd.DataFrame, residuals: pd.DataFrame | None, horizon: int
) -> pd.DataFrame:
    """``frame`` (``select_outcomes`` of ``horizon``) plus ``RESIDUAL_FIELDS``: the stored
    residual return of each row's name and window, its status and reason. A row without a
    residual row is UNMEASURED, ``NO_RESIDUAL_ROW``; so is one whose residual row is."""
    out = frame.assign(
        fwd_residual_return=float("nan"),
        residual_status=UNMEASURED,
        residual_reason=NO_RESIDUAL_ROW,
    )
    if residuals is None or residuals.empty or frame.empty:
        return out
    mine = residuals[residuals["horizon_sessions"] == horizon]
    mine = mine.drop_duplicates(["instrument_id", "session_date"], keep="last")
    key = ["instrument_id", "session_date"]
    left = out.drop(columns=list(RESIDUAL_FIELDS)).assign(
        instrument_id=out["instrument_id"].astype(str),
        session_date=pd.to_datetime(out["session_date"]).dt.date,
    )
    right = mine[[*key, "fwd_residual_return", "outcome_status", "outcome_reason"]].assign(
        instrument_id=mine["instrument_id"].astype(str),
        session_date=pd.to_datetime(mine["session_date"]).dt.date,
    )
    right = right.rename(
        columns={"outcome_status": "residual_status", "outcome_reason": "residual_reason"}
    )
    merged = left.merge(right, on=key, how="left")
    absent = merged["residual_status"].isna()
    merged["residual_status"] = merged["residual_status"].where(~absent, UNMEASURED)
    merged["residual_reason"] = merged["residual_reason"].where(~absent, NO_RESIDUAL_ROW)
    merged["fwd_residual_return"] = pd.to_numeric(merged["fwd_residual_return"])
    merged.index = frame.index  # the merge keeps the left's order
    return merged
