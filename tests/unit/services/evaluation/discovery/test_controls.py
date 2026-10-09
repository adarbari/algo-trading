"""``controls``: five matched controls per winner from the winner's own cell, seeded and
independent of row order."""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.services.evaluation.discovery.controls import assign_cells, draw_controls
from tests.unit.services.evaluation.discovery.conftest import settings

S = date(2014, 3, 3)


def names(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "instrument_id": [f"EQ:{i:04d}" for i in range(n)],
            "adv": rng.uniform(1e6, 1e9, n),
            "age_years": rng.uniform(0.0, 12.0, n),
        }
    )


def winners_of(eligible: pd.DataFrame, k: int = 6) -> list[str]:
    return sorted(eligible["instrument_id"].iloc[::50][:k])


def test_controls_seeded_order_invariant() -> None:
    """The same eligible names and winners give the same controls whatever order the rows and
    winners arrive in, the seed is recorded, and another session or seed draws differently.
    Catches: a draw that depends on dataframe order or on an unseeded generator."""
    s = settings()
    eligible = names()
    winners = winners_of(eligible)
    first = draw_controls(assign_cells(eligible, s), winners, S, s)
    shuffled = eligible.sample(frac=1.0, random_state=3)
    again = draw_controls(assign_cells(shuffled, s), list(reversed(winners)), S, s)
    assert first.ids == again.ids and first.seed == (s.seed, S.toordinal())
    other_day = draw_controls(assign_cells(eligible, s), winners, date(2014, 3, 4), s)
    other_seed = draw_controls(
        assign_cells(eligible, settings(seed=1)), winners, S, settings(seed=1)
    )
    assert first.ids not in (other_day.ids, other_seed.ids)


def test_controls_same_cell_never_winners() -> None:
    """Every control shares a cell with a winner, no control is a winner, none repeats, and each
    cell yields ``controls_per_winner`` per winner in it. Catches: a control from another
    liquidity or age cell, a winner drawn as its own control, a name used twice."""
    s = settings()
    eligible = names()
    cells = assign_cells(eligible, s)
    winners = winners_of(eligible)
    got = draw_controls(cells, winners, S, s)
    assert got.wanted == 5 * len(winners) == len(got.ids) == len(set(got.ids))
    assert not set(got.ids) & set(winners)
    winner_cells = cells[winners]
    for cell in set(cells[list(got.ids)]):
        n_winners = int((winner_cells == cell).sum())
        assert n_winners and int((cells[list(got.ids)] == cell).sum()) == 5 * n_winners


def test_cells_are_liquidity_quantile_by_listing_age() -> None:
    """Five liquidity quantiles by dollar volume rank crossed with the age buckets (< 2, 2 to 5,
    5+ years). Catches: age edges read as the wrong side, or quantiles by value not rank."""
    s = settings()
    eligible = pd.DataFrame(
        {
            "instrument_id": [f"EQ:{i}" for i in range(10)],
            "adv": [float(10**6 * (i + 1) ** 3) for i in range(10)],  # skewed: rank not value
            "age_years": [1.9, 2.0, 4.99, 5.0, 30.0] * 2,
        }
    )
    cells = assign_cells(eligible, s)
    assert [cells[f"EQ:{i}"][:2] for i in range(10)] == [f"L{i // 2}" for i in range(10)]
    assert [cells[f"EQ:{i}"][2:] for i in range(5)] == ["A0", "A1", "A1", "A2", "A2"]


def test_a_cell_short_of_names_gives_all_it_has() -> None:
    """A winner alone in a thin cell gets the few names there are, no filling from other cells;
    the shortfall shows as drawn < wanted. Catches: padding from another cell, or an error."""
    s = settings(liquidity_quantiles=2)
    eligible = pd.DataFrame(
        {
            "instrument_id": [f"EQ:{i}" for i in range(6)],
            "adv": [1e6, 2e6, 3e6, 4e6, 5e6, 6e6],
            "age_years": [10.0] * 6,
        }
    )
    got = draw_controls(assign_cells(eligible, s), ["EQ:5"], S, s)
    assert got.ids == ("EQ:3", "EQ:4") and got.wanted == 5
