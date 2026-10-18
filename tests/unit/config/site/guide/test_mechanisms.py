"""``config/site/guide/mechanisms/<id>.toml`` (ADR 0051): the fitness tests over the shipped files
first (exactly one file per ``MECHANISM_KINDS`` value; the id is the file's name; every see_also
is a glossary term; titles unique; sources https with no url twice; stats well formed; the edge
documents' kinds all have a page), then the loader's shape checks."""

import copy
import tomllib
from typing import Any

import pytest

from algotrade.config.edges.document import MECHANISM_KINDS
from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.config.site.guide.mechanisms import (
    FOLDER,
    GuideMechanisms,
    MechanismProse,
    MechanismStat,
    load_guide_mechanisms,
)
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
FILES = REPO_ROOT / "config" / "site" / "guide" / "mechanisms"


def test_exactly_one_file_per_mechanism_kind() -> None:
    stems = sorted(p.stem for p in FILES.glob("*.toml"))
    assert stems == sorted(MECHANISM_KINDS), (
        f"one config/site/guide/mechanisms/<kind>.toml per MECHANISM_KINDS value: missing "
        f"{sorted(set(MECHANISM_KINDS) - set(stems))}, no such kind "
        f"{sorted(set(stems) - set(MECHANISM_KINDS))}"
    )
    assert sorted(m.id for m in load_guide_mechanisms(SHIPPED).mechanisms) == stems


def test_every_see_also_is_a_glossary_term() -> None:
    terms = {t.id for t in load_guide_glossary(SHIPPED).terms}
    bad = [
        f"{m.id} -> {ref}"
        for m in load_guide_mechanisms(SHIPPED).mechanisms
        for ref in m.see_also
        if ref not in terms
    ]
    assert not bad, f"see_also names no glossary term: {bad}"


def test_titles_are_unique_and_every_page_has_sources() -> None:
    found = load_guide_mechanisms(SHIPPED).mechanisms
    assert len({m.title for m in found}) == len(found)
    assert all(m.sources and m.stats for m in found)


def test_the_shipped_stats_are_our_own_bar() -> None:
    verdict = tomllib.loads((REPO_ROOT / "config" / "site" / "verdict.toml").read_text())
    assert verdict["works_t"] == 3.0
    assert (
        verdict["published_haircut"]["short"] == verdict["published_haircut"]["long_short"] == 0.5
    )
    assert round(1 / verdict["published_haircut"]["long"]) == 3
    for m in load_guide_mechanisms(SHIPPED).mechanisms:
        for stat in m.stats:
            assert stat.source is None or stat.source <= len(m.sources)


DOC: dict[str, Any] = {
    "id": "alpha",
    "title": "Alpha",
    "question": "Who?",
    "examples": "one, two",
    "short": "Short.",
    "how_it_works": ["a"],
    "why_it_survives": ["b"],
    "research": ["c"],
    "real_vs_decoy": ["d"],
    "dont": "Do not.",
    "see_also": ["t1"],
    "stats": [{"label": "L", "value": "V", "note": "N", "source": 1}],
    "sources": [{"title": "T", "url": "https://example.org/a", "note": "n"}],
}


def _with(**changes: Any) -> dict[str, Any]:
    return {**copy.deepcopy(DOC), **changes}


def test_a_document_is_typed_and_a_missing_folder_has_nothing() -> None:
    found = load_guide_mechanisms(MemoryConfigStore({("site", FOLDER, "alpha"): DOC}))
    m = found.get("alpha")
    assert isinstance(m, MechanismProse) and m.sources[0].url == "https://example.org/a"
    assert m.stats == (MechanismStat("L", "V", "N", 1),)
    assert load_guide_mechanisms(MemoryConfigStore({})) == GuideMechanisms()


def test_stats_and_see_also_are_optional() -> None:
    doc = {k: v for k, v in DOC.items() if k not in ("stats", "see_also")}
    m = MechanismProse.from_document("alpha", doc)
    assert m.stats == () and m.see_also == ()


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        (_with(id="beta"), "expected 'alpha'"),
        (_with(colour="red"), "unknown keys"),
        (_with(title=" "), "title: expected a non-empty string"),
        (_with(how_it_works=[]), "how_it_works: expected one or more"),
        (_with(see_also=["a", "a"]), "see_also ids listed more than once"),
        (_with(sources=[{"title": "T", "url": "http://x.org", "note": "n"}]), "https url"),
        (
            _with(sources=[{"title": "T", "url": "https://x.org", "note": "n"}] * 2),
            "source urls listed more than once",
        ),
        (_with(stats=[{"label": "L", "value": "V", "note": "N", "source": 2}]), "but there are 1"),
        (_with(stats=[{"label": "L", "value": "V"}]), "note: expected a non-empty string"),
        (_with(stats=[{"label": "L", "value": "V", "note": "N", "x": 1}]), "unknown keys"),
        (_with(api_key="x"), "looks like a secret"),
    ],
)
def test_bad_documents_fail_naming_the_file(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        MechanismProse.from_document("alpha", doc)


def test_two_files_with_one_title_fail() -> None:
    store = MemoryConfigStore(
        {("site", FOLDER, "alpha"): DOC, ("site", FOLDER, "beta"): _with(id="beta")}
    )
    with pytest.raises(ConfigurationError, match="titles listed more than once"):
        load_guide_mechanisms(store)
