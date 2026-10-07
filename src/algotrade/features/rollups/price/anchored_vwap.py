"""``anchored_vwap@v2``: the volume-weighted average price since the last earnings report, and
since the swing low and the swing high ``swing_levels@v1`` found (``docs/data/swing.md``,
``docs/data/technical.md``).

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
    avwap_swing_low    the same average from swing_levels@v1's swing_low_date (support) through
                       the session; avwap_swing_high from swing_high_date (resistance)

The earnings window cap (``MAX_SESSIONS``, 126: about two quarters) is part of the definition;
a swing anchor can be up to ``SWING_SESSIONS`` (251) sessions back, as far as swing_levels
looks. v2 adds the swing anchors (ADR 0023 step 6: a new stored column is a new version).
"""

from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate.earnings import EVENTS, valid_events
from algotrade.features.rollups.price.price_stats import Matrix, Panel, panel, traded_rows

NAME = "anchored_vwap"
VERSION = 2
BARS = "bars/1d"
SWING_LEVELS = "rollups/instrument/swing_levels@v1"
MAX_SESSIONS = (
    126  # an earnings anchor further back than this (sessions before the session) is stale
)
SWING_SESSIONS = 251  # a swing anchor can be this far back (swing_levels@v1's window)
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
    *(
        Feature(
            f"avwap_swing_{side}", "float32", "usd_per_share",
            "Volume-weighted average of the typical price (high + low + close) / 3 from the "
            f"session of swing_levels@v1's swing_{side} "
            f"({'support' if side == 'low' else 'resistance'}) through the session: where the "
            "average participant since that pivot is positioned",
            f"no swing_{side} on the session (no swing_levels row, or no confirmed pivot "
            f"{'below' if side == 'low' else 'above'} the close); or fewer than 2 sessions "
            "from the pivot through the session, a session in that range without a bar, or no "
            "volume in it",
            valid_range=(0, None),
            inputs=(
                f"swing_levels.swing_{side}_date@v1",
                f"{BARS}.high", f"{BARS}.low", f"{BARS}.close", f"{BARS}.volume",
            ),
        )
    for side in ("low", "high")
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


def vwap_from(px: Panel, start: npt.NDArray[np.float64]) -> Matrix:
    """Per column: the VWAP of the typical price from row ``start`` (NaN: no anchor) through
    the last row; NaN when fewer than 2 rows, a missing bar in the range, or no volume."""
    typical = (px.high + px.low + px.close) / 3
    # sums from each row through the last one (a missing bar counts in ``gaps``)
    weighted = np.nan_to_num(typical * px.volume)[::-1].cumsum(axis=0)[::-1]
    volume = np.nan_to_num(px.volume)[::-1].cumsum(axis=0)[::-1]
    gaps = np.isnan(px.close)[::-1].cumsum(axis=0)[::-1]
    has = ~np.isnan(start)
    at = np.where(has, start, 0).astype(np.int64)
    cols = np.arange(len(px.ids))
    total = volume[at, cols]
    ok = has & (gaps[at, cols] == 0) & (len(px.close) - 1 - at >= 1) & (total > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.asarray(np.where(ok, weighted[at, cols] / total, np.nan))


def _swing_rows(
    levels: pd.DataFrame | None, ids: npt.NDArray[np.str_], days: list[date], side: str
) -> npt.NDArray[np.float64]:
    """Per instrument: the row of ``days`` its swing pivot sits on (NaN: none)."""
    if levels is None or levels.empty:
        return np.full(len(ids), np.nan)
    dates = levels.set_index(levels["instrument_id"].astype(str))[f"swing_{side}_date"]
    index = {d: i for i, d in enumerate(days)}
    picked = dates.reindex(ids)
    return np.array(
        [index.get(d, np.nan) if isinstance(d, date) else np.nan for d in picked], dtype=float
    )


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored, bars = inputs[EVENTS], inputs[BARS]
    assert stored is not None and bars is not None  # required inputs
    days = sessions_ending(session, SWING_SESSIONS + 1)
    px = panel(bars, days)
    # Earnings: the window is the last MAX_SESSIONS + 1 sessions plus the session before it;
    # a report before that anchors at its row 0 at the latest: too old, never used.
    earn_days = days[-MAX_SESSIONS - 2 :]
    reports = valid_events(stored, session, since=earn_days[0])
    rows = anchors(reports[reports["report"] <= session], earn_days).reindex(px.ids) - 1
    offset = len(days) - (MAX_SESSIONS + 1)
    start = rows.to_numpy(dtype=float) + offset
    avwap = vwap_from(px, start)
    has = ~np.isnan(start)
    at = np.where(has, start, 0).astype(np.int64)
    anchor = np.array([days[a] if h else None for a, h in zip(at, has, strict=True)], dtype=object)
    values: dict[str, Matrix] = {"avwap_earnings": avwap, "avwap_anchor_date": anchor}
    for side in ("low", "high"):
        values[f"avwap_swing_{side}"] = vwap_from(
            px, _swing_rows(inputs[SWING_LEVELS], px.ids, days, side)
        )
    return traded_rows(px, values, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "VWAP anchored to the last earnings report (from the reaction session through the session) "
    "and to the swing low and swing high swing_levels@v1 found",
    (Input(EVENTS), Input(BARS, lookback=SWING_SESSIONS), Input(SWING_LEVELS, required=False)),
    FEATURES,
    compute,
)
