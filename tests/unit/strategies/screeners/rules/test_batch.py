"""``evaluate_column`` gives, for any column, exactly what ``evaluate_criterion`` gives value by
value: outcome, distance, normalised, penalty, the value kept as it came and the verdict (the
property that lets a screen evaluate a column at once, bit for bit)."""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.core.model.predicates import Rule
from algotrade.core.model.screen_spec import Criterion, Mode, Tolerance
from algotrade.core.views.feature_view import FeatureView
from algotrade.strategies.screeners.rules import evaluate_screen
from algotrade.strategies.screeners.rules.batch import evaluate_column
from algotrade.strategies.screeners.rules.criteria import CriterionResult, evaluate_criterion
from tests.unit.strategies.screeners.rules.test_evaluate import DAY, ROWS, spec

_NUM = st.one_of(
    st.none(),
    st.floats(allow_nan=True, allow_infinity=True, width=64),
    st.floats(min_value=-5, max_value=5).map(lambda x: round(x, 1)),
    st.integers(min_value=-10, max_value=10),
)
_ODD = st.one_of(
    _NUM, st.booleans(), st.text(max_size=3), st.integers(min_value=2**60, max_value=2**61)
)
_BOUND = st.one_of(st.integers(-5, 5), st.floats(-5, 5).map(lambda x: round(x, 1)))
_TOLERANCE = st.one_of(
    st.none(),
    st.builds(Tolerance, st.sampled_from([0.0, 0.1, 1.0, 2.5]), st.booleans()),
)


@st.composite
def criteria(draw: st.DrawFn) -> Criterion:
    op = draw(st.sampled_from(["gt", "gte", "lt", "lte", "between", "in", "is_null", "not_null"]))
    if op == "between":
        low, high = sorted((draw(_BOUND), draw(_BOUND)))
        value: object = (low, high)
    elif op == "in":
        value = (1, 2)
    elif op in ("is_null", "not_null"):
        value = None
    else:
        value = draw(_BOUND)
    return Criterion(
        "c", Rule("f", op, value), draw(st.sampled_from(list(Mode))), draw(_TOLERANCE),  # type: ignore[arg-type]
        draw(st.sampled_from(["WATCH", "EVENT_RISK", "LIQUIDITY_RISK"])),
    )  # fmt: skip


def _same(a: CriterionResult, b: CriterionResult) -> bool:
    fields = ("value", "outcome", "distance", "normalised", "penalty")
    # repr tells -0.0 from 0.0, nan from nan, 1 from 1.0
    return all(repr(getattr(a, f)) == repr(getattr(b, f)) for f in fields) and (
        a.criterion is b.criterion and a.verdict == b.verdict
    )


@settings(max_examples=400, deadline=None)
@given(criteria(), st.lists(_NUM, max_size=30))
def test_a_numeric_column_equals_the_scalar_results(criterion: Criterion, values: list) -> None:
    batch = evaluate_column(criterion, values)
    assert len(batch) == len(values)
    for got, value in zip(batch, values, strict=True):
        assert _same(got, evaluate_criterion(criterion, value))


@settings(max_examples=200, deadline=None)
@given(criteria(), st.lists(_ODD, max_size=20))
def test_a_column_of_anything_else_equals_the_scalar_results(
    criterion: Criterion, values: list
) -> None:
    for got, value in zip(evaluate_column(criterion, values), values, strict=True):
        assert _same(got, evaluate_criterion(criterion, value))


def test_nan_is_recorded_as_missing_and_a_zero_width_band_is_infinite() -> None:
    soft = Criterion("c", Rule("f", "gte", 1), Mode.SOFT, Tolerance(0.0))
    miss, nan = evaluate_column(soft, [0.5, math.nan])
    assert nan.value is None and nan.outcome.value == "MISSING"
    assert miss.normalised == math.inf and miss.outcome.value == "FAIL"


def test_a_screen_evaluated_by_column_equals_the_memoised_per_value_screen() -> None:
    """``evaluate_screen`` without a memo takes the column path, with one the per-value path:
    the same rows, bit for bit (the golden equality; the memo-less run is the harness's)."""
    view = FeatureView(DAY, ROWS)
    by_column = evaluate_screen(spec(), view)
    by_value = evaluate_screen(spec(), view, {})
    assert repr(by_column.rows) == repr(by_value.rows)
    assert repr(by_column.summary) == repr(by_value.summary)
