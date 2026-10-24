"""``cohort_pct_fundamental@v1``: the percentile rank of short-interest and valuation features
among the universe's stocks, the instrument's sector and its industry (ADR 0023;
``members.py`` for the cohorts).

Inputs (each optional: a missing source makes its columns null): ``short_interest@v1``
(``days_to_cover``), ``pe_ratio@v1`` (the expression feature ``pe_ratio``, materialised: a
code group reads tables only), ``universe`` and ``instruments/company``. One row per
instrument with a row of a source on the session. A percentile is the average rank among the
cohort's known values, 0 the lowest and 1 the highest (``quant.cross_section``). A negative
P/E is never shown, so a loss-making name has no P/E and is not counted in its cohort.

Parameters: ``CohortParams`` (``config/site/rollups.toml`` ``["cohort_pct_fundamental@v1"]``;
``min_coverage`` is not used: the sources are sparse by nature, not by a partial day).
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

NAME = "cohort_pct_fundamental"
VERSION = 1
SHORT = "rollups/instrument/short_interest@v1"
PE = "rollups/instrument/pe_ratio@v1"  # the materialised expression feature pe_ratio
# (table, source column, the levels it is ranked at)
SOURCES = (
    (SHORT, "days_to_cover", LEVELS),
    (PE, "pe_ratio", LEVELS),
)
_WHAT = {
    "days_to_cover": "FINRA's days to cover: the short position over the average daily volume",
    "pe_ratio": "trailing price to earnings; a loss-making name has none",
}
FEATURES = percentile_features(SOURCES, _WHAT, source_inputs={"pe_ratio": "pe_ratio@v1"})
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, p: CohortParams) -> pd.DataFrame:
    return percentile_frame(inputs, session, p, SOURCES, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Percentile ranks of FINRA's days to cover and the trailing P/E among the universe's "
    "stocks, the instrument's sector and its industry",
    (
        Input(SHORT, required=False),
        Input(PE, required=False),
        Input(UNIVERSE, required=False),
        Input(COMPANY, required=False),
    ),
    FEATURES,
    compute,
    CohortParams(),
)
