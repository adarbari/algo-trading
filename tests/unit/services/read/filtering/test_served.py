"""``load_list_filters`` is ``load_served_filters`` without the no-data check: the lists never
run it (a full read whose result only ``filterSet`` uses, #956), they resolve the same filters
and columns for every input, and ``filterSet`` is the only caller of the full loader."""

import ast
import copy
import tomllib

import pytest

from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext
from algotrade.services.read.filtering import served
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.filtering.served import (
    load_filter_set_with,
    load_list_filters,
    load_served_filters,
)
from algotrade.services.read.screens.ideas import load_ideas
from tests.conftest import REPO_ROOT
from tests.unit.services.read.screens.conftest import context, screens_store

FILTERS = REPO_ROOT / "config/site/filters"
SURFACES = sorted(p.stem for p in FILTERS.glob("*.toml"))
DOCS = {
    ("site", "filters", s): tomllib.loads((FILTERS / f"{s}.toml").read_text()) for s in SURFACES
}
USERS = {
    ("site", "settings", "users"): {
        "user": [
            {"id": "admin", "role": "admin"},
            {"id": "bare", "role": "trader"},
            {"id": "full", "role": "trader", "licences": ["personal", "yahoo"]},
        ]
    }
}
PERSONAL = "rollup.ibkr_iv@v1.iv30_ibkr"
WANTED = [
    (),
    ("feature:rollup.volume@v1.dollar_volume",),
    (f"feature:{PERSONAL}", "feature:nope.missing"),
    ("dollar_volume", "feature:rollup.volume@v1.dollar_volume"),
]


def view(user: str) -> ReadContext:
    return context(StoreReader(screens_store()), copy.deepcopy({**DOCS, **USERS}), user=user)


def test_list_filters_never_check_data(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args, **kwargs):
        raise AssertionError("the no-data check ran for a list")

    monkeypatch.setattr(served, "fields_without_data", refuse)
    ctx = view("full")
    assert SURFACES
    for surface in SURFACES:
        assert load_list_filters(ctx, surface).resolved.surface == surface
    assert load_ideas(ctx, 10, None, [FilterInput("dollar_volume", min=1)]).total >= 0
    with pytest.raises(AssertionError):  # the guard works: filterSet still runs the check
        load_served_filters(ctx, "ideas", ctx.session.date)


@pytest.mark.parametrize("user", ["bare", "full"])
@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("wanted", WANTED)
def test_list_filters_equal_the_served_ones(user, surface, wanted) -> None:
    ctx = view(user)
    full = load_served_filters(ctx, surface, ctx.session.date, wanted)
    lists = load_list_filters(ctx, surface, wanted)
    assert lists.resolved == full.resolved
    assert lists.columns == full.columns


def _calls(path) -> list[tuple[str, str]]:
    """``(file, enclosing function)`` of each use of ``load_served_filters`` outside its def and
    imports."""
    found = []
    for file in path.rglob("*.py"):
        tree = ast.parse(file.read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Name) and node.id == "load_served_filters":
                    found.append((file.name, fn.name))
    return found


def test_filter_set_is_the_only_caller_of_the_full_loader() -> None:
    uses = _calls(REPO_ROOT / "src/algotrade") + _calls(REPO_ROOT / "apps/api")
    assert {u for u in uses if u != ("served.py", "load_served_filters")} == {
        ("served.py", "load_filter_set_with")
    }
    assert load_filter_set_with  # the loader the GraphQL FilterSet type calls
