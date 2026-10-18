"""``short_interest@v1``: each instrument's latest FINRA short interest known by the session (the
inputs of the edge ``short_squeeze_days_to_cover``, EB E6).

Input: ``events/short_interest`` by the session each report became public (``known_from``,
which ingestion sets from FINRA's publication schedule: the session after the 7th business day
after the settlement date, never the settlement date itself, the figure is two weeks old when it
is public), no further back than ``LOOKBACK`` sessions (two reporting periods of margin). The
latest report per instrument:

    short_position         shares sold short at the settlement date (FINRA, all markets)
    days_to_cover          FINRA's own: short_position over the average daily share volume of
                           that report's period
    short_interest_date    the settlement date the figures describe (a stale figure shows here)

An instrument with no report in the window has no row (UNKNOWN, never "no short interest").
The table is ``no_ml``: no learned scorer may read these columns (``tables.toml``).
"""

from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "short_interest"
VERSION = 1
EVENTS = "events/short_interest"
LOOKBACK = 30  # sessions of reports loaded: two semi-monthly reports plus the publication lag
_NONE = "no short-interest report became public in the last 30 sessions: never read as no shorts"
_STALE = "; the figure is the settlement date's, about two weeks before it became public"
FEATURES = (
    Feature(
        "short_position", "float", "shares",
        "Shares sold short at the latest settlement date public by the session (FINRA, all "
        "markets)", _NONE, valid_range=(0, None), inputs=(f"{EVENTS}.short_position",),
    ),
    Feature(
        "days_to_cover", "float", "sessions",
        "FINRA's days to cover: the short position over the average daily share volume of the "
        "report's period; 5 means five average sessions of volume to buy it all back",
        _NONE + "; or FINRA gives no average volume for the report",
        valid_range=(0, None), inputs=(f"{EVENTS}.days_to_cover",),
    ),
    Feature(
        "short_interest_date", "date", "date",
        "The settlement date of the latest short-interest report public by the session"
        + _STALE,
        _NONE, inputs=(f"{EVENTS}.ts",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    columns = ["instrument_id", *COLUMNS]
    stored = inputs.get(EVENTS)
    if stored is None or stored.empty:
        return pd.DataFrame(columns=columns)
    rows = stored[pd.to_datetime(stored["known_from"]) <= pd.Timestamp(session)]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    latest = rows.sort_values(["ts", "known_from"], kind="stable").drop_duplicates(
        "instrument_id", keep="last"
    )
    out = pd.DataFrame(
        {
            "instrument_id": latest["instrument_id"].astype(str).to_numpy(),
            "short_position": latest["short_position"].to_numpy(),
            "days_to_cover": latest["days_to_cover"].to_numpy(),
            "short_interest_date": pd.to_datetime(latest["ts"], utc=True).dt.date.to_numpy(),
        }
    )
    return out[columns].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The latest FINRA short interest public by the session: shares short, days to cover and its "
    "settlement date",
    (Input(EVENTS, lookback=LOOKBACK, required=False),),
    FEATURES,
    compute,
)
