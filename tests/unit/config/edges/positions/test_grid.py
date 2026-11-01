"""``[[variant_grid]]``: parsed fail closed, expanded deterministically (axes in a fixed order,
values ascending, the id spelled from the point)."""

from typing import Any

import pytest

from algotrade.config.edges.positions.grid import parse_grids, points
from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

GRID = {"prefix": "g", "strike_delta": [0.16, 0.2, 0.3], "tenor_days": [7, 30, 45],
        "take_profit": [0.0, 0.5]}  # fmt: skip


def parse(*grids: dict[str, Any]) -> Any:
    return parse_grids(Table({"variant_grid": list(grids)}, "doc"))


def test_the_expansion_is_deterministic_whatever_the_key_order() -> None:
    shuffled = dict(reversed(list(GRID.items())))
    a, b = points(parse(GRID)[0]), points(parse(shuffled)[0])
    assert a == b and len(a) == 18
    assert a[0].id == "g_d16_t7_tp0" and a[1].id == "g_d16_t7_tp50"
    assert a[-1].id == "g_d30_t45_tp50" and len({p.id for p in a}) == 18
    assert dict(a[1].values) == {"strike_delta": 0.16, "tenor_days": 7, "take_profit": 0.5}


@pytest.mark.parametrize(
    ("grid", "match"),
    [
        ({"prefix": "g"}, "names no axis"),
        ({"prefix": "g", "strike_delta": [0.3, 0.2]}, "ascending"),
        ({"prefix": "g", "strike_delta": [0.2, 0.2]}, "distinct"),
        ({"prefix": "g", "tenor_days": [7.5]}, "integers"),
        ({"prefix": "g", "tenor_days": []}, "tenor_days"),
        ({"prefix": "g", "take_profit": [0, 5]}, "take_profit"),
        ({"prefix": "g", "strike_delta": [0.9]}, "strike_delta"),
        ({"prefix": "g", "exit_dte": [1000]}, "exit_dte"),
        ({"prefix": "g", "yield": [1]}, "unknown keys"),
        ({"prefix": "G!", "tenor_days": [7]}, "invalid variant id"),
        ({"prefix": "g", "tenor_days": list(range(1, 70))}, "at most 64"),
    ],
)
def test_a_grid_is_typed_fail_closed(grid: dict[str, Any], match: str) -> None:
    with pytest.raises(ConfigurationError, match=match):
        parse(grid)


def test_a_prefix_is_listed_once_and_no_grid_is_none() -> None:
    with pytest.raises(ConfigurationError, match="listed twice"):
        parse({"prefix": "g", "tenor_days": [7]}, {"prefix": "g", "tenor_days": [30]})
    assert parse() == ()
