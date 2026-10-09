"""``iv_history@v2``: IV rank and percentile over a year of ``iv30@v1``.

Inputs: ``iv30@v1`` for the session and the ``window - 1`` sessions before it (our own IV30 by
default; ``source = "cboe"`` uses the feed's). One row per instrument with an ``iv30@v1`` row
on the session.

    iv30                 the session's IV30 (from ``source``)
    iv_rank_252d         (iv30 - min) / (max - min) over the window's IVs, today included;
                         null when max == min
    iv_percentile_252d   share of the window's EARLIER IVs strictly below today's
    history_days         sessions of the window with an IV (today included)
    rank_status          UNKNOWN (history_days < min_provisional; rank and percentile null),
                         PROVISIONAL (< window), FULL

Windows are exchange sessions (``core.time.calendar``); a session without an IV is a gap,
counted out of ``history_days``, not filled. ``window`` and ``min_provisional`` are in
``rollups.toml ["iv_history@v2"]`` (owner decision: provisional after 60 sessions, full after
252); the column names carry 252, so a different full window is a new version.

v2 (ADR 0023 step 3) stores the floats as 32-bit and drops ``iv_hv_spread`` / ``iv_hv_ratio``
(and with them the ``price_stats`` input): they are expression features
(``config/site/features/options/volatility.toml``), computed on read.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.options.iv30 import ILLIQUID_STATUSES

NAME = "iv_history"
VERSION = 2
IV30 = "rollups/instrument/iv30@v1"
SOURCES = {"ours": "iv30", "cboe": "iv30_cboe"}

_IV = "iv30.iv30@v1"
_THIN = tuple(sorted(ILLIQUID_STATUSES))
_STATUS = "iv30.iv30_status@v1"  # why iv30@v1 has no IV (ADR 0042: a thin chain reads ILLIQUID)
_UNKNOWN = "rank_status is UNKNOWN (fewer than 60 sessions with an IV), or there is no IV today"

FEATURES = (
    Feature(
        "iv30", "float32", "decimal",
        "The session's IV30 from iv30@v1 (ours; the feed's with source = cboe)",
        "iv30@v1 has no IV for the session (its iv30_status says why)", "expression",
        valid_range=(0, 5), inputs=(_IV, "iv30.iv30_cboe@v1"),
        null_status=_STATUS, illiquid_statuses=_THIN,
    ),
    Feature(
        "iv_rank_252d", "float32", "decimal",
        "IV rank: (iv30 - min) / (max - min) over the last 252 sessions' IVs, today included",
        f"{_UNKNOWN}; or every IV in the window is equal", valid_range=(0, 1), inputs=(_IV,),
        null_status=_STATUS,
        illiquid_statuses=_THIN,
    ),
    Feature(
        "iv_percentile_252d", "float32", "decimal",
        "IV percentile: the share of the window's earlier IVs strictly below today's",
        f"{_UNKNOWN}; or no earlier IV", valid_range=(0, 1), inputs=(_IV,),
        null_status=_STATUS, illiquid_statuses=_THIN,
    ),
    Feature(
        "history_days", "int", "sessions",
        "Sessions of the 252-session window with an IV, today included (gaps are not filled)",
        "never", valid_range=(0, None), inputs=(_IV,),
    ),
    Feature(
        "rank_status", "str", "category",
        "UNKNOWN below 60 sessions with an IV (no rank), PROVISIONAL below 252, FULL from 252",
        "never", "label", categories=("UNKNOWN", "PROVISIONAL", "FULL"), inputs=(_IV,),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class IvHistoryParams:
    window: int = 252  # sessions for FULL (today included)
    min_provisional: int = 60  # sessions with an IV before the rank is shown (PROVISIONAL)
    source: str = "ours"  # "ours" (iv30) or "cboe" (iv30_cboe)

    def __post_init__(self) -> None:
        if not 2 <= self.min_provisional <= self.window:
            raise ValueError("need 2 <= min_provisional <= window")
        if self.source not in SOURCES:
            raise ValueError(f"source must be one of {sorted(SOURCES)}, got {self.source!r}")


def history(ivs: np.ndarray, p: IvHistoryParams) -> dict[str, np.ndarray]:
    """Rank columns from a sessions x instruments matrix whose LAST row is the session."""
    today = ivs[-1]
    present = ~np.isnan(ivs)
    days = present.sum(axis=0)
    with np.errstate(all="ignore"):
        lo, hi = (
            np.nanmin(ivs, axis=0, initial=np.inf, where=present),
            np.nanmax(ivs, axis=0, initial=-np.inf, where=present),
        )
        rank = np.where(hi > lo, (today - lo) / (hi - lo), np.nan)
        past = ivs[:-1]
        earlier = (~np.isnan(past)).sum(axis=0)
        below = (past < today[None, :]).sum(axis=0)
        percentile = np.where(earlier > 0, below / earlier, np.nan)
    status = np.where(
        days < p.min_provisional, "UNKNOWN", np.where(days < p.window, "PROVISIONAL", "FULL")
    )
    shown = (status != "UNKNOWN") & ~np.isnan(today)
    return {
        "iv30": today,
        "iv_rank_252d": np.where(shown, rank, np.nan),
        "iv_percentile_252d": np.where(shown, percentile, np.nan),
        "history_days": days,
        "rank_status": status,
    }


def window_matrix(
    rows: pd.DataFrame, column: str, session: date, window: int
) -> tuple[list[str], np.ndarray]:
    """The instruments with a row on ``session`` (sorted ids) and their ``column`` as a
    sessions x instruments matrix over the ``window`` exchange sessions ending on it (NaN: no
    row or no value; the LAST row is the session). Shared by the rank groups over a stored
    group (``iv_history@v2``, ``skew_history@v1``)."""
    ids = sorted(rows.loc[rows["session_date"] == session, "instrument_id"].astype(str).unique())
    matrix = (
        rows.assign(instrument_id=rows["instrument_id"].astype(str), v=rows[column].astype(float))
        .pivot_table(index="session_date", columns="instrument_id", values="v", dropna=False)
        .reindex(index=sessions_ending(session, window), columns=ids)
        .to_numpy(dtype=float)
    )
    return ids, matrix


def compute(inputs: Inputs, session: date, p: IvHistoryParams) -> pd.DataFrame:
    rows = inputs[IV30]
    assert rows is not None  # required input
    ids, matrix = window_matrix(rows, SOURCES[p.source], session, p.window)
    return pd.DataFrame({"instrument_id": ids, **history(matrix, p)})


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "IV30 rank and percentile over 252 sessions (provisional after 60)",
    (Input(IV30, lookback=lambda p: p.window - 1),),
    FEATURES,
    compute,
    IvHistoryParams(),
    applies_to="optionable",
)
