"""``cohort_pct_price@v1``: the percentile rank of price-derived features among the universe's
stocks, the instrument's sector and its industry (ADR 0023; ``members.py`` for the cohorts).

Inputs (each optional: a missing source makes its columns null): ``trend_stats@v2``
(``mom_12_1``), ``price_stats@v2`` (``adv_usd_20d``), ``relative_strength@v1``
(``rs_spy_63d``: sector and industry only, it is already measured against the market),
``universe`` and ``instruments/company``. One row per instrument with a row of a source on the
session. A percentile is the average rank among the cohort's known values, 0 the lowest and
1 the highest (``quant.cross_section``); below ``min_coverage`` of the universe's stocks with a
``price_stats`` row (a partial day) every column is null, as in ``relative_strength@v1``.

Parameters: ``CohortParams`` (``config/site/rollups.toml`` ``["cohort_pct_price@v1"]``).
"""

from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.rollups.cohort.members import (
    COMPANY,
    LEVELS,
    UNIVERSE,
    CohortParams,
    member_ids,
    percentile_features,
    percentile_frame,
)

NAME = "cohort_pct_price"
VERSION = 1
TREND = "rollups/instrument/trend_stats@v2"
STATS = "rollups/instrument/price_stats@v2"
RELATIVE = "rollups/instrument/relative_strength@v1"
# (table, source column, the levels it is ranked at)
SOURCES = (
    (TREND, "mom_12_1", LEVELS),
    (STATS, "adv_usd_20d", LEVELS),
    (RELATIVE, "rs_spy_63d", ("sector", "industry")),
)
_WHAT = {
    "mom_12_1": "12-1 momentum (the 12-month return without the last month)",
    "adv_usd_20d": "20-session average dollar volume",
    "rs_spy_63d": "63-session relative strength against SPY",
}
_COVERAGE = (
    ", or fewer than min_coverage of the universe's stocks have a price_stats row (a partial day)"
)

FEATURES = percentile_features(SOURCES, _WHAT, _COVERAGE)
COLUMNS = column_types(FEATURES)


def _covered(inputs: Inputs, today: dict[str, pd.DataFrame | None], p: CohortParams) -> bool:
    """At least ``min_coverage`` of the universe's stocks have a price_stats row."""
    members = member_ids(inputs)
    stats = today[STATS]
    have = set(stats["instrument_id"].astype(str)) if stats is not None else set()
    return bool(members) and len(members & have) / len(members) >= p.min_coverage


def compute(inputs: Inputs, session: date, p: CohortParams) -> pd.DataFrame:
    return percentile_frame(inputs, session, p, SOURCES, COLUMNS, _covered)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Percentile ranks of 12-1 momentum and 20-session dollar volume among the universe's "
    "stocks, the instrument's sector and its industry, and of 63-session relative strength "
    "against SPY within sector and industry",
    (
        Input(TREND, required=False),
        Input(STATS, required=False),
        Input(RELATIVE, required=False),
        Input(UNIVERSE, required=False),
        Input(COMPANY, required=False),
    ),
    FEATURES,
    compute,
    CohortParams(),
)
