"""``config/site/guide/ideas/<family>.toml`` (ADR 0051): the fitness tests over the shipped files
first (the catalogue's headings and the ideas agree; an idea filed as an edge names a site edge
or one of its variants; an idea not filed is not a site edge, so building one fails here until
its entry moves to ``filed_as``; the closed sets; one plain sentence of why), then the loader's
shape checks."""

import copy
import re
from typing import Any

import pytest

from algotrade.config.edges.document import MECHANISM_KINDS
from algotrade.config.site.guide.ideas import (
    FAMILIES,
    FOLDER,
    IDEA_FEASIBILITY,
    IDEA_VERDICTS,
    GuideIdeas,
    Idea,
    load_guide_ideas,
)
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
PAGES = REPO_ROOT / "docs" / "edge-ideas"
PAGE_FILES = {  # family letter -> its catalogue page (docs/edge-ideas/README.md, family table)
    "A": "cross-sectional", "B": "events", "C": "options-volatility", "D": "calendar-flows",
    "E": "trend-macro", "F": "altdata-text-ml", "G": "statarb-technical",
    "H": "structural-niches", "I": "frontier",
}  # fmt: skip
HEADING = re.compile(r"^### (\S+) — ", re.MULTILINE)
WHERE = "config/site/guide/ideas/<family>.toml"
MAX_WHY_WORDS = 30


def _headings() -> dict[str, set[str]]:
    return {
        letter: set(HEADING.findall((PAGES / f"{page}.md").read_text()))
        for letter, page in PAGE_FILES.items()
    }


def _site_edges() -> tuple[set[str], set[str]]:
    """The site edge ids and the ids of their ``[[variants]]``."""
    ids = SHIPPED.names("site", "edges")
    variants = {
        v["id"] for i in ids for v in (SHIPPED.load("site", "edges", i) or {}).get("variants", [])
    }
    return set(ids), variants


@pytest.fixture(scope="module")
def ideas() -> GuideIdeas:
    return load_guide_ideas(SHIPPED)


def test_the_families_are_the_catalogues_nine_pages() -> None:
    assert list(PAGE_FILES) == list(FAMILIES)
    assert [p.replace("-", "_") for p in PAGE_FILES.values()] == list(FAMILIES.values())
    assert SHIPPED.names("site", FOLDER) == sorted(FAMILIES.values())


def test_every_catalogue_heading_is_an_idea_or_a_site_edge_and_every_idea_a_heading(
    ideas: GuideIdeas,
) -> None:
    headings = set().union(*_headings().values())
    edges, _ = _site_edges()
    listed = {i.id for i in ideas.ideas}
    assert listed <= headings, (
        f"{WHERE}: not a heading of docs/edge-ideas: {sorted(listed - headings)}"
    )
    missing = headings - listed - edges
    assert not missing, (
        f"add each to {WHERE} (an [[idea]]: filed_as, or verdict, feasibility and why_not_built): "
        f"{sorted(missing)}"
    )


def test_an_idea_sits_in_a_family_whose_page_has_its_heading(ideas: GuideIdeas) -> None:
    heads = _headings()
    for idea in ideas.ideas:
        assert idea.id in heads[idea.family], (
            f"{idea.id} has no heading in the page of family {idea.family}"
        )


def test_an_idea_filed_as_an_edge_names_a_site_edge_or_one_of_its_variants(
    ideas: GuideIdeas,
) -> None:
    edges, variants = _site_edges()
    for idea in ideas.ideas:
        if idea.filed_as is not None:
            assert idea.filed_as in edges | variants, (
                f"{idea.id} filed_as {idea.filed_as!r}: not a site edge or a variant of one"
            )


def test_an_idea_not_filed_is_not_a_site_edge_so_building_one_moves_it_to_filed_as(
    ideas: GuideIdeas,
) -> None:
    edges, variants = _site_edges()
    built = sorted(i.id for i in ideas.unfiled if i.id in edges | variants)
    assert not built, (
        f"{built} is now a site edge: replace its verdict, feasibility and why_not_built in "
        f"{WHERE} with filed_as = its edge id"
    )


def test_every_closed_set_value_is_valid_and_one_plain_sentence_says_why(ideas: GuideIdeas) -> None:
    for idea in ideas.ideas:
        assert idea.mechanism_kind in MECHANISM_KINDS, idea.id
        assert len(idea.title.split()) <= 8, f"{idea.id}: a title is at most 8 words"
        if idea.filed_as is not None:
            continue
        assert idea.verdict in IDEA_VERDICTS and idea.feasibility in IDEA_FEASIBILITY, idea.id
        why = idea.why_not_built or ""
        assert why.endswith(".") and "." not in why[:-1].replace("e.g.", ""), (
            f"{idea.id}: why_not_built is one sentence ending in a full stop"
        )
        assert len(why.split()) <= MAX_WHY_WORDS, (
            f"{idea.id}: why_not_built over {MAX_WHY_WORDS} words"
        )


def test_a_why_states_no_return_figure(ideas: GuideIdeas) -> None:
    """The catalogue's returns and statistics are not all verified: a why states none."""
    for idea in ideas.unfiled:
        assert not re.search(
            r"%|\bbp\b|basis point|\bt-stat|\bSharpe\b", idea.why_not_built or ""
        ), f"{idea.id}: why_not_built states a return figure; leave it to the edge's own page"


# --- the loader's shape checks ---

DOC: dict[str, Any] = {
    "family": "B",
    "idea": [
        {
            "id": "alpha", "title": "Alpha", "mechanism_kind": "slow_to_update",
            "filed_as": "momentum_12_1",
        },
        {
            "id": "beta", "title": "Beta", "mechanism_kind": "forced_flows", "verdict": "weak",
            "feasibility": "needs_data", "why_not_built": "It needs data we do not store.",
        },
    ],
}  # fmt: skip


def _load(doc: dict[str, Any], name: str = "events") -> GuideIdeas:
    return load_guide_ideas(MemoryConfigStore({("site", FOLDER, name): doc}))


def test_the_loader_reads_filed_and_unfiled_ideas() -> None:
    found = _load(DOC)
    assert [i.id for i in found.ideas] == ["alpha", "beta"]
    assert found.get("alpha") == Idea(
        "alpha", "B", "Alpha", "slow_to_update", filed_as="momentum_12_1"
    )
    assert [i.id for i in found.unfiled] == ["beta"]
    assert load_guide_ideas(MemoryConfigStore({})) == GuideIdeas()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["idea"][1].update(verdict="great"), "verdict"),
        (lambda d: d["idea"][1].update(feasibility="soon"), "feasibility"),
        (lambda d: d["idea"][1].pop("why_not_built"), "why_not_built"),
        (lambda d: d["idea"][0].update(verdict="weak"), "filed_as"),
        (lambda d: d["idea"][0].pop("filed_as"), "filed_as, or"),
        (lambda d: d["idea"][1].update(note="x"), "note"),
        (lambda d: d["idea"][1].update(id="Beta"), "snake_case"),
        (lambda d: d["idea"][1].update(id="alpha"), "alpha"),
        (lambda d: d.update(family="C"), "family"),
    ],
)
def test_the_loader_refuses_a_bad_idea(mutate: Any, message: str) -> None:
    doc = copy.deepcopy(DOC)
    mutate(doc)
    with pytest.raises(ConfigurationError, match=message):
        _load(doc)
