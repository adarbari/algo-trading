"""``controls``: five matched controls per winner from the winner's own cell, seeded and
independent of row order."""

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.services.evaluation.discovery.controls import assign_cells, draw_controls
from algotrade.services.evaluation.discovery.grid import pick_eligible
from tests.unit.services.evaluation.discovery.conftest import settings

S = date(2014, 3, 3)


def names(n: int = 3000) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "instrument_id": [f"EQ:{i:04d}" for i in range(n)],
            "adv": rng.uniform(1e6, 1e9, n),
            "hv": rng.uniform(0.1, 1.5, n),
            "age_years": rng.uniform(0.0, 12.0, n),
        }
    )


def winners_of(eligible: pd.DataFrame, k: int = 6) -> list[str]:
    return sorted(eligible["instrument_id"].iloc[::500][:k])


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


def test_cells_include_volatility_bucket() -> None:
    """A cell is liquidity quantile by volatility quantile by age bucket (< 2, 2 to 5, 5+ years),
    each quantile by rank (a skewed value spread still fills them evenly). Catches: controls not
    matched on volatility (the first run's tells were mostly variance), age edges read as the wrong
    side, or quantiles by value not rank."""
    s = settings(liquidity_quantiles=2, volatility_quantiles=5)
    eligible = pd.DataFrame(
        {
            "instrument_id": [f"EQ:{i:02d}" for i in range(10)],
            "adv": [float(10**6 * (i + 1) ** 3) for i in range(10)],  # skewed: rank not value
            "hv": [float(10 - i) ** 3 for i in range(10)],  # falls as the id rises
            "age_years": [1.9, 2.0, 4.99, 5.0, 30.0] * 2,
        }
    )
    cells = assign_cells(eligible, s)
    assert [cells[f"EQ:{i:02d}"][:2] for i in range(10)] == [f"L{i // 5}" for i in range(10)]
    assert [cells[f"EQ:{i:02d}"][2:4] for i in range(10)] == [f"V{4 - i // 2}" for i in range(10)]
    assert [cells[f"EQ:{i:02d}"][4:] for i in range(5)] == ["A0", "A1", "A1", "A2", "A2"]
    same_but_hv = eligible.assign(hv=[0.3 + i for i in range(10)])
    assert not cells.equals(assign_cells(same_but_hv, s))


def test_a_cell_short_of_names_gives_all_it_has() -> None:
    """A winner alone in a thin cell gets the few names there are, no filling from other cells;
    the shortfall shows as drawn < wanted. Catches: padding from another cell, or an error."""
    s = settings(liquidity_quantiles=2, volatility_quantiles=2, max_control_shortfall=1.0)
    eligible = pd.DataFrame(
        {
            "instrument_id": [f"EQ:{i}" for i in range(6)],
            "adv": [1e6, 2e6, 3e6, 4e6, 5e6, 6e6],
            "hv": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            "age_years": [10.0] * 6,
        }
    )
    got = draw_controls(assign_cells(eligible, s), ["EQ:5"], S, s)
    assert got.ids == ("EQ:3", "EQ:4") and got.wanted == 5


def test_controls_are_drawn_only_from_names_with_an_outcome() -> None:
    """A name with no COMPLETE or DELISTED row cannot be shown not to have won, so it is never a
    control. Catches: drawing from every eligible name."""
    s = settings()
    eligible = names()
    cells = assign_cells(eligible, s)
    winners = winners_of(eligible)
    measured = set(eligible["instrument_id"].iloc[:250])
    got = draw_controls(cells, winners, S, s, measured)
    assert set(got.ids) <= measured and got.ids
    assert got.ids != draw_controls(cells, winners, S, s).ids


def test_unknown_volatility_not_eligible() -> None:
    """A name at the price and dollar-volume floors with no volatility (NaN) is not eligible, is
    not in any cell and is counted, never given a middle bucket. Catches: an UNKNOWN volatility
    imputed or sorted into a cell, which would pair winners with controls of unknown risk."""
    s = settings()
    day = date(2015, 6, 1)
    listings = pd.DataFrame(
        {
            "instrument_id": ["A", "B", "C"],
            "asset_type": "Stock",
            "start_date": [date(2005, 6, 1)] * 3,
        }
    )
    prices = pd.DataFrame(
        {
            "instrument_id": ["A", "B", "C"],
            "close": [20.0, 20.0, 2.0],
            "adv": [9e6, 9e6, 9e6],
            "hv": [0.3, None, None],  # C is also under the price floor: not counted as unknown
        }
    )
    got = pick_eligible(listings, prices, day, s)
    assert got.names["instrument_id"].tolist() == ["A"] and got.unknown_volatility == 1
    assert list(assign_cells(got.names, s).index) == ["A"]


def test_shortfall_raises() -> None:
    """A session whose controls fall short of the wanted count by more than
    ``max_control_shortfall`` is refused (naming the session), one inside it is drawn. Catches:
    winners compared with a thin remainder of their cell, silently."""
    s = settings(liquidity_quantiles=2, volatility_quantiles=2, max_control_shortfall=0.25)
    eligible = pd.DataFrame(
        {
            "instrument_id": [f"EQ:{i}" for i in range(8)],
            "adv": [float(i + 1) * 1e6 for i in range(8)],
            "hv": [0.1] * 8,
            "age_years": [10.0] * 8,
        }
    )
    cells = assign_cells(eligible, s)
    with pytest.raises(MissingDataError, match="2014-03-03"):
        draw_controls(cells, ["EQ:7"], S, s)  # 3 names left in the cell for 5 wanted: 40% short
    ok = draw_controls(cells, ["EQ:7"], S, replace(s, max_control_shortfall=0.5))
    assert len(ok.ids) == 3 and ok.wanted == 5
