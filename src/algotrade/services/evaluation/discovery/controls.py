"""The matched controls of one grid session (ED6 winners study, definition 2).

Each winner gets ``controls_per_winner`` controls from the **same cell** at S: the liquidity
quantile of ``adv_usd_20d`` among the eligible names at S, crossed with the listing age bucket
(years from the listing's start date, cut at ``listing_age_edges_years``). Not sector (company
snapshots start in 2026: a lookahead for history) and not prior return (a candidate tell). Only
eligible names at S are drawn, never a winner, each at most once. The draw is seeded by
``[seed, S.toordinal()]`` over ids sorted ascending, cells in sorted order, so the same inputs give
the same controls whatever the order the rows arrive in. A cell with fewer names than wanted gives
all it has (the shortfall is counted in ``Controls``, not filled from another cell).
"""

from bisect import bisect_right
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.config.edges.winners import WinnersStudySettings


@dataclass(frozen=True)
class Controls:
    """``ids``: the controls drawn, ascending; ``wanted``: per-winner count times winners;
    ``seed``: the generator's seed sequence, recorded with the run."""

    ids: tuple[str, ...]
    wanted: int
    seed: tuple[int, int]


def assign_cells(eligible: pd.DataFrame, settings: WinnersStudySettings) -> pd.Series:
    """Each eligible name's cell, ``L<quantile>A<age bucket>``, indexed by ``instrument_id``.
    ``eligible``: ``instrument_id``, ``adv``, ``age_years``. The quantile is the name's rank by
    (adv, id) over the eligible names, split in ``liquidity_quantiles`` near-equal runs."""
    ordered = eligible.sort_values(["adv", "instrument_id"], kind="stable").reset_index(drop=True)
    n = len(ordered)
    quantile = (np.arange(n) * settings.liquidity_quantiles) // max(n, 1)
    edges = list(settings.listing_age_edges_years)
    age = [bisect_right(edges, float(a)) for a in ordered["age_years"]]
    cells = [f"L{q}A{a}" for q, a in zip(quantile, age, strict=True)]
    return pd.Series(cells, index=ordered["instrument_id"].astype(str).to_numpy(), name="cell")


def draw_controls(
    cells: pd.Series,
    winners: Collection[str],
    session: date,
    settings: WinnersStudySettings,
) -> Controls:
    """The controls for ``winners`` among the names of ``cells`` (``assign_cells``)."""
    won = set(winners)
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
    return Controls(tuple(sorted(drawn)), wanted, seed)
