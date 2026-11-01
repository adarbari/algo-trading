"""``earnings_gap_volume@v1``: how much volume the last earnings report drew, against the volume
before it (the field the ``earnings_gap_volume`` screener confirms a reaction with, edge
``earnings_gap_volume_drift``, EB E3).

The window and the counted report are ``earnings_reaction@v2``'s own (``read_reactions``: a
report counts once ``known_from <= session`` and its window E-1 .. E+1 has closed), so the ratio
describes the same report as ``reaction_excess_return`` and ``sessions_since_reaction``:

    reaction_volume_ratio   the mean dollar volume of the sessions E-1, E and E+1 divided by the
                            mean dollar volume of the 20 sessions ending at E-1 inclusive (the
                            report day and after are left out), for the last counted report

``earnings_reaction@v2.earnings_volume_ratio`` is the mean of four reports' ratios, a habit of the
name; this is the last report's, the event itself. One row per instrument traded on the session;
null when no report is counted, a bar of the window or of the 20 sessions before is missing, or
the history is shorter (UNKNOWN, never zero).
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.corporate.earnings_reaction import (
    LOOKBACK,
    SYMBOLS,
    read_reactions,
    window_ratio,
)
from algotrade.features.rollups.price.price_stats import BARS

NAME = "earnings_gap_volume"
VERSION = 1

FEATURES = (
    Feature(
        "reaction_volume_ratio", "float32", "ratio",
        "Mean dollar volume of the last report's window (the sessions before, of and after it) "
        "divided by the mean dollar volume of the 20 sessions ending at the one before the report",
        "no report known by the session has a closed reaction window, or a bar of the window or "
        "of the 20 sessions before it is missing, or the history is shorter",
        valid_range=(0, None),
        inputs=("bars/1d.close", "bars/1d.volume", f"{earnings.EVENTS}.ts"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    read = read_reactions(inputs, session)
    traded = read.ids[~np.isnan(read.px[-1])]  # every instrument traded on the session
    ratios = [
        window_ratio(read, str(i), read.by_report[str(i)][0])
        if str(i) in read.by_report
        else np.nan
        for i in traded
    ]
    frame = pd.DataFrame({"instrument_id": traded.astype(str), "reaction_volume_ratio": ratios})
    frame["reaction_volume_ratio"] = frame["reaction_volume_ratio"].where(
        np.isfinite(frame["reaction_volume_ratio"])
    )
    return (
        frame[["instrument_id", *COLUMNS]]
        .sort_values("instrument_id", kind="stable")
        .reset_index(drop=True)
    )


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How much volume the last earnings report drew against the volume before it",
    (
        Input(earnings.EVENTS),
        Input(BARS, lookback=LOOKBACK),
        Input(SYMBOLS, required=False),
    ),
    FEATURES,
    compute,
    applies_to="operating_company",
)
