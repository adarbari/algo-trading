"""Evaluation: vectorised values with nulls (null propagates, Kleene and / or, division by
zero and invalid logs are null), every built-in, and conversion from stored columns."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.features.expressions.evaluator import evaluate_formula, from_column, to_column
from algotrade.features.expressions.functions import NULL, NUM, Type, full, null_mask, unify
from algotrade.features.expressions.parser import parse_formula

NAN = np.nan
DAYS = pd.to_datetime(["2026-01-02", None, "2026-01-01", "2026-01-05", "2026-01-02"]).to_numpy(
    dtype="datetime64[ns]"
)
COLUMNS: dict[str, tuple[np.ndarray, str]] = {
    "g.x": (np.array([1.0, 2.0, NAN, 4.0, -1.0]), "num"),
    "g.y": (np.array([0.0, 1.0, 1.0, 2.0, 3.0]), "num"),
    "g.ok": (np.array([1.0, 0.0, NAN, 1.0, 0.0]), "bool"),
    "g.no": (np.array([NAN, NAN, 0.0, 1.0, 1.0]), "bool"),
    "g.tier": (np.array(["A", None, "C", "D", "B"], dtype=object), "str"),
    "g.day": (DAYS, "date"),
    "exists:g": (np.array([1.0, 0.0, NAN, 1.0, 1.0]), "bool"),
}


def run(text: str) -> list[object]:
    values, kind = evaluate_formula(parse_formula(text, "w"), COLUMNS.__getitem__, 5)
    if kind in ("num", "bool"):
        return [None if np.isnan(v) else float(v) for v in values]
    return [None if (v is None or (kind == "date" and np.isnat(v))) else v for v in values]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("g.x + g.y", [1.0, 3.0, None, 6.0, 2.0]),
        ("g.x - 1", [0.0, 1.0, None, 3.0, -2.0]),
        ("g.x * 2", [2.0, 4.0, None, 8.0, -2.0]),
        ("g.x / g.y", [None, 2.0, None, 2.0, -1 / 3]),  # x / 0 is null
        ("-g.x", [-1.0, -2.0, None, -4.0, 1.0]),
        ("g.x > 1", [0.0, 1.0, None, 1.0, 0.0]),
        ("g.x == 2", [0.0, 1.0, None, 0.0, 0.0]),
        ("g.ok and g.no", [None, 0.0, 0.0, 1.0, 0.0]),  # false and null = false
        ("g.ok or g.no", [1.0, None, None, 1.0, 1.0]),  # true or null = true
        ("not g.ok", [0.0, 1.0, None, 0.0, 1.0]),
        ("if(g.ok, g.x, 0)", [1.0, 0.0, None, 4.0, 0.0]),
        ("if(g.ok, 'Y', null)", ["Y", None, None, "Y", None]),
        ("abs(g.x)", [1.0, 2.0, None, 4.0, 1.0]),
        ("sqrt(g.x)", [1.0, np.sqrt(2), None, 2.0, None]),
        ("log(g.y)", [None, 0.0, 0.0, np.log(2), np.log(3)]),
        ("min(g.x, g.y)", [0.0, 1.0, None, 2.0, -1.0]),
        ("max(g.x, g.y, 3)", [3.0, 3.0, None, 4.0, 3.0]),
        ("clip(g.x, 0, 3)", [1.0, 2.0, None, 3.0, 0.0]),
        ("coalesce(g.x, g.y, 9)", [1.0, 2.0, 1.0, 4.0, -1.0]),
        ("coalesce(g.tier, 'D')", ["A", "D", "C", "D", "B"]),
        ("max(coalesce(g.tier, 'D'), 'B')", ["B", "D", "C", "D", "B"]),
        ("min(g.tier, 'B')", ["A", None, "B", "B", "B"]),
        ("is_null(g.x)", [0.0, 0.0, 1.0, 0.0, 0.0]),
        ("one_of(g.tier, 'A', 'B')", [1.0, None, 0.0, 0.0, 1.0]),
        ("g.tier < 'C'", [1.0, None, 0.0, 0.0, 1.0]),
        ("exists(g)", [1.0, 0.0, None, 1.0, 1.0]),
        ("g.day > g.day", [0.0, None, 0.0, 0.0, 0.0]),
        (
            "coalesce(g.day, g.day)",
            [DAYS[0], None, *DAYS[2:]],
        ),
        ("1e308 * 10", [None] * 5),  # overflow is null, never inf
        ("null + 1", [None] * 5),
        ("if(true, 1, null)", [1.0] * 5),
        ("if(false, 'a', 'b') == 'b'", [1.0] * 5),
    ],
)
def test_values_and_nulls(text: str, expected: list[object]) -> None:
    got = run(text)
    for g, e in zip(got, expected, strict=True):
        if isinstance(e, float):
            assert g == pytest.approx(e)
        else:
            assert g == e


def test_column_conversion_round_trips() -> None:
    floats = pd.Series([1.5, None], dtype="float32")
    assert np.isnan(to_column(floats, "num")[1]) and to_column(floats, "num")[0] == 1.5
    ints = pd.Series([3, None], dtype="int64[pyarrow]")
    assert list(np.isnan(to_column(ints, "num"))) == [False, True]
    flags = pd.Series([True, None, False], dtype="bool[pyarrow]")
    assert list(to_column(flags, "bool")[[0, 2]]) == [1.0, 0.0]
    labels = pd.Series(["A", None], dtype="string[pyarrow]")
    assert list(to_column(labels, "str")) == ["A", None]
    days = to_column(pd.Series([date(2026, 1, 2), None]), "date")
    assert np.isnat(days[1])
    back = from_column(np.array([1.0, 0.0, NAN]), "bool")
    assert str(back.dtype) == "bool[pyarrow]" and back.isna().tolist() == [False, False, True]
    assert from_column(np.array([1.0]), "num").tolist() == [1.0]


def test_value_helpers() -> None:
    assert unify([NULL, NULL]) == NULL and unify([NUM, NULL]) == NUM
    assert unify([NUM, Type("str")]) is None
    assert null_mask(full(None, "str", 2), "str").all()
    assert np.isnan(full(None, "null", 1)).all()
    assert list(full(True, "bool", 2)) == [1.0, 1.0]
