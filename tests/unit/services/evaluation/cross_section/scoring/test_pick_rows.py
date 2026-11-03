"""The null and finite coercions of a stored cell, and the measuring's re-export of pick rows."""

import math

import pandas as pd

from algotrade.services.evaluation.cross_section import measuring
from algotrade.services.evaluation.cross_section.scoring import pick_rows


def test_finite_drops_none_nan_and_inf() -> None:
    assert pick_rows._finite(None) is None
    assert pick_rows._finite(math.nan) is None
    assert pick_rows._finite(math.inf) is None
    assert pick_rows._finite(1.5) == 1.5


def test_none_if_null_keeps_values() -> None:
    assert pick_rows._none_if_null(pd.NA) is None
    assert pick_rows._none_if_null("x") == "x"


def test_measuring_still_exposes_the_split_names() -> None:
    assert measuring._picks is pick_rows._picks
    assert measuring.NO_ENTRY_BAR == pick_rows.NO_ENTRY_BAR
