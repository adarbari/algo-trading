"""``etf_launches@v1``: how long ago a specialised ETF launched (the fields the
``on_event:etf_launch[:<category>]`` schedule reads, ADR 0076, ADR 0050).

Input: ``instruments/etf_launches`` (``data.listings.etf_launches``): the Tiingo listing start of
each ETF whose ``etf_category`` is ``thematic`` or ``sector``, only launches on or before the
session (a later one is not known) and no further back than ``LOOKBACK`` sessions, five years,
the paper's months 1 to 60. The launch date is the listing's first day, not the fund's
inception (``launch_date_source``), and the category is the one resolved from the fund's name at
the latest universe build (a renamed fund carries today's category on its launch date; a fund
delisted before the first reference snapshot has none and no row).

    last_etf_launch_date      the launch (listing start) date, the event's anchor
    sessions_since_etf_launch exchange sessions from that date up to the session (0: today)
    etf_category              ``thematic`` or ``sector`` (the subtype the schedule filters on)
    etf_theme                 the theme group (thematic) or the sector (sector)
    launch_date_source        ``tiingo_listing``

One row per specialised ETF launched in the window; none: no row (UNKNOWN, never "not launched").
"""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "etf_launches"
VERSION = 1
LAUNCHES = "instruments/etf_launches"
LAUNCH_SOURCE = "tiingo_listing"  # kept equal to data.listings.etf_launches by a test
SPECIALISED = ("thematic", "sector")
LOOKBACK = 1300  # sessions of launches loaded: five years and a margin
_NONE = (
    f"not a specialised ETF (thematic or sector) launched in the last {LOOKBACK} sessions, or "
    "the latest universe build gave it no category or no listing start is stored"
)
_INPUTS = (f"{LAUNCHES}.event_date", f"{LAUNCHES}.etf_category", f"{LAUNCHES}.etf_theme")

FEATURES = (
    Feature(
        "last_etf_launch_date", "date", "date",
        "The launch date of the ETF: its first listing day in the Tiingo listing history "
        "(the event's anchor)", _NONE, inputs=_INPUTS,
    ),
    Feature(
        "sessions_since_etf_launch", "int", "sessions",
        "Exchange sessions from the ETF's launch up to the session (0: the session is the "
        "launch day)", _NONE, valid_range=(0, None), inputs=_INPUTS,
    ),
    Feature(
        "etf_category", "str", "category",
        "thematic (a story tying several industries) or sector (one industry)",
        _NONE, "label", categories=SPECIALISED, inputs=_INPUTS,
    ),
    Feature(
        "etf_theme", "str", "category",
        "The theme group of a thematic ETF, or the sector of a sector ETF", _NONE, "label",
        inputs=_INPUTS,
    ),
    Feature(
        "launch_date_source", "str", "category",
        "Where the launch date comes from: tiingo_listing, the first listing of the instrument "
        "(not the fund's inception)", _NONE, "label", categories=(LAUNCH_SOURCE,), inputs=_INPUTS,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    columns = ["instrument_id", *COLUMNS]
    stored = inputs.get(LAUNCHES)
    if stored is None or stored.empty:
        return pd.DataFrame(columns=columns)
    rows = stored[stored["event_date"] <= session].sort_values(
        ["instrument_id", "event_date"], kind="stable"
    )
    rows = rows.drop_duplicates("instrument_id", keep="first")
    if rows.empty:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        {
            "instrument_id": rows["instrument_id"].astype(str).to_numpy(),
            "last_etf_launch_date": list(rows["event_date"]),
            "sessions_since_etf_launch": pd.array(
                [sessions_to(day, session) for day in rows["event_date"]], dtype="Int64"
            ),
            "etf_category": rows["etf_category"].to_numpy(),
            "etf_theme": rows["etf_theme"].to_numpy(),
            "launch_date_source": LAUNCH_SOURCE,
        }
    )[columns].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How long ago a specialised ETF (thematic or sector) launched, from its first listing day",
    (Input(LAUNCHES, lookback=LOOKBACK, required=False),),
    FEATURES,
    compute,
)
