"""``cohort_pct_options@v1``: the percentile rank of the IV rank among the universe's stocks,
the instrument's sector and its industry (ADR 0023; ``members.py`` for the cohorts).

Inputs (each optional: a missing source makes its columns null): ``iv_history@v2``
(``iv_rank_252d``, ranked from our own open ``iv30``, never the coalesced ``iv_rank`` that may
carry an IBKR value), ``universe`` and ``instruments/company``. One row per instrument with an
``iv_history`` row on the session. A percentile is the average rank among the cohort's known
values, 0 the lowest and 1 the highest (``quant.cross_section``); a name with no IV rank (too
little history, a thin chain) is not counted in its cohort.

Parameters: ``CohortParams`` (``config/site/rollups.toml`` ``["cohort_pct_options@v1"]``;
``min_coverage`` is not used).
"""

from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.rollups.cohort.members import (
    COMPANY,
    LEVELS,
    UNIVERSE,
    CohortParams,
    percentile_features,
    percentile_frame,
)

NAME = "cohort_pct_options"
VERSION = 1
IV_HISTORY = "rollups/instrument/iv_history@v2"
# (table, source column, the levels it is ranked at)
SOURCES = ((IV_HISTORY, "iv_rank_252d", LEVELS),)
_WHAT = {"iv_rank_252d": "where today's IV30 sits in its 252-session range"}
FEATURES = percentile_features(SOURCES, _WHAT)
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, p: CohortParams) -> pd.DataFrame:
    return percentile_frame(inputs, session, p, SOURCES, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Percentile ranks of the 252-session IV rank among the universe's stocks, the "
    "instrument's sector and its industry",
    (
        Input(IV_HISTORY, required=False),
        Input(UNIVERSE, required=False),
        Input(COMPANY, required=False),
    ),
    FEATURES,
    compute,
    CohortParams(),
)
