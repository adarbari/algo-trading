"""``market_triggers@v1``: the market-level triggers an ``on_market:<trigger>`` edge times by
(ADR 0075), one ``MKT:US`` row per session. The first trigger is the VIX spike.

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

Only observations known by the session are read (``LOOKBACK`` sessions of them), so a spike is
judged on what the session knew; a spike needs ``QUIET_SESSIONS`` of history before it, so
none is found in the first sessions of the history read. Stale is not quiet: when the newest
VIX or VIX3M observation known is more than ``MAX_AGE_SESSIONS`` sessions old, every column is
null (UNKNOWN), never an older spike and never "no spike".
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import next_session, sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.market.macro import ID, MACRO
from algotrade.features.rollups.market.observations import Series, as_series, fresh

NAME = "market_triggers"
VERSION = 1
SPIKE_LEVEL = 30.0  # a high day: VIX at least this
QUIET_SESSIONS = 21  # sessions without a high day before a spike (and of history it needs)
MAX_AGE_SESSIONS = 3  # the newest observation older than this is stale
LOOKBACK = 300  # sessions of observations read: spikes older than this are not seen
VIX, VIX3M = ID["VIX"], ID["VIX3M"]
_UNKNOWN = (
    "VIX or VIX3M has no observation known by the session, or its newest is more than "
    f"{MAX_AGE_SESSIONS} sessions old (stale: nothing is read, never 'no spike')"
)
_NONE = f"{_UNKNOWN}; or no spike in the last {LOOKBACK} sessions of observations"
_INPUTS = ("series:VIX", "series:VIX3M")

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
        "session is that day)", _NONE, valid_range=(0, LOOKBACK + 1), inputs=_INPUTS,
        licence="personal",
    ),
    Feature(
        "vix_spike_level", "float32", "pct_points",
        "The VIX close of the latest spike (20 = 20% implied vol)", _NONE,
        valid_range=(SPIKE_LEVEL, 150), inputs=_INPUTS, licence="personal",
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
    }  # fmt: skip
    found = None if vix_stale(series, session) else spike(series, session)
    if found is None:
        return empty
    day, level = found
    return {
        "vix_spike_date": day,
        "sessions_since_vix_spike": sessions_to(day, session),
        "vix_spike_level": level,
    }


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    row = {"instrument_id": market_id("US"), **trigger_row(as_series(inputs[MACRO]), session)}
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Market-level triggers for the time-series edges: the latest VIX spike (VIX at least 30 "
    "in backwardation after 21 quiet sessions), known from the session after its close",
    (Input(MACRO, lookback=LOOKBACK, required=False, ids=(VIX, VIX3M)),),
    FEATURES,
    compute,
    entity="market",
)
