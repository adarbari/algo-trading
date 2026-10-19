"""``reverse_splits@v1``: the latest reverse split of an instrument and how long ago (the fields
the ``on_event:reverse_split`` schedule reads, ADR 0075, ADR 0050).

Input: ``events/split`` by EVENT date (the ex-date, a fact of record: the table has no
``known_from``), only rows with ``ts`` on or before the session (a declared future ex-date is
never read) and no further back than ``LOOKBACK`` sessions.

**Ratio convention** (``data.prices``): the stored ``ratio`` is new shares per old share, the
number an earlier bar is divided by. A 4-for-1 forward split is stored as 4, a 1-for-10 reverse
split as 0.1; a reverse split is a ratio below 1 (a ratio of 1 or above, zero or null is no
reverse split).

    last_reverse_split_date      the latest reverse split's ex-date (the event's anchor)
    sessions_since_reverse_split exchange sessions from that ex-date up to the session (0: today)
    reverse_split_ratio          that split's stored ratio, below 1 (0.1: one new share per ten)
    reverse_splits_1y            reverse splits with an ex-date in the window

One row per instrument with a reverse split in the window; none: no row (UNKNOWN, never "no
split"). Funds reverse-split too; the edge's universe excludes them.
"""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "reverse_splits"
VERSION = 1
EVENTS = "events/split"
LOOKBACK = 252  # sessions of splits loaded: a year
_NONE = f"no reverse split with an ex-date in the last {LOOKBACK} sessions"
_INPUTS = (f"{EVENTS}.ts", f"{EVENTS}.ratio")

FEATURES = (
    Feature(
        "last_reverse_split_date", "date", "date",
        "The ex-date of the latest reverse split (the event's anchor)", _NONE, inputs=_INPUTS,
    ),
    Feature(
        "sessions_since_reverse_split", "int", "sessions",
        "Exchange sessions from the latest reverse split's ex-date up to the session "
        "(0: the session is the ex-date)",
        _NONE, valid_range=(0, None), inputs=_INPUTS,
    ),
    Feature(
        "reverse_split_ratio", "float", "ratio",
        "New shares per old share of the latest reverse split (0.1: one new share for ten old, "
        "a 1-for-10)",
        _NONE, valid_range=(0, 1), inputs=_INPUTS,
    ),
    Feature(
        "reverse_splits_1y", "int", "count",
        f"Reverse splits with an ex-date in the last {LOOKBACK} sessions",
        _NONE, valid_range=(1, None), inputs=_INPUTS,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    columns = ["instrument_id", *COLUMNS]
    stored = inputs.get(EVENTS)
    if stored is None or stored.empty:
        return pd.DataFrame(columns=columns)
    ratio = pd.to_numeric(stored["ratio"], errors="coerce")
    rows = stored[(stored["event_date"] <= session) & (ratio > 0) & (ratio < 1)]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    rows = rows.assign(instrument_id=rows["instrument_id"].astype(str), ratio=ratio[rows.index])
    rows = rows.sort_values(["instrument_id", "event_date"], kind="stable")
    latest = rows.drop_duplicates("instrument_id", keep="last").set_index("instrument_id")
    count = rows.groupby("instrument_id").size()
    ids = list(latest.index)
    return pd.DataFrame(
        {
            "instrument_id": ids,
            "last_reverse_split_date": list(latest["event_date"]),
            "sessions_since_reverse_split": pd.array(
                [sessions_to(d, session) for d in latest["event_date"]], dtype="Int64"
            ),
            "reverse_split_ratio": latest["ratio"].astype(float).to_numpy(),
            "reverse_splits_1y": pd.array(count[ids].to_numpy(), dtype="Int64"),
        }
    )[columns].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The latest reverse split of an instrument, its ratio and the sessions since its ex-date",
    (Input(EVENTS, lookback=LOOKBACK, required=False),),
    FEATURES,
    compute,
)
