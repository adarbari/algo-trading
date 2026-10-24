"""The cohorts a percentile is ranked in, and their parameters (shared by the cohort groups).

Members are the STOCK rows of the ``universe`` snapshot the session sees (as
``relative_strength@v1`` and ``market_breadth@v1`` count them: common stocks and ADRs; ETFs,
funds and trusts are never members, so their percentiles are null). The sector and industry
of a member are the ``instruments/company`` snapshot on or before the session (``None`` before
the first one: a later snapshot would show facts not known then). A member without a sector
(or industry) has no cohort at that level and keeps its universe percentile.

``cohorts`` returns, per level, an int code per instrument (-1: no cohort) for
``quant.cross_section.cohort_percentile``.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import Inputs
from algotrade.features.rollups.market.breadth import MEMBER_CLASS

UNIVERSE = "universe"
COMPANY = "instruments/company"
LEVELS = ("universe", "sector", "industry")
MEMBERS = f"{UNIVERSE}.instrument_id"
SECTOR = f"{COMPANY}.sector"
INDUSTRY = f"{COMPANY}.industry"


@dataclass(frozen=True)
class CohortParams:
    min_members_universe: int = 200  # known values a universe percentile needs
    min_members_sector: int = 20  # known values a sector percentile needs
    min_members_industry: int = 10  # known values an industry percentile needs
    min_coverage: float = 0.9  # share of member stocks with a source row (price groups only)

    def __post_init__(self) -> None:
        if not 0 <= self.min_coverage <= 1:
            raise ValueError(f"min_coverage must be in [0, 1], got {self.min_coverage}")
        for level in LEVELS:
            if self.minimum(level) < 2:
                raise ValueError(f"min_members_{level} must be >= 2, got {self.minimum(level)}")

    def minimum(self, level: str) -> int:
        return int(getattr(self, f"min_members_{level}"))


def member_ids(inputs: Inputs) -> set[str]:
    """The STOCK instruments of the universe snapshot the session sees (none without one)."""
    universe = inputs.get(UNIVERSE)
    if universe is None:
        return set()
    stocks = universe.loc[universe["asset_class"] == MEMBER_CLASS, "instrument_id"]
    return set(stocks.astype(str))


def _codes(labels: pd.Series) -> np.ndarray:
    """An int code per distinct non-empty string label; -1 for anything else."""
    text = labels.where(labels.map(lambda v: isinstance(v, str) and bool(v.strip())))
    return pd.factorize(text)[0].astype(int)


def cohorts(inputs: Inputs, ids: Sequence[str]) -> dict[str, np.ndarray]:
    """``{level: codes}`` for ``ids``: non-members and members without that level's label
    get -1."""
    index = pd.Index([str(i) for i in ids])
    is_member = index.isin(list(member_ids(inputs))).astype(bool)
    out = {"universe": np.where(is_member, 0, -1).astype(int)}
    company = inputs.get(COMPANY)
    for level in ("sector", "industry"):
        codes = np.full(len(index), -1, dtype=int)
        if company is not None and level in company.columns and len(index):
            named = company.drop_duplicates("instrument_id", keep="last")
            labels = pd.Series(
                named[level].to_numpy(), index=named["instrument_id"].astype(str)
            ).reindex(index)
            codes = _codes(labels.reset_index(drop=True))
        out[level] = np.where(is_member, codes, -1).astype(int)
    return out
