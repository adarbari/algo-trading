"""The option-structure engine is deterministic and order-free (CLAUDE.md rule 7): marking the
same window twice gives the same marks, and the marks of a name do not depend on which other names
are in the window or where they sit."""

from datetime import date

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.engines.structures.chain import DayChain
from algotrade.engines.structures.marking import LegColumn, Window, mark_window
from algotrade.quant.black_scholes import price

DAYS = (date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7))
EXPIRY = date(2026, 11, 6)
NAMES = [f"EQ:{c}" for c in "ABCD"]


def _chain(day: int, spots: dict[str, float]) -> DayChain:
    rows = []
    for name, spot in spots.items():
        for strike in (95.0, 100.0):
            mid = float(price(spot, strike, (EXPIRY - DAYS[day]).days / 365, 0.0, 0.0, 0.3, False))
            rows.append({"instrument_id": f"{name}:P{int(strike)}", "underlying_id": name,
                         "expiry": EXPIRY, "right": "P", "strike": strike,
                         "bid": max(mid - 0.05, 0.0), "ask": mid + 0.05})  # fmt: skip
    return DayChain(DAYS[day], pd.DataFrame(rows), spots, dict.fromkeys(spots, "OK"), None)


def _window(names: list[str]) -> Window:
    n = len(names)
    legs = [
        LegColumn("P", qty, pd.Series([f"{x}:P{int(k)}" for x in names]), np.full(n, k),
                  pd.Series([EXPIRY] * n))
        for qty, k in ((-1.0, 100.0), (1.0, 95.0))
    ]  # fmt: skip
    return Window(pd.Series(names), legs, np.ones(n, bool), np.full(n, None, object),
                  np.full(n, None, object))  # fmt: skip


def _marks(names: list[str], paths: dict[str, tuple[float, float, float]]):
    days = [_chain(i, {n: paths[n][i] for n in names}) for i in range(3)]
    return mark_window(days, _window(names))


path = st.tuples(*(st.floats(60.0, 140.0) for _ in range(3)))


@settings(max_examples=60, deadline=None)
@given(st.fixed_dictionaries(dict.fromkeys(NAMES, path)), st.permutations(NAMES))
def test_marks_are_deterministic_and_independent_of_the_other_names_and_their_order(
    paths: dict[str, tuple[float, float, float]], order: list[str]
) -> None:
    full, again = _marks(NAMES, paths), _marks(NAMES, paths)
    for a, b in ((full.entry_mid, again.entry_mid), (full.exit_mid, again.exit_mid),
                 (full.exit_exec, again.exit_exec)):  # fmt: skip
        np.testing.assert_array_equal(a, b)
    shuffled = _marks(order, paths)
    for i, name in enumerate(order):
        j = NAMES.index(name)
        np.testing.assert_allclose(shuffled.entry_mid[i], full.entry_mid[j], equal_nan=True)
        np.testing.assert_allclose(shuffled.exit_mid[i], full.exit_mid[j], equal_nan=True)
        np.testing.assert_allclose(shuffled.deltas[0][i], full.deltas[0][j], equal_nan=True)
    alone = _marks([order[0]], paths)
    j = NAMES.index(order[0])
    np.testing.assert_allclose(alone.exit_exec[0], full.exit_exec[j], equal_nan=True)
