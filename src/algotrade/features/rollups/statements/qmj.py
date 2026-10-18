"""``qmj@v1``: quality minus junk (Asness, Frazzini and Pedersen 2019) from the stored SEC
statement groups: a profitability score, a safety score and their combination, each a
cross-sectional z-score.

Inputs and point in time as ``mispricing@v1`` (the same statement groups, each already public by
the session's acceptance, ADR 0067 as amended by H2); the raw measures are its ``measures``, so a
ratio means the same here and there. The source's recipe: z(x) is the z-score of x's
cross-sectional rank; profitability is z of the sum of the z of gross profit over assets, ROE,
ROA, cash flow over assets, gross margin and low accruals; safety is z of the sum of the z of low
beta, low leverage, low O-score, low Altman Z and low earnings volatility; quality is z of the
sum of profitability, growth and safety. Built from what is stored:

    profitability_z   the six profitability parts, all of them stored
    safety_z          low debt to equity and low ohlson_o only (no beta, Altman Z or earnings
                      volatility: price based or unstored)
    qmj_score         z(profitability_z + safety_z); the growth part (five-year changes of the
                      profitability measures) is not built

A part that cannot be formed is left out of its mean; too few parts, or a cross-section with fewer
than ``min_members`` known values, is null (UNKNOWN), never zero.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.statements.lines import PRICE_STATS, STATEMENTS
from algotrade.features.rollups.statements.mispricing import (
    BALANCE,
    CASH_FLOW,
    FINANCIALS,
    FUNDAMENTALS,
    INCOME,
    MispricingParams,
    measures,
)

NAME = "qmj"
VERSION = 1
# (raw measure, sign): +1 when high is good, -1 when low is good.
PROFITABILITY = (
    ("gross_profit_to_assets", 1), ("roe", 1), ("roa", 1), ("ocf_to_assets", 1),
    ("gross_margin", 1), ("accruals", -1),
)  # fmt: skip
SAFETY = (("debt_to_equity", -1), ("ohlson_o", -1))


@dataclass(frozen=True)
class QmjParams(MispricingParams):
    """``MispricingParams`` plus how many parts a score needs."""

    min_profitability_inputs: int = 4  # of the six profitability parts
    min_safety_inputs: int = 1  # of the two safety parts

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 1 <= self.min_profitability_inputs <= len(PROFITABILITY):
            raise ValueError(
                f"min_profitability_inputs must be in [1, 6], got {self.min_profitability_inputs}"
            )
        if not 1 <= self.min_safety_inputs <= len(SAFETY):
            raise ValueError(f"min_safety_inputs must be in [1, 2], got {self.min_safety_inputs}")


_STATEMENT = (
    "no balance sheet, income statement, cash flow or net income of the session (ETFs, funds, no "
    "CIK, issuers that report outside USD), or one of them is STALE (its newest period ended "
    "more than stale_days, 480, before the session) or the balance sheet is PARTIAL"
)
_RANKED = (
    "; or fewer than min_members (100) instruments have a known value that session (the "
    "cross-section is too thin to score)"
)
_INPUTS = (
    "balance_sheet.total_assets@v2",
    "balance_sheet.bs_status@v2",
    "financials.net_income_ttm@v3",
    "financials.revenue_ttm@v3",
    "income_statement.gross_profit_ttm@v2",
    "cash_flow.ocf_ttm@v2",
)

FEATURES = (
    Feature(
        "profitability_z", "float32", "ratio",
        "Quality minus junk, profitability: the z-score across the cross-section of the mean "
        "of the z-scores (of the rank, as Asness, Frazzini and Pedersen define z) of gross "
        "profit over assets, ROE, ROA, operating cash flow over assets, gross margin and low "
        "accruals (the mispricing@v1 measures); 0 is the cross-section's middle, 1 one "
        "standard deviation above. A part that cannot be formed is left out of the mean",
        _STATEMENT + "; or fewer than min_profitability_inputs (4) of the six parts can be "
        "formed" + _RANKED,
        valid_range=(None, None), kind="cross_section", inputs=_INPUTS,
    ),
    Feature(
        "safety_z", "float32", "ratio",
        "Quality minus junk, safety, as far as the stored data allows: the z-score across the "
        "cross-section of the mean of the z-scores of low debt to equity and low ohlson_o; 1 "
        "is one standard deviation safer than the middle. OMITS the source's low beta, low "
        "Altman Z and low earnings volatility (beta and volatility are price based, Altman Z "
        "and a five-year earnings history are not stored): it is a leverage and distress "
        "score, not the paper's safety",
        _STATEMENT + "; or neither debt to equity nor ohlson_o can be formed (no total debt "
        "tagged, a negative equity, an O-score input missing, a bank)" + _RANKED,
        valid_range=(None, None), kind="cross_section", inputs=_INPUTS,
    ),
    Feature(
        "qmj_score", "float32", "ratio",
        "Quality minus junk: the z-score across the cross-section of profitability_z plus "
        "safety_z; high is quality, low is junk. OMITS the paper's growth part (five-year "
        "changes of the profitability measures) and its safety parts beyond leverage and "
        "distress (see safety_z); ranks across all instruments, not within a size or industry "
        "bucket",
        "profitability_z or safety_z is null (see each)" + _RANKED,
        valid_range=(None, None), kind="cross_section", inputs=_INPUTS,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def zscore(values: pd.Series, p: QmjParams) -> pd.Series:
    """The z-score of the cross-sectional rank (ties share the average rank); all NaN when
    fewer than ``min_members`` values are known."""
    known = values.notna()
    if known.sum() < max(p.min_members, 3):
        return pd.Series(np.nan, index=values.index, dtype=float)
    rank = values.rank(method="average")
    return (rank - rank.mean()) / rank.std(ddof=0)


def _part_mean(
    raw: pd.DataFrame, parts: tuple[tuple[str, int], ...], need: int, p: QmjParams
) -> pd.Series:
    """The mean z-score of the parts an instrument has (NaN under ``need`` of them)."""
    z = pd.DataFrame({c: zscore(sign * raw[c], p) for c, sign in parts})
    return z.mean(axis=1).where(z.notna().sum(axis=1) >= need)


def compute(inputs: Inputs, session: date, p: QmjParams) -> pd.DataFrame:
    raw = measures(inputs, session, p)
    profitability = zscore(_part_mean(raw, PROFITABILITY, p.min_profitability_inputs, p), p)
    safety = zscore(_part_mean(raw, SAFETY, p.min_safety_inputs, p), p)
    out = pd.DataFrame(index=raw.index)
    out["profitability_z"] = profitability
    out["safety_z"] = safety
    out["qmj_score"] = zscore(profitability + safety, p)
    return out.reset_index()


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Quality minus junk from the stored SEC statement groups: a profitability z-score, a "
    "leverage and distress safety z-score and their combined z-score across the cross-section, "
    "point in time by filing acceptance; parts that cannot be formed are left out and too few "
    "make the score null",
    (
        Input(PRICE_STATS),
        Input(BALANCE, required=False),
        Input(INCOME, required=False),
        Input(CASH_FLOW, required=False),
        Input(FINANCIALS, required=False),
        Input(FUNDAMENTALS, required=False),
        Input(STATEMENTS, required=False),
    ),
    FEATURES,
    compute,
    QmjParams(),
)
