"""``ibkr_iv@v1``: IBKR's IV30 and HV30 and the IV rank and percentile over a year of them.

Input: ``volatility/ibkr_iv30`` (IB's 30-day implied vol of the underlying's options and its
30-day historical vol; ADR 0028) for the session and the ``window - 1`` sessions before it.
One row per instrument with an IBKR row on the session.

    iv30_ibkr                  the session's IBKR IV30
    hv30_ibkr                  the session's IBKR HV30
    iv_rank_252d_ibkr          (iv - min) / (max - min) over the window's IBKR IVs
    iv_percentile_252d_ibkr    share of the window's EARLIER IBKR IVs strictly below today's
    history_days_ibkr          sessions of the window with an IBKR IV (today included)
    rank_status_ibkr           UNKNOWN / PROVISIONAL / FULL

The rank, percentile and status follow ``iv_history@v2`` exactly (``iv_history.history``):
same window, same thresholds (``rollups.toml ["ibkr_iv@v1"]``, defaults equal to
``["iv_history@v2"]``), gaps counted out, never filled. Every feature here is derived from
IBKR market data: ``licence = "personal"``. The site's ``iv_rank`` / ``iv_percentile``
expression features prefer these and fall back to ours, saying which they used
(``config/site/features/volatility.toml``).
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence
from algotrade.features.rollups.options.iv_history import IvHistoryParams, history

NAME = "ibkr_iv"
VERSION = 1
TABLE = "volatility/ibkr_iv30"

_IV, _HV = f"{TABLE}.iv30_ibkr", f"{TABLE}.hv30_ibkr"
_UNKNOWN = (
    "rank_status_ibkr is UNKNOWN (fewer than 60 sessions with an IBKR IV), or IBKR has no IV "
    "for the session"
)
_P: Licence = "personal"

FEATURES = (
    Feature(
        "iv30_ibkr", "float32", "decimal",
        "IBKR's 30-day implied vol of the underlying's options for the session (IB's daily "
        "OPTION_IMPLIED_VOLATILITY bar, or the streamed tick 106 after the close)",
        "IBKR had no implied vol for the underlying (no listed options, no quotes)",
        valid_range=(0, 5), inputs=(_IV,), licence=_P,
    ),
    Feature(
        "hv30_ibkr", "float32", "decimal",
        "IBKR's 30-day historical (realised) vol of the underlying for the session",
        "IBKR had no historical vol for the session; or the session has no nightly snapshot "
        "(the IV history backfill fetches no HV: it comes from the snapshot only)",
        valid_range=(0, 5), inputs=(_HV,),
        licence=_P,
    ),
    Feature(
        "iv_rank_252d_ibkr", "float32", "decimal",
        "IV rank on IBKR's IV: (iv - min) / (max - min) over the last 252 sessions, today "
        "included", f"{_UNKNOWN}; or every IV in the window is equal", valid_range=(0, 1),
        inputs=(_IV,), licence=_P,
    ),
    Feature(
        "iv_percentile_252d_ibkr", "float32", "decimal",
        "IV percentile on IBKR's IV: the share of the window's earlier IVs strictly below "
        "today's", f"{_UNKNOWN}; or no earlier IV", valid_range=(0, 1), inputs=(_IV,),
        licence=_P,
    ),
    Feature(
        "history_days_ibkr", "int", "sessions",
        "Sessions of the 252-session window with an IBKR IV, today included (gaps are not "
        "filled)", "never", valid_range=(0, None), inputs=(_IV,), licence=_P,
    ),
    Feature(
        "rank_status_ibkr", "str", "category",
        "UNKNOWN below 60 sessions with an IBKR IV (no rank), PROVISIONAL below 252, FULL "
        "from 252", "never", "label", categories=("UNKNOWN", "PROVISIONAL", "FULL"),
        inputs=(_IV,), licence=_P,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class IbkrIvParams:
    window: int = 252  # sessions for FULL (today included); as iv_history@v2
    min_provisional: int = 60  # sessions with an IV before the rank is shown (PROVISIONAL)

    def __post_init__(self) -> None:
        if not 2 <= self.min_provisional <= self.window:
            raise ValueError("need 2 <= min_provisional <= window")


def compute(inputs: Inputs, session: date, p: IbkrIvParams) -> pd.DataFrame:
    rows = inputs[TABLE]
    assert rows is not None  # required input
    rows = rows.assign(instrument_id=rows["instrument_id"].astype(str))
    today = rows[rows["session_date"] == session].drop_duplicates("instrument_id")
    ids = sorted(today["instrument_id"].unique())
    days = sessions_ending(session, p.window)
    matrix = (
        rows.assign(v=rows["iv30_ibkr"].astype(float))
        .pivot_table(index="session_date", columns="instrument_id", values="v", dropna=False)
        .reindex(index=days, columns=ids)
        .to_numpy(dtype=float)
    )
    ranked = history(matrix, IvHistoryParams(p.window, p.min_provisional))
    hv = today.set_index("instrument_id")["hv30_ibkr"].astype(float).reindex(ids)
    return pd.DataFrame(
        {
            "instrument_id": ids,
            "iv30_ibkr": ranked["iv30"],
            "hv30_ibkr": hv.to_numpy(),
            "iv_rank_252d_ibkr": ranked["iv_rank_252d"],
            "iv_percentile_252d_ibkr": ranked["iv_percentile_252d"],
            "history_days_ibkr": ranked["history_days"],
            "rank_status_ibkr": ranked["rank_status"],
        }
    )


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "IBKR's IV30 and HV30, and the IV rank and percentile over 252 sessions of IBKR's IV "
    "(provisional after 60; personal-use licence)",
    (Input(TABLE, lookback=lambda p: p.window - 1),),
    FEATURES,
    compute,
    IbkrIvParams(),
)
