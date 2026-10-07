"""``flow_history@v1``: today's option volume against the last 20 sessions of ``chain_flow@v1``
(``docs/data/positioning.md`` OP2, ADR 0031).

Input: ``chain_flow@v1`` for the session and the ``window - 1`` sessions before it. One row per
instrument with a ``chain_flow@v1`` row on the session. A session counts when its row has
volume (``flow_status`` OK): a NO_CHAIN row carries none. Windows are exchange sessions
(``core.time.calendar``); a session without a row is a gap, counted out of
``flow_history_days``, not filled.

    option_volume_rel_20d  today's call + put volume / the mean total volume of the window's
                           EARLIER sessions with a row; null without a row today, with fewer
                           than ``min_sessions`` sessions with a row (today included), or when
                           that mean is 0
    pc_volume_ratio_20d    put volume / call volume summed over the window's sessions with a
                           row, today included; null without a row today, with fewer than
                           ``min_sessions`` sessions, or with no call volume
    flow_history_days      sessions of the window with a row, today included

Chains are stored nightly from 2026-10-02 only (there is nothing to backfill), so a name reads
null until it has ``min_sessions`` sessions of chain flow. ``window`` and ``min_sessions`` are
in ``rollups.toml ["flow_history@v1"]``; the column names carry 20, so a different window is a
new version.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "flow_history"
VERSION = 1
CHAIN_FLOW = "rollups/instrument/chain_flow@v1"

_VOLUME = ("chain_flow.call_volume@v1", "chain_flow.put_volume@v1")
_YOUNG = (
    "fewer than 10 of the last 20 sessions have chain flow (chains are stored nightly from "
    "2026-10-02 only, so most names read null until mid-October 2026), or there is no chain "
    "flow row with volume today"
)

FEATURES = (
    Feature(
        "option_volume_rel_20d", "float32", "ratio",
        "Today's call + put volume over the mean total option volume of the earlier sessions "
        "among the last 20 that have chain flow (2 is twice the usual volume)",
        f"{_YOUNG}; or that mean is 0", "window", valid_range=(0, None), inputs=_VOLUME,
    ),
    Feature(
        "pc_volume_ratio_20d", "float32", "ratio",
        "Put volume over call volume summed across the last 20 sessions that have chain flow, "
        "today included (above 1 is put-heavy)",
        f"{_YOUNG}; or no call volume in the window", "window", valid_range=(0, None),
        inputs=_VOLUME,
    ),
    Feature(
        "flow_history_days", "int", "sessions",
        "Sessions of the last 20 with chain flow volume, today included (gaps are not filled)",
        "never", "window", valid_range=(0, 20), inputs=_VOLUME,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class FlowHistoryParams:
    window: int = 20  # sessions, today included
    min_sessions: int = 10  # sessions with chain flow before the ratios are shown

    def __post_init__(self) -> None:
        if not 2 <= self.min_sessions <= self.window:
            raise ValueError("need 2 <= min_sessions <= window")


def history(calls: np.ndarray, puts: np.ndarray, p: FlowHistoryParams) -> dict[str, np.ndarray]:
    """The columns from sessions x instruments matrices of call and put volume (NaN: no row)
    whose LAST row is the session."""
    present = ~np.isnan(calls) & ~np.isnan(puts)
    calls, puts = np.where(present, calls, 0.0), np.where(present, puts, 0.0)
    days = present.sum(axis=0)
    shown = present[-1] & (days >= p.min_sessions)
    earlier = days - present[-1]
    with np.errstate(all="ignore"):
        usual = (calls + puts)[:-1].sum(axis=0) / earlier
        rel = np.where(shown & (usual > 0), (calls + puts)[-1] / usual, np.nan)
        pc = np.where(shown & (calls.sum(axis=0) > 0), puts.sum(axis=0) / calls.sum(axis=0), np.nan)
    return {"option_volume_rel_20d": rel, "pc_volume_ratio_20d": pc, "flow_history_days": days}


def compute(inputs: Inputs, session: date, p: FlowHistoryParams) -> pd.DataFrame:
    rows = inputs[CHAIN_FLOW]
    assert rows is not None  # required input
    ids = sorted(rows.loc[rows["session_date"] == session, "instrument_id"].astype(str).unique())
    days = sessions_ending(session, p.window)
    stored = rows.assign(instrument_id=rows["instrument_id"].astype(str))

    def matrix(column: str) -> np.ndarray:
        return (
            stored.assign(v=stored[column].astype(float))
            .pivot_table(index="session_date", columns="instrument_id", values="v", dropna=False)
            .reindex(index=days, columns=ids)
            .to_numpy(dtype=float)
        )

    return pd.DataFrame(
        {"instrument_id": ids, **history(matrix("call_volume"), matrix("put_volume"), p)}
    )


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Option volume against the last 20 sessions of chain flow: relative volume and the "
    "20-session put / call volume ratio",
    (Input(CHAIN_FLOW, lookback=lambda p: p.window - 1),),
    FEATURES,
    compute,
    FlowHistoryParams(),
    applies_to="optionable",
)
