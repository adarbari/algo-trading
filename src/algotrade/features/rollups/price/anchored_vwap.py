"""``anchored_vwap@v1``: the volume-weighted average price since the last earnings report
(``docs/data/swing.md``).

Inputs: every ``events/earnings`` row known on or before the session (ADR 0050), read as
``earnings@v1`` reads them (``corporate.earnings.valid_events``: the latest snapshot covering a
date is its authority, moved or cancelled dates are dropped; only report dates from the
session before the window on, the only ones that can anchor), and ``bars/1d`` split-adjusted AS
OF the session (prices divided and volume multiplied by the splits up to it), the session plus
``MAX_SESSIONS`` earlier ones. One row per instrument with a bar on the session.

The **anchor** is the session a report's price reaction starts: the report date's session for
a report before the open (``pre_market``) or at an unknown time (the report day then holds the
reaction of a pre-market report), the next session for one after the close (``after_hours``).
The anchor used is the latest one on or before the session among the reports known then, so a
report due after today's close leaves the previous one in place until tomorrow.

    avwap_earnings     sum(typical x volume) / sum(volume) from the anchor session through
                       the session, typical = (high + low + close) / 3
    avwap_anchor_date  that anchor session

The window cap (``MAX_SESSIONS``, 126: about two quarters) is part of the definition.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate.earnings import EVENTS, valid_events
from algotrade.features.rollups.price.price_stats import panel

NAME = "anchored_vwap"
VERSION = 1
BARS = "bars/1d"
MAX_SESSIONS = 126  # an anchor further back than this (sessions before the session) is stale
AFTER_CLOSE = "after_hours"

_REPORT = (f"{EVENTS}.ts", f"{EVENTS}.time")
_NO_ANCHOR = (
    f"no report known on the session anchors on or before it within the last {MAX_SESSIONS} "
    "sessions (no earlier report stored, or the last one is older)"
)

FEATURES = (
    Feature(
        "avwap_earnings", "float32", "usd_per_share",
        "Volume-weighted average of the typical price (high + low + close) / 3 from the last "
        "earnings anchor session through the session (the anchor: the report date, or the "
        "next session for a report after the close)",
        f"{_NO_ANCHOR}; or fewer than 2 sessions from the anchor through the session, a "
        "session in that range without a bar, or no volume in it",
        valid_range=(0, None),
        inputs=(*_REPORT, f"{BARS}.high", f"{BARS}.low", f"{BARS}.close", f"{BARS}.volume"),
    ),
    Feature(
        "avwap_anchor_date", "date", "date",
        "The session avwap_earnings is anchored on: the last report date (pre-market or "
        "unknown time) or the session after it (after the close)",
        _NO_ANCHOR, inputs=_REPORT,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def anchors(reports: pd.DataFrame, days: list[date]) -> pd.Series:
    """The latest anchor row in ``days`` per instrument (``days[0]`` is the session before the
    window: an anchor there or earlier is too old and is dropped). ``reports``: valid events
    with ``report`` (date) and ``time``."""
    when = np.array(days, dtype="datetime64[D]")
    reported = reports["report"].to_numpy(dtype="datetime64[D]")
    after = reports["time"].astype(str).to_numpy() == AFTER_CLOSE if "time" in reports else False
    row = np.where(
        after,
        np.searchsorted(when, reported, side="right"),
        np.searchsorted(when, reported, side="left"),
    )
    found = pd.Series(row, index=reports["instrument_id"].astype(str).to_numpy())
    found = found[found < len(days)]  # anchored after the session: not yet
    latest = found.groupby(level=0).max()
    return latest[latest >= 1]


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored, bars = inputs[EVENTS], inputs[BARS]
    assert stored is not None and bars is not None  # required inputs
    days = sessions_ending(session, MAX_SESSIONS + 2)  # the window plus the session before it
    px = panel(bars, days[1:])
    traded = ~np.isnan(px.close[-1])
    # A report before days[0] anchors at row 0 at the latest: too old, never used.
    reports = valid_events(stored, since=days[0])
    rows = anchors(reports[reports["report"] <= session], days).reindex(px.ids) - 1
    typical = (px.high + px.low + px.close) / 3
    # sums from each row through the last one (a missing bar counts in ``gaps``)
    weighted = np.nan_to_num(typical * px.volume)[::-1].cumsum(axis=0)[::-1]
    volume = np.nan_to_num(px.volume)[::-1].cumsum(axis=0)[::-1]
    gaps = np.isnan(px.close)[::-1].cumsum(axis=0)[::-1]
    start = rows.to_numpy(dtype=float)
    has = ~np.isnan(start)
    at = np.where(has, start, 0).astype(np.int64)
    cols = np.arange(len(px.ids))
    total = volume[at, cols]
    ok = has & (gaps[at, cols] == 0) & (len(days) - 2 - at >= 1) & (total > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        avwap = np.where(ok, weighted[at, cols] / total, np.nan)
    anchor = [days[1 + a] if h else None for a, h in zip(at, has, strict=True)]
    return pd.DataFrame(
        {
            "instrument_id": px.ids[traded],
            "avwap_earnings": avwap[traded],
            "avwap_anchor_date": [d for d, t in zip(anchor, traded, strict=True) if t],
        }
    )


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "VWAP anchored to the last earnings report (from the reaction session through the session)",
    (Input(EVENTS), Input(BARS, lookback=MAX_SESSIONS)),
    FEATURES,
    compute,
)
