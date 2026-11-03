"""``event_calendar@v1``: the next reaction session of each scheduled macro release (ADR 0050 EV6,
docs/event-sensitivity-plan.md 5.4): the calendar of what is coming, as columns of every
instrument's row (an expression feature reads one entity, so the market's dates are repeated per
name), so a screen reads "days to the next impact event" and "impact events before the expiry" as
expression features over a name's own reactions (``event_reaction@v1``) without a calendar scan
per name.

Input: ``events/macro_release`` known by the session (``known_from <= S``: the latest version of
each release, a ``moved`` date dropped, ``moves.release_days``). For each release key, the first
reaction session after the session (a release at or before 16:00 ET reacts on its own session, a
later one on the next; ``moves.reaction_session``): a release made today before the close has
reacted already and is not ahead. A key with no release ahead in the stored calendar is null
(UNKNOWN: the calendar's horizon, never "nothing is coming"). One row per instrument traded on the
session.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.event_study import moves
from algotrade.features.rollups.event_study.event_reaction import MACRO_RELEASE
from algotrade.features.rollups.price.price_stats import BARS

NAME = "event_calendar"
VERSION = 1
_REL = f"{MACRO_RELEASE}.release_date"
_NONE = "no release of the key is ahead in the stored calendar known by the session"


def _features() -> tuple[Feature, ...]:
    out: list[Feature] = []
    for key in moves.MACRO_KEYS:
        k = key.lower()
        out.append(
            Feature(
                f"{k}_next_date",
                "date",
                "date",
                f"The session the next {key} release reacts on (a release after the close: the "
                "next session)",
                _NONE,
                inputs=(_REL,),
            )
        )
        out.append(
            Feature(
                f"{k}_sessions_to",
                "int",
                "sessions",
                f"Exchange sessions from the session to the next {key} release's reaction session",
                _NONE,
                valid_range=(1, None),
                inputs=(_REL,),
            )
        )
    return tuple(out)  # fmt: skip


FEATURES = _features()
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    ahead: dict[str, date] = {}
    for key, day, time_et in moves.release_days(inputs.get(MACRO_RELEASE), session):
        if key not in moves.MACRO_KEYS:
            continue
        reacts = moves.reaction_session(day, time_et)
        if reacts > session and (key not in ahead or reacts < ahead[key]):
            ahead[key] = reacts
    row: dict[str, object] = {}
    for key in moves.MACRO_KEYS:
        k = key.lower()
        nxt = ahead.get(key)
        row[f"{k}_next_date"] = nxt if nxt is not None else pd.NaT
        row[f"{k}_sessions_to"] = sessions_to(session, nxt) if nxt is not None else np.nan
    bars = inputs[BARS]
    assert bars is not None  # required input
    ids = sorted(set(bars.loc[bars["session_date"] == session, "instrument_id"].astype(str)))
    frame = pd.DataFrame(
        [{"instrument_id": i, **row} for i in ids], columns=["instrument_id", *COLUMNS]
    )
    for name, dtype in COLUMNS.items():
        if dtype == "int":
            frame[name] = frame[name].astype("Int64")
    return frame


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The session each scheduled macro release (CPI, jobs, FOMC, ...) next reacts on, so a screen "
    "can count the impact events before an expiry",
    (Input(BARS, lookback=1), Input(MACRO_RELEASE, lookback=0, required=False)),
    FEATURES,
    compute,
)
