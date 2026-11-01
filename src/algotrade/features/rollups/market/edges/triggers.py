"""``market_triggers@v2``: the market-level triggers an ``on_market:<trigger>`` edge times by
(ADR 0075), one ``MKT:US`` row per session. The first trigger is the VIX spike; the second
(v2, ADR 0088) is the first session the curve is back in contango after a spike.

Inputs: ``macro/series`` VIX (FRED ``VIXCLS``) and VIX3M (``VXVCLS``), Cboe closes with
``pit = "lag"`` and ``release_lag_days = 1`` (``config/site/macro.toml``; personal use only, so
the group is ``licence = "personal"``). Neither is revised: an observation has one value and
is known from the session after its date, the same rule for history and live.

A day is *high* when its VIX is at least ``SPIKE_LEVEL`` and VIX / VIX3M is above 1
(backwardation). The *spike* is the first high day after at least ``QUIET_SESSIONS`` sessions
without a high one, so a month of high readings is one spike. The thresholds are fixed here:
changing one is a new version (ADR 0023). The spike's date D is the session the reading was
first known (the session after its observation date), not the observation date.

    vix_spike_date           D of the latest spike known by the session
    sessions_since_vix_spike exchange sessions from D to the session (0: the session is D)
    vix_spike_level          the VIX close of the spike's observation

The *post-spike contango* trigger is the first session of a recovery (design section 2.1, R-B):
VIX at least ``RECOVERY_OFF_HIGH`` below its ``HIGH_WINDOW``-observation high, VIX / VIX3M
below 1 (back in contango) and VIX above its ``MEDIAN_WINDOW``-observation median, after
``RESET_SESSIONS`` sessions with that state off (a long recovery is one trigger; a curve that
re-inverts and recovers again, after the reset, is a second). Its windows are complete or the
day is not judged, so it needs ``MEDIAN_WINDOW + RESET_SESSIONS`` observations of history. Its
date is the session the reading was first known, like the spike's; the thresholds are fixed here.

    post_spike_contango_date           D of the latest such trigger known by the session
    sessions_since_post_spike_contango sessions from D to the session; ``NONE_SEEN`` when fresh
                                       and none seen

v2 added the two post-spike columns to v1's; the spike columns are computed as v1 did, over the
same ``LOOKBACK`` sessions (the input reads more for the median window). v1 is superseded.

Only observations known by the session are read (``LOOKBACK`` sessions of them), so a spike is
judged on what the session knew; a spike needs ``QUIET_SESSIONS`` of history before it, so
none is found in the first sessions of the history read. Stale is not quiet: when the newest
VIX or VIX3M observation known is more than ``MAX_AGE_SESSIONS`` sessions old, every column is
null (UNKNOWN), never an older spike and never "no spike". Fresh readings with no spike in
the lookback have ``sessions_since_vix_spike = NONE_SEEN`` and a null date and level, so a reader
(``time_series/triggers.py``) tells "none seen" from "not known".
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import next_session, sessions_ending, sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.market.macro import ID, MACRO
from algotrade.features.rollups.market.observations import Series, as_series, fresh

NAME = "market_triggers"
VERSION = 2
SPIKE_LEVEL = 30.0  # a high day: VIX at least this
QUIET_SESSIONS = 21  # sessions without a high day before a spike (and of history it needs)
MAX_AGE_SESSIONS = 3  # the newest observation older than this is stale
LOOKBACK = 300  # sessions of observations judged: triggers older than this are not seen
RECOVERY_OFF_HIGH = 0.25  # post-spike contango: VIX at least this far below its recent high
HIGH_WINDOW = 20  # ... the high over this many observations
MEDIAN_WINDOW = 252  # ... and above the median over this many
RESET_SESSIONS = 21  # sessions with the state off before the next trigger
READ = LOOKBACK + MEDIAN_WINDOW + RESET_SESSIONS  # sessions of observations the input reads
NONE_SEEN = LOOKBACK + 1  # sessions_since_vix_spike when the readings are fresh and hold no spike
VIX, VIX3M = ID["VIX"], ID["VIX3M"]
_UNKNOWN = (
    "VIX or VIX3M has no observation known by the session, or its newest is more than "
    f"{MAX_AGE_SESSIONS} sessions old (stale: nothing is read, never 'no spike')"
)
_NONE = f"{_UNKNOWN}; or no spike in the last {LOOKBACK} sessions of observations"
_SINCE_NONE = _UNKNOWN
_INPUTS = ("series:VIX", "series:VIX3M")
_CONTANGO_NONE = (
    f"{_UNKNOWN}; or no post-spike contango trigger in the last {LOOKBACK} sessions of observations"
)

FEATURES = (
    Feature(
        "vix_spike_date", "date", "date",
        f"The session the latest VIX spike was first known: the first day with VIX at least "
        f"{SPIKE_LEVEL:g} and VIX / VIX3M above 1 after {QUIET_SESSIONS} sessions without one "
        "(known from the session after its close)",
        _NONE, inputs=_INPUTS, licence="personal",
    ),
    Feature(
        "sessions_since_vix_spike", "int", "sessions",
        "Exchange sessions from the latest VIX spike's session up to the session (0: the "
        f"session is that day); {NONE_SEEN} when the readings are fresh and no spike is in the "
        f"last {LOOKBACK} sessions", _SINCE_NONE, valid_range=(0, NONE_SEEN), inputs=_INPUTS,
        licence="personal",
    ),
    Feature(
        "vix_spike_level", "float32", "pct_points",
        "The VIX close of the latest spike (20 = 20% implied vol)", _NONE,
        valid_range=(SPIKE_LEVEL, 150), inputs=_INPUTS, licence="personal",
    ),
    Feature(
        "post_spike_contango_date", "date", "date",
        f"The session the latest post-spike contango trigger was first known: the first day VIX "
        f"is {RECOVERY_OFF_HIGH:.0%} or more below its {HIGH_WINDOW}-observation high, VIX / "
        f"VIX3M is below 1 and VIX is above its {MEDIAN_WINDOW}-observation median, after "
        f"{RESET_SESSIONS} sessions without that state (known from the session after its close)",
        _CONTANGO_NONE, inputs=_INPUTS, licence="personal",
    ),
    Feature(
        "sessions_since_post_spike_contango", "int", "sessions",
        "Exchange sessions from the latest post-spike contango trigger's session up to the "
        f"session (0: the session is that day); {NONE_SEEN} when the readings are fresh and none "
        f"is in the last {LOOKBACK} sessions", _SINCE_NONE, valid_range=(0, NONE_SEEN),
        inputs=_INPUTS, licence="personal",
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def spike(series: dict[str, Series], session: date) -> tuple[date, float] | None:
    """``(D, VIX)`` of the latest spike known by ``session``, or ``None`` (no spike in the
    history, or either series stale: the caller tells those apart with ``vix_stale``)."""
    vix, vix3m = series.get(VIX), series.get(VIX3M)
    if vix is None or vix3m is None:
        return None
    both = pd.concat({"vix": vix, "vix3m": vix3m}, axis=1, join="inner").sort_index()
    if both.empty:
        return None
    first = pd.Timestamp(both.index[0]).date()
    found: tuple[date, float] | None = None
    last_high: date | None = None
    for ts, row in both.iterrows():
        day = pd.Timestamp(str(ts)).date()
        if not (row["vix"] >= SPIKE_LEVEL and row["vix"] / row["vix3m"] > 1):
            continue
        quiet = last_high is None or sessions_to(last_high, day) - 1 >= QUIET_SESSIONS
        if quiet and sessions_to(first, day) >= QUIET_SESSIONS and next_session(day) <= session:
            found = (next_session(day), float(row["vix"]))
        last_high = day
    return found


def post_spike_contango(series: dict[str, Series], session: date) -> date | None:
    """D of the latest post-spike contango trigger known by ``session`` and within ``LOOKBACK``
    sessions of it, or ``None`` (none in the history, or either series stale: the caller tells
    those apart with ``vix_stale``)."""
    vix, vix3m = series.get(VIX), series.get(VIX3M)
    if vix is None or vix3m is None:
        return None
    high = vix.rolling(HIGH_WINDOW).max()
    median = vix.rolling(MEDIAN_WINDOW).median()
    state = pd.concat({"vix": vix, "vix3m": vix3m, "high": high, "median": median}, axis=1)
    state = state.dropna().sort_index()  # a day is judged only with every window complete
    on = (
        (state["vix"] <= state["high"] * (1 - RECOVERY_OFF_HIGH))
        & (state["vix"] < state["vix3m"])
        & (state["vix"] > state["median"])
    )
    start = sessions_ending(session, LOOKBACK + 1)[0]
    found: date | None = None
    quiet = 0  # consecutive judged days with the state off
    for ts, is_on in on.items():
        day = pd.Timestamp(str(ts)).date()
        if is_on and quiet >= RESET_SESSIONS and next_session(day) <= session:
            known = next_session(day)
            found = known if known >= start else found
        quiet = 0 if is_on else quiet + 1
    return found


def vix_stale(series: dict[str, Series], session: date) -> bool:
    """Whether VIX or VIX3M has no fresh observation known by ``session``."""
    return not (
        fresh(series.get(VIX), session, MAX_AGE_SESSIONS)
        and fresh(series.get(VIX3M), session, MAX_AGE_SESSIONS)
    )


def trigger_row(series: dict[str, Series], session: date) -> dict[str, object]:
    """Every column for ``session`` from the known ``series`` (by id)."""
    empty: dict[str, object] = {
        "vix_spike_date": None, "sessions_since_vix_spike": np.nan, "vix_spike_level": np.nan,
        "post_spike_contango_date": None, "sessions_since_post_spike_contango": np.nan,
    }  # fmt: skip
    if vix_stale(series, session):
        return empty
    # a fresh reading and nothing seen: told apart from stale by the NONE_SEEN count
    row = {**empty, "sessions_since_vix_spike": NONE_SEEN,
           "sessions_since_post_spike_contango": NONE_SEEN}  # fmt: skip
    found = spike(_trimmed(series, session), session)
    if found is not None:
        day, level = found
        row.update(vix_spike_date=day, sessions_since_vix_spike=sessions_to(day, session),
                   vix_spike_level=level)  # fmt: skip
    contango = post_spike_contango(series, session)
    if contango is not None:
        row.update(post_spike_contango_date=contango,
                   sessions_since_post_spike_contango=sessions_to(contango, session))  # fmt: skip
    return row


def _trimmed(series: dict[str, Series], session: date) -> dict[str, Series]:
    """The observations of the last ``LOOKBACK`` sessions: what the spike columns judged in v1
    (the input now reads more, for the post-spike median window)."""
    start = pd.Timestamp(sessions_ending(session, LOOKBACK + 1)[0])
    return {k: s[s.index >= start] for k, s in series.items()}


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    row = {"instrument_id": market_id("US"), **trigger_row(as_series(inputs[MACRO]), session)}
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Market-level triggers for the time-series edges: the latest VIX spike (VIX at least 30 "
    "in backwardation after 21 quiet sessions) and the latest post-spike contango (VIX 25% off "
    "its high with the curve back in contango), known from the session after the close",
    (Input(MACRO, lookback=READ, required=False, ids=(VIX, VIX3M)),),
    FEATURES,
    compute,
    entity="market",
)
