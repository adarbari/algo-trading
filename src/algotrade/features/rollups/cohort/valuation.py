"""``cohort_pct_valuation@v1``: the percentile rank of the trailing P/E among the universe's
stocks, the instrument's sector and its industry (ADR 0023; ``members.py`` for the cohorts).

Inputs (each optional: a missing source makes its columns null): ``pe_ratio@v1`` (the
expression feature ``pe_ratio``, materialised: a code group reads tables only), ``universe``
and ``instruments/company``. One row per instrument with a ``pe_ratio`` row on the session. A
negative P/E is never shown, so a loss-making name has no P/E and is not counted in its
cohort. A percentile is the average rank among the cohort's known values, 0 the lowest and 1
the highest (``quant.cross_section``).

Parameters: ``CohortParams`` (``config/site/rollups.toml`` ``["cohort_pct_valuation@v1"]``;
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

NAME = "cohort_pct_valuation"
VERSION = 1
PE = "rollups/instrument/pe_ratio@v1"  # the materialised expression feature pe_ratio
# (table, source column, the levels it is ranked at)
SOURCES = ((PE, "pe_ratio", LEVELS),)
_WHAT = {"pe_ratio": "trailing earnings multiple; a loss-making name has none"}
FEATURES = percentile_features(SOURCES, _WHAT, source_inputs={"pe_ratio": "pe_ratio@v1"})
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, p: CohortParams) -> pd.DataFrame:
    return percentile_frame(inputs, session, p, SOURCES, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Percentile ranks of the trailing P/E among the universe's stocks, the instrument's "
    "sector and its industry",
    (
        Input(PE, required=False),
        Input(UNIVERSE, required=False),
        Input(COMPANY, required=False),
    ),
    FEATURES,
    compute,
    CohortParams(),
)
