"""``index_changes@v1``: the latest S&P 500 membership change of an instrument and how long ago
(the field the ``on_event:index_change`` schedule reads, ADR 0050, ADR 0053 amendment, EB H0).

Input: ``events/index_change`` by EVENT date (a fact of record: the session the change was
first stored, which is when it was known, so ``known_from <= session`` holds by
construction), up to the session and no further back than ``LOOKBACK`` sessions.

    last_index_change_date      the latest change's date (the session it was first stored)
    sessions_since_index_change exchange sessions from that date up to the session (0: today)
    last_index_change           sp500_added or sp500_removed

One row per instrument with a change in the window; none: no row (UNKNOWN, never "no change").
Additions and deletions are kept together here; a later group may split them (EB H4).
"""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "index_changes"
VERSION = 1
EVENTS = "events/index_change"
LOOKBACK = 60  # sessions of changes loaded: the schedule needs the last few weeks
ADDED, REMOVED = "sp500_added", "sp500_removed"

_NONE = f"no S&P 500 membership change in the last {LOOKBACK} sessions"
_INPUTS = (f"{EVENTS}.ts", f"{EVENTS}.change")

FEATURES = (
    Feature(
        "last_index_change_date", "date", "date",
        "The date of the latest S&P 500 membership change (the session it was first stored)",
        _NONE, inputs=_INPUTS,
    ),
    Feature(
        "sessions_since_index_change", "int", "sessions",
        "Exchange sessions from the latest S&P 500 membership change up to the session "
        "(0: the session is that day)",
        _NONE, valid_range=(0, None), inputs=_INPUTS,
    ),
    Feature(
        "last_index_change", "str", "category",
        "The latest change: sp500_added (joined the index) or sp500_removed (left it)",
        _NONE, "label", categories=(ADDED, REMOVED), inputs=_INPUTS,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    columns = ["instrument_id", *COLUMNS]
    stored = inputs.get(EVENTS)
    if stored is None or stored.empty:
        return pd.DataFrame(columns=columns)
    rows = stored[stored["event_date"] <= session]
    rows = rows[rows["change"].isin([ADDED, REMOVED])]
    rows = rows.sort_values(["instrument_id", "event_date"], kind="stable")
    last = rows.drop_duplicates("instrument_id", keep="last")
    frame = pd.DataFrame(
        {
            "instrument_id": last["instrument_id"].astype(str).to_numpy(),
            "last_index_change_date": last["event_date"].to_numpy(),
            "sessions_since_index_change": pd.array(
                [sessions_to(d, session) for d in last["event_date"]], dtype="Int64"
            ),
            "last_index_change": last["change"].astype(str).to_numpy(),
        }
    )
    return frame[columns].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The latest S&P 500 membership change of an instrument and the sessions since it",
    (Input(EVENTS, lookback=LOOKBACK, required=False),),
    FEATURES,
    compute,
)
