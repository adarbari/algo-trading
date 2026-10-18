"""ttm.py: the TTM arithmetic moved out of financials@v3 (same objects, same results)."""

from datetime import date

from algotrade.features.rollups.corporate import financials
from algotrade.features.rollups.statements import ttm

DAY = date(1970, 1, 1)


def _d(y: int, m: int, d: int) -> int:
    return (date(y, m, d) - DAY).days


def _quarterly(values: list[float]) -> list[ttm.Fact]:
    ends = [(2024, 3, 31), (2024, 6, 30), (2024, 9, 30), (2024, 12, 31)]
    starts = [(2024, 1, 1), (2024, 4, 1), (2024, 7, 1), (2024, 10, 1)]
    return [
        (_d(*s), _d(*e), v, _d(*e) + 30, 0) for s, e, v in zip(starts, ends, values, strict=True)
    ]


def test_financials_uses_the_shared_ttm_functions() -> None:
    for name in ("annual", "discrete_quarters", "latest_quarter", "months", "trailing"):
        assert getattr(financials, name) is getattr(ttm, name)


def test_four_quarters_sum_to_the_ttm() -> None:
    found = ttm.trailing(_quarterly([1.0, 2.0, 3.0, 4.0]))
    assert found is not None
    (value, end, _, annual), year_ago = found
    assert (value, end, annual, year_ago) == (10.0, _d(2024, 12, 31), False, None)


def test_three_quarters_give_no_ttm() -> None:
    assert ttm.trailing(_quarterly([1.0, 2.0, 3.0, 4.0])[:3]) is None
