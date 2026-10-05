"""``nearest_expiry@v1``: the nearest listed option expiry on or after the session, from the
session's own stored chain, and how far away it is.

Input: the session's ``chains/option_quotes`` (required). One row per underlying with a chain.

    expiry_date         the earliest listed expiry on or after the session (an expiry ON the
                        session counts: 0-DTE, it trades until the close)
    dte                 calendar days from the session to it (0: expires today)
    sessions_to_expiry  exchange sessions after the session up to it (0: expires today;
                        ``core.time.calendar.sessions_to``, as ``earnings.days_to_earnings``)

This is the stored form of what Ideas computed per request (``ranking.top_ideas`` over
``data.chains.chain_expiries``): the same table, the same session partition, the same rule
(nearest ``e >= session``, DTE ``(e - session).days``); there is no intended difference.
Unlike ``option_liquidity.target_expiry`` it is the nearest expiry, not the target one.
"""

from datetime import date
from functools import cache

import pandas as pd

from algotrade.core.time.calendar import sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.options.iv30 import OPTIONS

NAME = "nearest_expiry"
VERSION = 1

_EXPIRY = (f"{OPTIONS}.expiry",)
_NONE = "every listed expiry in the session's stored chain is before the session"

FEATURES = (
    Feature(
        "expiry_date", "date", "date",
        "The nearest listed option expiry on or after the session (0-DTE included), from the "
        "session's stored chain",
        _NONE, "chain", inputs=_EXPIRY,
    ),
    Feature(
        "dte", "int", "days",
        "Calendar days from the session to the nearest expiry (0: expires on the session)",
        _NONE, "chain", valid_range=(0, None), inputs=_EXPIRY,
    ),
    Feature(
        "sessions_to_expiry", "int", "sessions",
        "Exchange sessions after the session up to the nearest expiry (0: expires on the "
        "session)",
        _NONE, "chain", valid_range=(0, None), inputs=_EXPIRY,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@cache
def _sessions_to(start: date, end: date) -> int:
    return sessions_to(start, end)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    options = inputs[OPTIONS]
    assert options is not None  # required input
    found = pd.DataFrame(
        {
            "instrument_id": options["underlying_id"].astype(str).to_numpy(),
            "expiry": pd.to_datetime(options["expiry"]).dt.date.to_numpy(),
        }
    )
    ahead = found[found["expiry"] >= session]
    nearest = ahead.groupby("instrument_id")["expiry"].min()
    rows = []
    for iid in sorted(set(found["instrument_id"])):
        expiry = nearest.get(iid)
        rows.append(
            {
                "instrument_id": iid,
                "expiry_date": expiry,
                "dte": None if expiry is None else (expiry - session).days,
                "sessions_to_expiry": None if expiry is None else _sessions_to(session, expiry),
            }
        )
    return pd.DataFrame(rows, columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The nearest listed option expiry on or after the session, its DTE and sessions to it",
    (Input(OPTIONS),),
    FEATURES,
    compute,
)
