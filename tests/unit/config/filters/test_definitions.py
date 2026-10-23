"""``config/site/filters/<surface>.toml`` (ADR 0082): the fitness tests over the shipped files
first (every field is a catalogue name or a declared column of the surface, the kind fits the
dtype, the options and bins are what the kind needs, the Guide entry exists and the enum is
real), then the loader's shape checks."""

import dataclasses
import importlib
from typing import Any, get_args, get_origin, get_type_hints

import pytest

from algotrade.config.filters.definitions import (
    COLUMN,
    GROUPS,
    FilterSet,
    load_filter_set,
    parse_filter_set,
)
from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import open_stores
from algotrade.services.read.screens.ideas import Idea
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
SURFACES = {"ideas": Idea}  # surface -> the read object its columns come from
NUMERIC = {"int", "float", "float32", "float64", "int32", "int64"}
KIND_DTYPES = {
    "pick": {"str"},
    "select": {"str"},
    "toggle": {"bool"},
    "range": NUMERIC,
    "window": {"int"},
    "percentile": NUMERIC,
}
COLUMN_DTYPE = {"str": "str", "int": "int", "float": "float", "bool": "bool", "date": "date"}


def shipped(surface: str) -> FilterSet:
    return load_filter_set(SHIPPED, surface)


def _fields() -> dict[str, Any]:
    site = open_stores(StoreReader(MemoryBackend()), SHIPPED, UserContext(SITE_USER))
    return dict(catalog_of(site.features).fields)


def _walk(root: type, path: str) -> bool:
    """Whether ``a.b`` is a field of ``root``'s dataclass ``a`` (a tuple of them: its element)."""
    cls: Any = root
    for part in path.split("."):
        if not dataclasses.is_dataclass(cls) or part not in {
            f.name for f in dataclasses.fields(cls)
        }:
            return False
        cls = get_type_hints(cls)[part]
        if get_origin(cls) is tuple:
            cls = get_args(cls)[0]
    return True


def test_a_column_path_is_checked_against_the_read_object() -> None:
    assert _walk(Idea, "best.decision") and _walk(Idea, "picked_by.config_id")
    assert not _walk(Idea, "best.nope") and not _walk(Idea, "rank.x")


@pytest.mark.parametrize("surface", SURFACES)
def test_every_shipped_surface_is_declared_here(surface: str) -> None:
    assert (REPO_ROOT / "config/site/filters" / f"{surface}.toml").exists()
    on_disk = {p.stem for p in (REPO_ROOT / "config/site/filters").glob("*.toml")}
    assert on_disk == set(SURFACES), "config/site/filters: add the new surface's read object above"


@pytest.mark.parametrize("surface", SURFACES)
def test_every_field_is_in_the_catalogue_or_a_column_of_the_surface(surface: str) -> None:
    fs = shipped(surface)
    catalogue = _fields()
    for f in fs.filters:
        if f.column_id is None:
            assert f.field in catalogue, (
                f"filters/{surface}.toml {f.id}: {f.field} not in the catalogue"
            )
        else:
            assert f.column_id in {c.id for c in fs.columns}


@pytest.mark.parametrize("surface", SURFACES)
def test_every_column_comes_from_the_read_object(surface: str) -> None:
    for c in shipped(surface).columns:
        source = c.source.removeprefix("len(").removesuffix(")")
        assert _walk(SURFACES[surface], source), f"{surface} column {c.id}: no {c.source}"


@pytest.mark.parametrize("surface", SURFACES)
def test_the_kind_fits_the_dtype(surface: str) -> None:
    fs = shipped(surface)
    catalogue = _fields()
    columns = {c.id: c.dtype for c in fs.columns}
    for f in fs.filters:
        dtype = columns[f.column_id] if f.column_id else str(catalogue[f.field])
        assert dtype in KIND_DTYPES[f.kind], f"{surface} {f.id}: a {f.kind} filter on {dtype}"


@pytest.mark.parametrize("surface", SURFACES)
def test_a_static_option_is_a_category_of_its_field(surface: str) -> None:
    site = open_stores(StoreReader(MemoryBackend()), SHIPPED, UserContext(SITE_USER))
    catalogue = catalog_of(site.features)
    for f in shipped(surface).filters:
        if f.options == "static" and f.column_id is None:
            cats = getattr(catalogue.fields[f.field], "categories", None)
            if cats:
                assert {o.value for o in f.static} <= set(cats), f"{surface} {f.id}"


@pytest.mark.parametrize("surface", SURFACES)
def test_an_enum_filter_names_a_real_enum(surface: str) -> None:
    for f in shipped(surface).filters:
        if f.enum:
            module, name = f.enum.split(":")
            values = list(getattr(importlib.import_module(module), name))
            assert values, f"{surface} {f.id}: {f.enum} has no values"


@pytest.mark.parametrize("surface", SURFACES)
def test_every_guide_entry_exists(surface: str) -> None:
    terms = {t.id for t in load_guide_glossary(SHIPPED).terms}
    fs = shipped(surface)
    refs = [f.guide for f in fs.filters]
    refs += [f"term:filter_group_{g}" for g in GROUPS]
    for ref in refs:
        kind, entry = ref.split(":")
        assert kind == "term" and entry in terms, f"filters/{surface}.toml: no Guide entry {ref}"


def test_the_control_words_have_guide_entries() -> None:
    terms = {t.id for t in load_guide_glossary(SHIPPED).terms}
    words = {"filter_removes", "filter_switched_off", "filter_unknown_rows", "filter_range",
             "filter_window", "filter_toggle"}  # fmt: skip
    assert words <= terms


def test_the_shipped_ideas_file_leaves_out_what_is_not_stored() -> None:
    ids = {f.id for f in shipped("ideas").filters}
    assert not ids & {"new_today", "rank_moved_up", "optionable"}, "needs new data first"


# ------------------------------------------------------------------ the loader's shape checks

GOOD: dict[str, Any] = {
    "label": "Things",
    "column": [{"id": "n", "dtype": "int", "source": "n"}],
    "filter": [
        {"id": "a", "label": "A", "group": "setup", "kind": "range", "field": "column:n",
         "bins": [0, 1, 2], "guide": "term:x"},
        {"id": "b", "label": "B", "group": "more", "kind": "pick", "field": "feature.f",
         "options": "static", "option": [{"value": "x", "label": "X"}], "guide": "term:y"},
        {"id": "c", "label": "C", "group": "coming_up", "kind": "window", "field": "feature.g",
         "window_unit": "days", "guide": "term:z"},
    ],
}  # fmt: skip


def with_filter(**changes: Any) -> dict[str, Any]:
    first = {**GOOD["filter"][0], **changes}
    return {**GOOD, "filter": [{k: v for k, v in first.items() if v is not None}]}


def test_a_document_is_typed_and_a_missing_file_has_no_filters() -> None:
    fs = parse_filter_set("things", GOOD)
    assert [f.id for f in fs.filters] == ["a", "b", "c"]
    assert fs.get("a").bins == (0.0, 1.0, 2.0) and fs.get("a").column_id == "n"
    assert [f.id for f in fs.in_group("more")] == ["b"] and fs.get("zz") is None
    assert parse_filter_set("none", None) == FilterSet("none", "none", (), ())


def test_the_store_serves_the_file_by_surface() -> None:
    store = MemoryConfigStore({("site", "filters", "things"): GOOD})
    assert [f.id for f in load_filter_set(store, "things").filters] == ["a", "b", "c"]


@pytest.mark.parametrize(
    "doc",
    [
        with_filter(bins=None),  # a range needs bins
        with_filter(bins=[2, 1]),  # ascending
        with_filter(bins=[1]),  # two or more
        with_filter(kind="pick"),  # a pick needs options (and has bins)
        with_filter(kind="window", bins=None),  # a window needs its unit
        with_filter(window_unit="days"),  # a unit only on a window
        with_filter(kind="toggle", bins=None, options="static"),  # options only on pick, select
        with_filter(group="elsewhere"),
        with_filter(kind="slider"),
        with_filter(guide="nothing"),
        with_filter(guide="page:x"),
        with_filter(id="Bad Id"),
        with_filter(field="column:other"),  # no such column
        with_filter(field="column:Bad"),
        with_filter(extra=1),
        {**GOOD, "filter": [GOOD["filter"][0], GOOD["filter"][0]]},  # an id twice
        {**GOOD, "column": [GOOD["column"][0], GOOD["column"][0]]},
        {**GOOD, "column": [{"id": "n", "dtype": "blob", "source": "n"}]},
        {**GOOD, "other": 1},
    ],
)
def test_a_malformed_document_fails_naming_the_file(doc: dict[str, Any]) -> None:
    with pytest.raises(ConfigurationError, match=r"filters/things\.toml"):
        parse_filter_set("things", doc)


@pytest.mark.parametrize(
    "extra",
    [
        {"options": "static"},  # static without [[option]]
        {"options": "enum"},  # enum without a name
        {"options": "enum", "enum": "not a path"},
        {"options": "values", "enum": "a.b:C"},  # a name only with enum
        {"options": "values", "option": [{"value": "x", "label": "X"}]},
        {"options": "static", "option": [{"value": "x", "label": "X"}] * 2},  # a value twice
        {"options": "bogus"},
    ],
)
def test_a_pick_needs_exactly_the_options_its_source_names(extra: dict[str, Any]) -> None:
    bad = with_filter(kind="pick", bins=None, **extra)
    with pytest.raises(ConfigurationError, match=r"filters/things\.toml"):
        parse_filter_set("things", bad)


def test_a_column_prefix_is_the_documented_one() -> None:
    assert COLUMN == "column:"
