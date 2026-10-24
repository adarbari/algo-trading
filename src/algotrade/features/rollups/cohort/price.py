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

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.cohort.members import (
    COMPANY,
    INDUSTRY,
    LEVELS,
    MEMBERS,
    SECTOR,
    UNIVERSE,
    CohortParams,
    cohorts,
    member_ids,
)
from algotrade.quant.cross_section import cohort_percentile

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
    "adv_usd_20d": "20-session dollar volume",
    "rs_spy_63d": "63-session relative strength against SPY",
}
_COHORT = {
    "universe": "the universe's stocks",
    "sector": "the stocks of the instrument's sector",
    "industry": "the stocks of the instrument's industry",
}
_INPUTS = {"universe": (MEMBERS,), "sector": (MEMBERS, SECTOR), "industry": (MEMBERS, INDUSTRY)}


def _source(table: str, column: str) -> str:
    """``price_stats.adv_usd_20d@v2`` for ``rollups/instrument/price_stats@v2``."""
    group, version = table.rsplit("/", maxsplit=1)[-1].split("@")
    return f"{group}.{column}@v{version.lstrip('v')}"


def _null(table: str, column: str, level: str) -> str:
    return (
        "the instrument is not a STOCK of the universe snapshot the session sees (an ETF, fund "
        "or trust, or no snapshot yet)"
        + ("" if level == "universe" else f", or its company snapshot has no {level}")
        + f", its {column} is null or missing, fewer than "
        f"min_members_{level} stocks of its cohort have a known one, or fewer than min_coverage "
        "of the universe's stocks have a source row (a partial day)"
    )


FEATURES = tuple(
    Feature(
        f"{column}_pct_{level}", "float32", "decimal",
        f"The percentile rank of {column} ({_WHAT[column]}) among {_COHORT[level]} with a known "
        f"one: 0 the lowest, 1 the highest, ties share one rank; 0.9 is above 90% of "
        "the cohort",
        _null(table, column, level),
        kind="cross_section", valid_range=(0, 1),
        inputs=(_source(table, column), *_INPUTS[level]),
    )
    for table, column, levels in SOURCES
    for level in LEVELS
    if level in levels
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _today(inputs: Inputs, table: str, session: date) -> pd.DataFrame | None:
    frame = inputs.get(table)
    if frame is None:
        return None
    return frame[frame["session_date"] == session]


def compute(inputs: Inputs, session: date, p: CohortParams) -> pd.DataFrame:
    today = {t: _today(inputs, t, session) for t, _, _ in SOURCES}
    ids = sorted({str(i) for f in today.values() if f is not None for i in f["instrument_id"]})
    out = pd.DataFrame({"instrument_id": ids})
    members = member_ids(inputs)
    stats = today[STATS]
    have = set(stats["instrument_id"].astype(str)) if stats is not None else set()
    covered = bool(members) and len(members & have) / len(members) >= p.min_coverage
    codes = cohorts(inputs, ids)
    for table, column, levels in SOURCES:
        frame = today[table]
        values = (
            pd.Series(frame[column].to_numpy(dtype=float), index=frame["instrument_id"].astype(str))
            .groupby(level=0)
            .last()
            .reindex(ids)
            .to_numpy()
            if frame is not None and len(frame)
            else np.full(len(ids), np.nan)
        )
        for level in levels:
            out[f"{column}_pct_{level}"] = (
                cohort_percentile(values, codes[level], p.minimum(level))
                if covered
                else np.full(len(ids), np.nan)
            )
    return out[["instrument_id", *COLUMNS]]


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
