"""``resolve_definitions``: a filter on a field the viewer's licences do not cover, or the
catalogue does not resolve, is not offered and is refused if sent (ADR 0082, ADR 0069)."""

import pytest

from algotrade.config.filters.definitions import load_filter_set, parse_filter_set
from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.services.licences import ALL_LICENCES, OPEN
from algotrade.services.read.context import open_stores
from algotrade.services.read.filtering.definitions import (
    FilterRefusedError,
    resolve_definitions,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

CONFIGS = FileConfigStore(REPO_ROOT / "config")
FEATURES = open_stores(StoreReader(MemoryBackend()), CONFIGS, UserContext(SITE_USER)).features


def surface(*fields: str):
    return parse_filter_set(
        "s",
        {
            "label": "S",
            "filter": [
                {"id": f"f{i}", "label": "F", "group": "more", "kind": "range", "field": f,
                 "bins": [0, 1], "guide": "term:t"}
                for i, f in enumerate(fields)
            ],
        },
    )  # fmt: skip


PERSONAL = "rollup.ibkr_iv@v1.iv30_ibkr"
OPEN_FIELD = "rollup.volume@v1.dollar_volume"


def test_a_licence_the_viewer_lacks_hides_the_filter() -> None:
    got = resolve_definitions(surface(OPEN_FIELD, PERSONAL), FEATURES, {OPEN})
    assert [f.id for f in got.offered] == ["f0"] and got.withheld == {"f1"}
    assert [
        f.id
        for f in resolve_definitions(surface(OPEN_FIELD, PERSONAL), FEATURES, ALL_LICENCES).offered
    ] == ["f0", "f1"]


def test_a_field_the_catalogue_does_not_resolve_is_not_offered() -> None:
    got = resolve_definitions(surface("feature.no_such_field"), FEATURES, ALL_LICENCES)
    assert got.offered == () and got.withheld == {"f0"}


def test_a_column_of_the_surface_is_offered_without_the_catalogue(filter_set) -> None:
    got = resolve_definitions(filter_set, FEATURES, {OPEN})
    assert got.get("tag") is not None  # column:tag; the feature.* ones are unknown here
    assert got.get("size") is None


def test_check_refuses_a_filter_that_is_not_offered() -> None:
    got = resolve_definitions(surface(OPEN_FIELD, PERSONAL), FEATURES, {OPEN})
    got.check(["f0"])
    with pytest.raises(FilterRefusedError, match="f1"):
        got.check(["f0", "f1"])
    with pytest.raises(FilterRefusedError):
        got.check(["nope"])


def test_the_shipped_ideas_surface_is_offered_to_an_open_viewer() -> None:
    got = resolve_definitions(load_filter_set(CONFIGS, "ideas"), FEATURES, {OPEN})
    assert got.withheld == frozenset() and len(got.offered) == 12
