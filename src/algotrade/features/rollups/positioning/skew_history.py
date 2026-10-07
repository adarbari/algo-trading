"""``skew_history@v1``: skew rank and percentile over a year of ``skew@v1`` (``docs/data/
positioning.md`` OP3, ADR 0031): ``iv_history@v2``'s pattern on the 30-day ``skew``.

Input: ``skew@v1`` for the session and the ``window - 1`` sessions before it. One row per
instrument with a ``skew@v1`` row on the session. The windows, gaps and the rank maths are
``iv_history``'s (``window_matrix`` and ``history``):

    skew_rank_252d         (skew - min) / (max - min) over the window's skews, today included;
                           null when max == min
    skew_percentile_252d   share of the window's EARLIER skews strictly below today's
    history_days           sessions of the window with a skew (today included)
    skew_rank_status       UNKNOWN (history_days < min_provisional; rank and percentile null),
                           PROVISIONAL (< window), FULL

Chains are stored nightly from 2026-10-02 only and there is no earlier source, so the rank is
UNKNOWN for every name until 60 sessions with a skew exist (about the end of 2026) and FULL
around October 2027. A session without a skew (no chain, or no 25-delta wing) is a gap, not
filled. ``window`` and ``min_provisional`` are in ``rollups.toml ["skew_history@v1"]``; the
column names carry 252, so a different full window is a new version.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.options.iv_history import IvHistoryParams, history, window_matrix

NAME = "skew_history"
VERSION = 1
SKEW = "rollups/instrument/skew@v1"

_SKEW = ("skew.skew@v1",)
_UNKNOWN = (
    "skew_rank_status is UNKNOWN (fewer than 60 sessions with a skew; chains are stored nightly "
    "from 2026-10-02 only, so every name reads null until about the end of 2026), or there is "
    "no skew today (skew_status says why)"
)

FEATURES = (
    Feature(
        "skew_rank_252d", "float32", "decimal",
        "Skew rank: (skew - min) / (max - min) over the last 252 sessions' skews, today "
        "included (1 is the most put-rich skew of the year, 0 the least)",
        f"{_UNKNOWN}; or every skew in the window is equal", valid_range=(0, 1), inputs=_SKEW,
    ),
    Feature(
        "skew_percentile_252d", "float32", "decimal",
        "Skew percentile: the share of the window's earlier skews strictly below today's",
        f"{_UNKNOWN}; or no earlier skew", valid_range=(0, 1), inputs=_SKEW,
    ),
    Feature(
        "history_days", "int", "sessions",
        "Sessions of the 252-session window with a skew, today included (gaps are not filled)",
        "never", valid_range=(0, 252), inputs=_SKEW,
    ),
    Feature(
        "skew_rank_status", "str", "category",
        "UNKNOWN below 60 sessions with a skew (no rank), PROVISIONAL below 252, FULL from 252",
        "never", "label", categories=("UNKNOWN", "PROVISIONAL", "FULL"), inputs=_SKEW,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class SkewHistoryParams:
    window: int = 252  # sessions for FULL (today included)
    min_provisional: int = 60  # sessions with a skew before the rank is shown (PROVISIONAL)

    def __post_init__(self) -> None:
        self.rank_rules()  # the same checks as iv_history@v2's

    def rank_rules(self) -> IvHistoryParams:
        """The ``iv_history@v2`` parameters ``history`` reads."""
        return IvHistoryParams(window=self.window, min_provisional=self.min_provisional)


def compute(inputs: Inputs, session: date, p: SkewHistoryParams) -> pd.DataFrame:
    rows = inputs[SKEW]
    assert rows is not None  # required input
    ids, matrix = window_matrix(rows, "skew", session, p.window)
    out = history(matrix, p.rank_rules())
    return pd.DataFrame(
        {
            "instrument_id": ids,
            "skew_rank_252d": out["iv_rank_252d"],
            "skew_percentile_252d": out["iv_percentile_252d"],
            "history_days": out["history_days"],
            "skew_rank_status": out["rank_status"],
        }
    )


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Skew rank and percentile over 252 sessions (provisional after 60)",
    (Input(SKEW, lookback=lambda p: p.window - 1),),
    FEATURES,
    compute,
    SkewHistoryParams(),
    applies_to="optionable",
)
