"""``config/site/guide/start.toml`` (ADR 0051): the fitness tests over the shipped file first
(the pages the spec lists are written, numbered from 1; every link names an existing Guide
entry of its kind; every catalogue name in the prose is in the catalogue), then the loader's
shape checks."""

from typing import Any

import pytest

from algotrade.config.site.guide.start import (
    ENTRY_KINDS,
    FOLDER,
    NAME,
    EntryRef,
    GuideStart,
    StartSection,
    load_guide_start,
)
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.guide.prose import name_tokens
from algotrade.services.read.guide.search import guide_entries
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
WHERE = "config/site/guide/start.toml"
# docs/ui/guide.md section 3, "Start here", and the Regime page's chart key (GD6).
SPEC_PAGES = (
    "How the app thinks about a day",
    "Read a screen's result",
    "Build a screen",
    "Draft a screen from a sentence",
    "Read the Regime page",
)


@pytest.fixture(scope="module")
def site() -> StoreContext:
    return open_stores(StoreReader(MemoryBackend()), SHIPPED, UserContext(SITE_USER))


def test_the_spec_pages_are_written_in_order_and_numbered_from_one() -> None:
    pages = load_guide_start(SHIPPED).pages
    assert tuple(p.title for p in pages[: len(SPEC_PAGES)]) == SPEC_PAGES
    assert [p.order for p in pages] == list(range(1, len(pages) + 1))


def test_every_link_names_an_existing_entry_of_its_kind(site: StoreContext) -> None:
    entries = {(e.kind, e.id) for e in guide_entries(site)}
    assert {kind for kind, _ in entries} == set(ENTRY_KINDS)  # every kind is reachable
    for page in load_guide_start(SHIPPED).pages:
        unknown = [f"{r.kind}:{r.id}" for r in page.links if (r.kind, r.id) not in entries]
        assert not unknown, f"{WHERE} {page.id} links: no such Guide entry {unknown}"


def test_every_catalogue_name_in_the_prose_is_in_the_catalogue(site: StoreContext) -> None:
    fields = catalog_of(site.features).fields
    for page in load_guide_start(SHIPPED).pages:
        texts = [page.summary, *(s.body for s in page.sections)]
        named = {n for text in texts for n in name_tokens(text)}
        unknown = sorted(n for n in named if not n[0].isdigit() and n not in fields)
        assert not unknown, f"{WHERE} {page.id} names fields not in the catalogue: {unknown}"


PAGE: dict[str, Any] = {
    "id": "two",
    "order": 2,
    "title": "Second",
    "summary": "Then  this.",
    "section": [{"title": "A", "body": "Read\n it."}],
    "links": [{"kind": "term", "id": "session"}],
}


def test_a_document_is_typed_in_order_and_a_missing_file_has_no_pages() -> None:
    first = {**PAGE, "id": "one", "order": 1, "links": []}
    doc = {"page": [PAGE, first]}
    found = load_guide_start(MemoryConfigStore({("site", FOLDER, NAME): doc}))
    one, two = found.pages
    assert (one.id, two.id) == ("one", "two")  # by order, not file order
    assert two.summary == "Then this."
    assert two.sections == (StartSection("A", "Read it."),)
    assert two.links == (EntryRef("term", "session"),) and one.links == ()
    assert found.get("two") is two and found.get("three") is None
    assert load_guide_start(MemoryConfigStore({})) == GuideStart()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"order": None}, "order: required"),
        ({"order": 0}, "order"),
        ({"title": ""}, "title: expected a non-empty string"),
        ({"section": []}, "expected one or more"),
        ({"section": [{"title": "A"}]}, "body: expected a non-empty string"),
        ({"section": [{"title": "A", "body": "b", "x": 1}]}, "unknown keys"),
        ({"links": [{"kind": "chart", "id": "x"}]}, "kind: expected one of"),
        ({"links": [{"id": "x"}]}, "kind: expected one of"),
        ({"links": [{"kind": "term", "id": "x"}] * 2}, "links listed more than once"),
        ({"colour": "red"}, "unknown keys"),
        ({"api_key": "x"}, "looks like a secret"),
    ],
)
def test_bad_pages_fail_naming_the_file(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        GuideStart.from_document({"page": [{**PAGE, **change}]})


@pytest.mark.parametrize(
    ("pages", "message"),
    [
        ([PAGE, {**PAGE, "order": 3}], "page ids listed more than once"),
        ([PAGE, {**PAGE, "id": "other"}], "page orders listed more than once"),
    ],
)
def test_ids_and_orders_are_unique(pages: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        GuideStart.from_document({"page": pages})
