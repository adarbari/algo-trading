"""The cohorts a percentile is ranked in, and their parameters (shared by the cohort groups).

Members are the STOCK rows of the ``universe`` snapshot the session sees (as
``relative_strength@v1`` and ``market_breadth@v1`` count them: common stocks and ADRs; ETFs,
funds and trusts are never members, so their percentiles are null). The sector and industry
of a member are the ``instruments/company`` snapshot on or before the session (``None`` before
the first one: a later snapshot would show facts not known then). A member without a sector
(or industry) has no cohort at that level and keeps its universe percentile. An industry code
is a label over the whole universe, not within a sector: stocks with one industry name rank
together whatever their sector.

``cohorts`` returns, per level, an int code per instrument (-1: no cohort) for
``quant.cross_section.cohort_percentile``; ``percentile_frame`` ranks each source of a group at
the levels it asks for.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import Inputs
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.market.breadth import MEMBER_CLASS
from algotrade.quant.cross_section import cohort_percentile

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


def session_rows(inputs: Inputs, table: str, session: date) -> pd.DataFrame | None:
    """``table``'s rows of the session (None when the source is missing)."""
    frame = inputs.get(table)
    if frame is None:
        return None
    return frame[frame["session_date"] == session]


def source_values(frame: pd.DataFrame | None, column: str, ids: Sequence[str]) -> np.ndarray:
    """``column`` of ``frame`` per id (the last row of a repeated id; NaN when missing)."""
    if frame is None or not len(frame):
        return np.full(len(ids), np.nan)
    series = pd.Series(
        frame[column].to_numpy(dtype=float), index=frame["instrument_id"].astype(str)
    )
    return series.groupby(level=0).last().reindex([str(i) for i in ids]).to_numpy()


def percentile_frame(
    inputs: Inputs,
    session: date,
    p: CohortParams,
    sources: Sequence[tuple[str, str, Sequence[str]]],
    columns: Iterable[str],
    covered: Callable[[Inputs, dict[str, pd.DataFrame | None], CohortParams], bool] | None = None,
) -> pd.DataFrame:
    """One row per instrument with a source row on the session and its ``columns``.

    ``covered`` (given the inputs, the session's rows per source table and the params) says
    whether the session is complete enough to rank; when it says no every column is null."""
    today = {t: session_rows(inputs, t, session) for t, _, _ in sources}
    ids = sorted({str(i) for f in today.values() if f is not None for i in f["instrument_id"]})
    out = pd.DataFrame({"instrument_id": ids})
    codes = cohorts(inputs, ids)
    ok = covered is None or covered(inputs, today, p)
    for table, column, levels in sources:
        values = source_values(today[table], column, ids)
        for level in levels:
            out[f"{column}_pct_{level}"] = (
                cohort_percentile(values, codes[level], p.minimum(level))
                if ok
                else np.full(len(ids), np.nan)
            )
    return out[["instrument_id", *columns]]


_COHORT = {
    "universe": "the universe's stocks",
    "sector": "the stocks of the instrument's sector",
    "industry": "the stocks of the instrument's industry",
}
_INPUTS = {"universe": (MEMBERS,), "sector": (MEMBERS, SECTOR), "industry": (MEMBERS, INDUSTRY)}


def source_key(table: str, column: str) -> str:
    """``price_stats.adv_usd_20d@v2`` for ``rollups/instrument/price_stats@v2``."""
    group, version = table.rsplit("/", maxsplit=1)[-1].split("@")
    return f"{group}.{column}@v{version.lstrip('v')}"


def percentile_features(
    sources: Sequence[tuple[str, str, Sequence[str]]],
    what: dict[str, str],
    extra_null: str = "",
    source_inputs: dict[str, str] | None = None,
) -> tuple[Feature, ...]:
    """The ``<column>_pct_<level>`` features of ``(table, column, levels)`` sources.

    ``what`` says in words what each column is; ``extra_null`` ends the null meaning (a rule
    the group adds, e.g. the price groups' coverage floor); ``source_inputs`` maps a column to
    its lineage key when it is not the ``<group>.<column>@v<N>`` of its table (an expression
    feature stored as ``<name>@v<N>``)."""
    return tuple(
        Feature(
            f"{column}_pct_{level}", "float32", "decimal",
            f"The percentile rank of {column} ({what[column]}) among {_COHORT[level]} with a "
            "known one: 0 the lowest, 1 the highest, ties share one rank; 0.9 is "
            "above 90% of the cohort",
            "the instrument is not a STOCK of the universe snapshot the session sees (an ETF, "
            "fund or trust, or no snapshot yet)"
            + ("" if level == "universe" else f", or its company snapshot has no {level}")
            + f", its {column} is null or missing, or fewer than min_members_{level} stocks of "
            "its cohort have a known one" + extra_null,
            kind="cross_section", valid_range=(0, 1),
            inputs=((source_inputs or {}).get(column) or source_key(table, column),
                    *_INPUTS[level]),
        )
        for table, column, levels in sources
        for level in LEVELS
        if level in levels
    )  # fmt: skip
