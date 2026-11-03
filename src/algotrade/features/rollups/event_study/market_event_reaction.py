"""``market_event_reaction@v1``: how far each macro release and rule day has moved the S&P 500, in
normal days (ADR 0050, plan 4.4: the market's own sensitivity per release, ``IDX:SPX`` as the
entity, ADR 0047), so a name's multiple in ``event_reaction@v1`` can be read against the index's.

Input: the index level ``IDX:SPX`` (``macro/series``, each observation as the session knew it)
laid on the ``HISTORY`` sessions ending at the session, and ``events/macro_release`` known by the
session; the maths are ``moves``' (the reaction session, the log return, the normal day, the
multiple), the same as the instrument group's. One ``MKT:US`` row; every column is null (UNKNOWN)
when the index has fewer than 250 levels on the grid or no release of the class has a reaction
session with a complete normal day.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import index_id, market_id
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.event_study import moves
from algotrade.features.rollups.event_study.event_reaction import (
    HISTORY,
    MACRO_RELEASE,
    class_features,
)
from algotrade.features.rollups.market.macro import MACRO
from algotrade.features.rollups.market.observations import as_series

NAME = "market_event_reaction"
VERSION = 1
SPX = index_id("SPX")
_REL = f"{MACRO_RELEASE}.release_date"
_LEVEL = f"{MACRO}.value"


def _features() -> tuple[Feature, ...]:
    out: list[Feature] = []
    for key in moves.MACRO_KEYS:
        out += class_features(f"spx_macro_{key.lower()}", f"S&P 500 {key} release", (_LEVEL, _REL))
    for name in moves.STRUCTURE:
        out += class_features(f"spx_{name}", f"S&P 500 {name.replace('_', ' ')}", (_LEVEL,))
    return tuple(out)


FEATURES = _features()
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    grid = sessions_ending(session, HISTORY + 1)
    level = as_series(inputs[MACRO]).get(SPX)
    close = np.full((len(grid), 1), np.nan)
    if level is not None:
        days = pd.DatetimeIndex(pd.to_datetime(grid))
        close[:, 0] = level.reindex(days).to_numpy(dtype=np.float64)
    returns = moves.log_returns(close)
    mult = moves.multiples(returns)
    releases = moves.release_days(inputs.get(MACRO_RELEASE), session)
    macro = moves.macro_positions(grid, releases)
    structure = moves.structure_positions(grid)
    row: dict[str, object] = {"instrument_id": market_id("US")}
    has_index = int(np.isfinite(close).sum()) >= moves.MIN_SESSIONS
    classes = {f"spx_macro_{k.lower()}": macro[k] for k in moves.MACRO_KEYS}
    classes |= {f"spx_{name}": structure[name] for name in moves.STRUCTURE}
    seen = {f"spx_macro_{k.lower()}" for k, _, _ in releases}
    for prefix, positions in classes.items():
        n, median, down = moves.class_stats(mult, returns, positions)
        enough = has_index and (prefix in seen or not prefix.startswith("spx_macro_"))
        row[f"{prefix}_n"] = int(n[0]) if enough else pd.NA
        row[f"{prefix}_multiple_median"] = float(median[0]) if enough else np.nan
        row[f"{prefix}_down_worst"] = float(down[0]) if enough else np.nan
    frame = pd.DataFrame([row], columns=["instrument_id", *COLUMNS])
    for name, dtype in COLUMNS.items():
        if dtype == "int":
            frame[name] = frame[name].astype("Int64")
    return frame


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How far each macro release, monthly option expiry and quarter end has moved the S&P 500 in "
    "normal days: the market's reaction the name's own is read against",
    (
        Input(MACRO, lookback=HISTORY + 30, required=False, ids=(SPX,)),
        Input(MACRO_RELEASE, lookback=0, required=False),
    ),
    FEATURES,
    compute,
    entity="market",
)
