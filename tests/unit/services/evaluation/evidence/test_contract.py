"""The trade contract's columns, enums and validator (ADR 0088, 2.5a)."""

import numpy as np
import pandas as pd

from algotrade.services.evaluation.evidence.contract import (
    COLUMN_NAMES,
    FIGURES,
    TRADE_COLUMNS,
    empty_trades,
    trade_problems,
)


def test_the_columns_are_the_frozen_set_in_order() -> None:
    assert (
        COLUMN_NAMES[:3] == ("instrument_id", "side", "entry_session") and len(TRADE_COLUMNS) == 18
    )
    assert FIGURES == (
        "capital", "return_on_capital_gross", "return_on_capital", "max_adverse",
        "underlying_return",
    )  # fmt: skip


def test_an_empty_frame_is_valid() -> None:
    assert trade_problems(empty_trades()) == []


def test_the_validator_names_what_is_wrong() -> None:
    assert trade_problems(pd.DataFrame({"x": [1]}))[0].startswith("columns")
    frame = empty_trades()
    frame.loc[0] = [
        "EQ:A", "sideways", None, None, None, 0.1, True, True, "missing_value", False, "weird",
        0.5, 0.1, 0.1, 0.1, 0.1, "nowhere", "open",
    ]  # fmt: skip
    problems = trade_problems(frame)
    assert "entry_session is null" in problems
    assert "side has ['sideways']" in problems and "capital_basis has ['weird']" in problems
    assert "price_source has ['nowhere']" in problems
    assert "capital is set on an excluded row" in problems
    frame.loc[0, "return_on_capital"] = np.inf
    assert "return_on_capital is not finite" in trade_problems(frame)
