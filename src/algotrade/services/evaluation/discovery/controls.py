"""The matched controls of one grid session (ED6 winners study, definition 2).

Each winner gets ``controls_per_winner`` controls from the **same cell** at S: the liquidity
quantile of ``adv_usd_20d`` among the eligible names at S, crossed with the quantile of the
60-session volatility (``hv``, read from the partition of S: the first run's tells were mostly
variance, so volatility is matched, never a tell) and the listing age bucket (years from the
listing's start date, cut at ``listing_age_edges_years``). Not sector (company
snapshots start in 2026: a lookahead for history) and not prior return (a candidate tell). Only
eligible names at S are drawn, never a winner, each at most once. The draw is seeded by
``[seed, S.toordinal()]`` over ids sorted ascending, cells in sorted order, so the same inputs give
the same controls whatever the order the rows arrive in. A cell with fewer names than wanted gives
all it has (never filled from another cell), and a session whose controls fall short of the wanted
count by more than ``max_control_shortfall`` is refused (``MissingDataError``, ADR 0008): winners
without their matches are not a comparison.
"""

from bisect import bisect_right
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.config.edges.winners import WinnersStudySettings
from algotrade.core.model.errors import MissingDataError


@dataclass(frozen=True)
class Controls:
    """``ids``: the controls drawn, ascending; ``wanted``: per-winner count times winners;
    ``seed``: the generator's seed sequence, recorded with the run."""

    ids: tuple[str, ...]
    wanted: int
    seed: tuple[int, int]


def assign_cells(eligible: pd.DataFrame, settings: WinnersStudySettings) -> pd.Series:
    """Each eligible name's cell, ``L<q>V<v>A<age bucket>``, indexed by ``instrument_id``.
    ``eligible``: ``instrument_id``, ``adv``, ``hv``, ``age_years``. A quantile is the name's rank
    by (value, id) over the eligible names, split in near-equal runs (``liquidity_quantiles``,
    ``volatility_quantiles``)."""
    ids = eligible["instrument_id"].astype(str).to_numpy()
    liquidity = _quantile(eligible["adv"], ids, settings.liquidity_quantiles)
    volatility = _quantile(eligible["hv"], ids, settings.volatility_quantiles)
    edges = list(settings.listing_age_edges_years)
    age = [bisect_right(edges, float(a)) for a in eligible["age_years"]]
    cells = [f"L{q}V{v}A{a}" for q, v, a in zip(liquidity, volatility, age, strict=True)]
    return pd.Series(cells, index=ids, name="cell").sort_index()


def _quantile(values: pd.Series, ids: np.ndarray, parts: int) -> np.ndarray:
    """Each row's quantile (0-based) by rank of (value, id), in the order of the input rows."""
    order = pd.DataFrame({"v": values.to_numpy(dtype=float), "id": ids}).reset_index()
    ranked = order.sort_values(["v", "id"], kind="stable").reset_index(drop=True)
    out = np.empty(len(ranked), dtype=int)
    out[ranked["index"].to_numpy()] = (np.arange(len(ranked)) * parts) // max(len(ranked), 1)
    return out


def draw_controls(
    cells: pd.Series,
    winners: Collection[str],
    session: date,
    settings: WinnersStudySettings,
    among: Collection[str] | None = None,
) -> Controls:
    """The controls for ``winners`` among the names of ``cells`` (``assign_cells``), only those in
    ``among`` when given (the names with a COMPLETE or DELISTED outcome: a name with no outcome
    row cannot be shown not to have won). Exclude the losers from ``among``: a control is neither a
    winner nor a loser. ``MissingDataError`` when more than ``max_control_shortfall`` of the
    wanted controls could not be drawn."""
    won = set(winners)
    if among is not None:
        cells = cells[cells.index.isin(set(among) | won)]
    seed = (settings.seed, session.toordinal())
    rng = np.random.default_rng(list(seed))
    wanted = settings.controls_per_winner * len(won)
    drawn: list[str] = []
    by_cell = cells.sort_index()
    for cell in sorted(set(by_cell[by_cell.index.isin(won)])):
        members = by_cell[by_cell == cell]
        need = settings.controls_per_winner * int(members.index.isin(won).sum())
        pool = sorted(i for i in members.index if i not in won)
        take = min(need, len(pool))
        if take:
            drawn.extend(pool[int(k)] for k in rng.choice(len(pool), size=take, replace=False))
    if wanted and 1.0 - len(drawn) / wanted > settings.max_control_shortfall:
        raise MissingDataError(
            "winners_study controls",
            f"{len(drawn)} of the {wanted} controls wanted on {session} could be drawn "
            f"(at most {settings.max_control_shortfall:.0%} may be missing)",
            "widen the eligible set or lower liquidity_quantiles / volatility_quantiles",
        )
    return Controls(tuple(sorted(drawn)), wanted, seed)
