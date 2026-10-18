"""``features/framework/columns.py``: ``conform`` types a frame to its declared columns. Fix
for: the expression catalogue passed 100 columns and the one-by-one inserts raised pandas'
PerformanceWarning (an error under pyproject's ``filterwarnings = error``)."""

import warnings

import pandas as pd
import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade.features.framework.columns import conform


def test_conform_of_a_hundred_and_twenty_columns_raises_no_warning_and_keeps_order_and_types() -> (
    None
):
    names = [f"c{i}" for i in range(120)]
    kinds = {n: ("float" if i % 2 else "int") for i, n in enumerate(names)}
    frame = pd.DataFrame({"instrument_id": ["EQ:A", "EQ:B"], **{n: [1, 2] for n in names}})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = conform("t", frame, kinds)
        out = pd.concat([pd.DataFrame({"session_date": [None, None]}), out], axis=1)
    assert list(out.columns) == ["session_date", "instrument_id", *names]
    assert isinstance(out.index, pd.RangeIndex)
    assert list(out["c0"]) == [1, 2] and list(out["c1"]) == [1.0, 2.0]
    assert out["c0"].dtype != out["c1"].dtype  # each column keeps its declared type


def test_conform_still_names_a_column_that_does_not_fit() -> None:
    frame = pd.DataFrame({"instrument_id": ["EQ:A"], "x": ["not a number"]})
    with pytest.raises(DataValidationError, match="x"):
        conform("t", frame, {"x": "float"})
