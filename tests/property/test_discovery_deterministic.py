"""The winners discovery is deterministic (CLAUDE.md rule 7): the same frames and settings give
the same result, byte for byte, and the controls the same draw, whatever the seed."""

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.services.evaluation.discovery.controls import assign_cells, draw_controls
from algotrade.services.evaluation.discovery.tells import find_tells
from tests.unit.services.evaluation.discovery.conftest import session_frame_of
from tests.unit.services.evaluation.discovery.conftest import settings as study

DAYS = [date(2012, 3, 1), date(2012, 3, 2), date(2019, 3, 1), date(2019, 3, 4)]
BLOCKS = [0, 0, 1, 1]


@settings(max_examples=10, deadline=None)
@given(seed=st.integers(0, 2**31 - 1), shift=st.floats(0.0, 2.0))
def test_the_same_frames_give_the_same_result(seed: int, shift: float) -> None:
    """Catches: any unseeded randomness (the permutation null, the shuffle, the clusters' order)
    in the discovery."""
    s = replace(study(permutations=4, stable_blocks=2, min_clusters=1), seed=seed)

    def frames() -> list:  # type: ignore[type-arg]
        rng = np.random.default_rng(seed % 1000)
        out = []
        for day, block in zip(DAYS, BLOCKS, strict=True):
            a = rng.normal(size=40)
            a[:10] += shift
            out.append(session_frame_of(day, block, {"a": a, "b": a * 2, "c": rng.normal(size=40)}))
        return out

    assert find_tells(frames(), s) == find_tells(frames(), s)


@settings(max_examples=25, deadline=None)
@given(seed=st.integers(0, 2**31 - 1), day=st.integers(0, 4000))
def test_the_controls_are_a_function_of_the_seed_and_the_session(seed: int, day: int) -> None:
    """Catches: a control draw that depends on process state."""
    s = replace(study(), seed=seed)
    rng = np.random.default_rng(1)
    eligible = pd.DataFrame(
        {
            "instrument_id": [f"EQ:{i:03d}" for i in range(120)],
            "adv": rng.uniform(1e6, 1e8, 120),
            "age_years": rng.uniform(0, 10, 120),
        }
    )
    session = date.fromordinal(735000 + day)
    winners = ["EQ:000", "EQ:050", "EQ:100"]
    cells = assign_cells(eligible, s)
    assert draw_controls(cells, winners, session, s) == draw_controls(cells, winners, session, s)
