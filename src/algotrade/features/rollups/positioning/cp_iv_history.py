"""``cp_iv_history@v1``: how the call-put IV signals and IV30 moved over the last 5 and 21
sessions (edge ideas c01 and c03, ``docs/edge-ideas/options-volatility.md``).

Inputs: ``cp_iv@v1`` and ``iv30@v1`` for the session and the 21 sessions before it. One row per
instrument with a ``cp_iv@v1`` row on the session. A change is the session's value minus the
value ``n`` exchange sessions earlier (the same ``window_matrix`` rule as ``iv_history``); a
session without a value, at either end, is a gap and the change is null, never filled:

    cp_iv_spread_chg_5d / _21d   change of ``cp_iv_spread``
    atm_call_iv_chg_5d / _21d    change of ``atm_call_iv`` (An-Ang-Bali-Cakici's call-IV change)
    atm_put_iv_chg_5d / _21d     change of ``atm_put_iv`` (their put-IV change)
    iv30_chg_5d                  change of our ``iv30`` (ATM, both sides)

Chains are stored nightly from 2026-10-02 only and there is no earlier source, so a 5-session
change exists from 2026-10-09 and a 21-session one from the end of October 2026.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.options.iv_history import window_matrix

NAME = "cp_iv_history"
VERSION = 1
CP_IV = "rollups/instrument/cp_iv@v1"
IV30 = "rollups/instrument/iv30@v1"

_SHORT, _LONG = 5, 21
_FROM = (
    "chains are stored nightly from 2026-10-02 only, so a 5-session change exists from "
    "2026-10-09 and a 21-session one from the end of October 2026"
)


def _change(name: str, source: str, column: str, days: int, what: str, bounds: float) -> Feature:
    return Feature(
        name,
        "float32",
        "decimal",
        f"{what} now minus {days} sessions ago (decimal vol, 0.03 is three vol points); "
        f"chain-derived, so {_FROM}",
        f"no {what} on the session or on the session {days} sessions earlier (a gap is not "
        f"filled); {_FROM}",
        "window",
        valid_range=(-bounds, bounds),
        inputs=(f"{source}.{column}@v1",),
    )


FEATURES = (
    _change("cp_iv_spread_chg_5d", "cp_iv", "cp_iv_spread", _SHORT, "the call-put IV spread", 4),
    _change("cp_iv_spread_chg_21d", "cp_iv", "cp_iv_spread", _LONG, "the call-put IV spread", 4),
    _change("atm_call_iv_chg_5d", "cp_iv", "atm_call_iv", _SHORT, "the ATM call IV", 5),
    _change("atm_call_iv_chg_21d", "cp_iv", "atm_call_iv", _LONG, "the ATM call IV", 5),
    _change("atm_put_iv_chg_5d", "cp_iv", "atm_put_iv", _SHORT, "the ATM put IV", 5),
    _change("atm_put_iv_chg_21d", "cp_iv", "atm_put_iv", _LONG, "the ATM put IV", 5),
    _change("iv30_chg_5d", "iv30", "iv30", _SHORT, "our 30-day ATM IV", 5),
)
COLUMNS = column_types(FEATURES)
_SOURCES = (
    ("cp_iv_spread", "cp_iv_spread"),
    ("atm_call_iv", "atm_call_iv"),
    ("atm_put_iv", "atm_put_iv"),
)


@dataclass(frozen=True)
class CpIvHistoryParams:
    short: int = _SHORT  # sessions back for the *_chg_5d columns
    long: int = _LONG  # sessions back for the *_chg_21d columns (the lookback)

    def __post_init__(self) -> None:
        if (self.short, self.long) != (_SHORT, _LONG):
            raise ValueError("the column names carry 5 and 21: another window is a new version")


def _changes(rows: pd.DataFrame, column: str, ids: list[str], session: date, n: int) -> np.ndarray:
    """``column`` now minus ``n`` sessions ago for ``ids``; NaN with either end missing."""
    got, matrix = window_matrix(rows, column, session, n + 1)
    if got != ids:  # another table's sessions: align by id
        frame = pd.DataFrame(matrix, columns=got).reindex(columns=ids)
        matrix = frame.to_numpy(dtype=float)
    change: np.ndarray = matrix[-1] - matrix[0]
    return change


def compute(inputs: Inputs, session: date, p: CpIvHistoryParams) -> pd.DataFrame:
    cp, iv30 = inputs[CP_IV], inputs[IV30]
    assert cp is not None and iv30 is not None  # required inputs
    ids = sorted(cp.loc[cp["session_date"] == session, "instrument_id"].astype(str).unique())
    out: dict[str, object] = {"instrument_id": ids}
    for name, column in _SOURCES:
        for suffix, n in (("5d", p.short), ("21d", p.long)):
            out[f"{name}_chg_{suffix}"] = _changes(cp, column, ids, session, n)
    out["iv30_chg_5d"] = _changes(iv30, "iv30", ids, session, p.short)
    return pd.DataFrame(out)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Changes of the call-put IV spread, the ATM call and put IV (5 and 21 sessions) and IV30 "
    "(5 sessions)",
    (Input(CP_IV, lookback=lambda p: p.long), Input(IV30, lookback=lambda p: p.long)),
    FEATURES,
    compute,
    CpIvHistoryParams(),
    applies_to="optionable",
)
