"""``ibkr_iv_history@v1``: how IBKR's IV30 moved over the last 5 and 21 sessions.

Input: ``ibkr_iv@v1`` for the session and the 21 sessions before it (IBKR's IV30 history
reaches back about 502 sessions, so the changes exist long before the chain-derived ones of
``cp_iv_history@v1``). One row per instrument with an ``ibkr_iv@v1`` row on the session.

    ibkr_iv_chg_5d    ``iv30_ibkr`` now minus 5 exchange sessions ago
    ibkr_iv_chg_21d   ``iv30_ibkr`` now minus 21 exchange sessions ago

A session without an IBKR IV, at either end, is a gap and the change is null, never filled.
IBKR's IV30 blends calls and puts, so this tests the overall IV-change effect, not the
call-minus-put split of ``cp_iv_history@v1``. Derived from IBKR market data:
``licence = "personal"`` (ADR 0028); the group is ``optional`` like ``ibkr_iv@v1`` (ADR 0055).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence
from algotrade.features.rollups.options.iv_history import window_matrix

NAME = "ibkr_iv_history"
VERSION = 1
IBKR_IV = "rollups/instrument/ibkr_iv@v1"

_SHORT, _LONG = 5, 21
_P: Licence = "personal"


def _change(days: int) -> Feature:
    return Feature(
        f"ibkr_iv_chg_{days}d", "float32", "decimal",
        f"IBKR's 30-day implied vol now minus {days} sessions ago (decimal vol, 0.03 is three "
        "vol points); IBKR's IV30 blends calls and puts",
        f"IBKR had no IV on the session or on the session {days} sessions earlier (a gap is not "
        "filled)",
        "window", valid_range=(-5, 5), inputs=("ibkr_iv.iv30_ibkr@v1",), licence=_P,
    )  # fmt: skip


FEATURES = (_change(_SHORT), _change(_LONG))
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class IbkrIvHistoryParams:
    short: int = _SHORT  # sessions back for ibkr_iv_chg_5d
    long: int = _LONG  # sessions back for ibkr_iv_chg_21d (the lookback)

    def __post_init__(self) -> None:
        if (self.short, self.long) != (_SHORT, _LONG):
            raise ValueError("the column names carry 5 and 21: another window is a new version")


def compute(inputs: Inputs, session: date, p: IbkrIvHistoryParams) -> pd.DataFrame:
    rows = inputs[IBKR_IV]
    assert rows is not None  # required input
    ids, matrix = window_matrix(rows, "iv30_ibkr", session, p.long + 1)
    short: np.ndarray = matrix[-1] - matrix[-1 - p.short]
    long: np.ndarray = matrix[-1] - matrix[0]
    return pd.DataFrame({"instrument_id": ids, "ibkr_iv_chg_5d": short, "ibkr_iv_chg_21d": long})


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Changes of IBKR's IV30 over 5 and 21 sessions (personal-use licence)",
    (Input(IBKR_IV, lookback=lambda p: p.long),),
    FEATURES,
    compute,
    IbkrIvHistoryParams(),
    applies_to="optionable",
    optional=True,
)
