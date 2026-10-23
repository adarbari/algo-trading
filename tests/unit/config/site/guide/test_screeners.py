"""``config/site/guide/screeners/<id>.toml`` (ADR 0051): the fitness tests over the shipped
files first (every site preset has exactly one screener and every screener a preset; ``asks``
names exactly the criteria of the preset's latest version; every related id is a site
screener; every catalogue name written in the prose is in the catalogue; every source marker
``[^n]`` names a source, every source is cited at least once and no marker stands outside the
four prose texts), then the loader's
shape checks."""

from typing import Any

import pytest

from algotrade.config.site.guide.screeners import (
    FOLDER,
    GuideScreeners,
    RelatedScreener,
    ScreenerProse,
    load_guide_screeners,
)
from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.config.site.guide.sources import GuideSource, markers
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.guide.prose import name_tokens
from algotrade.services.read.guide.screeners.site_screeners import site_screeners
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import SCREENERS, FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
WHERE = "config/site/guide/screeners"


@pytest.fixture(scope="module")
def site() -> StoreContext:
    return open_stores(StoreReader(MemoryBackend()), SHIPPED, UserContext(SITE_USER))


def test_every_site_preset_has_exactly_one_screener_and_every_screener_a_preset() -> None:
    presets = SHIPPED.names("site", SCREENERS)
    screeners = SHIPPED.names("site", FOLDER)
    assert screeners == presets, (
        f"write one {WHERE}/<id>.toml per site rule-screen preset: missing "
        f"{sorted(set(presets) - set(screeners))}, no such preset "
        f"{sorted(set(screeners) - set(presets))}"
    )


def test_asks_names_exactly_the_criteria_of_the_latest_preset_version(site: StoreContext) -> None:
    prose = load_guide_screeners(SHIPPED)
    screeners = site_screeners(site)
    assert [p.id for p in screeners] and len(screeners) == len(SHIPPED.names("site", SCREENERS))
    for screener in screeners:
        written = prose.get(screener.id)
        assert written is not None, screener.id
        assert written.version == screener.spec.version, (
            f"{WHERE}/{screener.id}.toml was written for version {written.version}, the preset "
            f"is at {screener.spec.version}: re-read its prose and thresholds, then raise version"
        )
        criteria = [c.id for c in screener.spec.criteria]
        asks = [name for name, _ in written.asks]
        assert sorted(asks) == sorted(criteria), (
            f"{WHERE}/{screener.id}.toml [asks]: one entry per criterion of version "
            f"{screener.spec.version}: missing {sorted(set(criteria) - set(asks))}, no such "
            f"criterion {sorted(set(asks) - set(criteria))}"
        )


def test_every_related_id_is_a_site_screener() -> None:
    presets = set(SHIPPED.names("site", SCREENERS))
    for screener in load_guide_screeners(SHIPPED).screeners:
        unknown = [r.id for r in screener.related if r.id not in presets]
        assert not unknown, f"{WHERE}/{screener.id}.toml related: no such screener {unknown}"


def test_every_catalogue_name_in_the_prose_is_in_the_catalogue(site: StoreContext) -> None:
    fields = catalog_of(site.features).fields
    for p in load_guide_screeners(SHIPPED).screeners:
        texts = [*p.texts, *(a for _, a in p.asks)]
        named = {n for text in texts for n in name_tokens(text) if not n[0].isdigit()}
        unknown = sorted(n for n in named if n not in fields)
        assert not unknown, f"{WHERE}/{p.id}.toml names fields not in the catalogue: {unknown}"


def test_every_marker_names_a_source_and_every_source_is_cited() -> None:
    for p in load_guide_screeners(SHIPPED).screeners:
        cited = {n for text in p.texts for n in markers(text)}  # a bad marker fails the loader
        uncited = sorted(set(range(1, len(p.sources) + 1)) - cited)
        assert not uncited, (
            f"{WHERE}/{p.id}.toml: sources {uncited} are never cited; put [^n] where the claim "
            f"they back is said, or drop the source"
        )
        assert p.sources, f"{WHERE}/{p.id}.toml: a screener names at least one source"


def test_no_marker_stands_outside_the_prose_texts() -> None:
    for p in load_guide_screeners(SHIPPED).screeners:
        outside = [t for _, t in p.asks if markers(t)]
        assert not outside, f"{WHERE}/{p.id}.toml: a marker in an ask: {outside}"


def test_every_site_preset_has_a_one_line_description() -> None:
    """The Screeners list shows it under every screener's name (ADR 0029 amendment): a preset
    without one fails here, not in the browser."""
    missing, long = [], []
    for preset in SHIPPED.names("site", SCREENERS):
        text = (SHIPPED.load("site", SCREENERS, preset) or {}).get("description")
        if not isinstance(text, str) or not text.strip():
            missing.append(preset)
        elif len(text) > 140 or "\n" in text:
            long.append(preset)
    assert not missing, f"presets without a `description` line: {missing}"
    assert not long, f"descriptions over 140 characters: {long}"


def test_every_url_is_https() -> None:
    for p in load_guide_screeners(SHIPPED).screeners:
        for source in p.sources:
            assert source.url is None or source.url.startswith("https://"), (p.id, source)


DOC: dict[str, Any] = {
    "id": "alpha",
    "version": 2,
    "summary": "Finds  leaders.[^1]",
    "hit": "Up.",
    "not_checked": "News.",
    "before_acting": ["Check feature.atr_pct.[^2]"],
    "related": [{"id": "beta", "reason": "the dip"}],
    "sources": [
        {"title": "A book", "url": "https://example.com/book", "note": "The dip."},
        {"title": "A paper", "note": "No page found."},
    ],
    "asks": {"adv": "Trades $50M a day", "close": "Closes above $5"},
}


def test_a_document_is_typed_and_a_missing_folder_has_nothing() -> None:
    found = load_guide_screeners(MemoryConfigStore({("site", FOLDER, "alpha"): DOC}))
    (alpha,) = found.screeners
    assert alpha.summary == "Finds leaders.[^1]"  # whitespace collapsed
    assert alpha.sources == (
        GuideSource("A book", "https://example.com/book", "The dip."),
        GuideSource("A paper", None, "No page found."),
    )
    assert alpha.version == 2
    assert alpha.related == (RelatedScreener("beta", "the dip"),)
    assert alpha.asks == (("adv", "Trades $50M a day"), ("close", "Closes above $5"))
    assert alpha.ask("close") == "Closes above $5" and alpha.ask("nope") is None
    assert found.get("alpha") is alpha and found.get("beta") is None
    assert load_guide_screeners(MemoryConfigStore({})) == GuideScreeners()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": "beta"}, "id: expected 'alpha'"),
        ({"version": None}, "version: required"),
        ({"version": 0}, "version"),
        ({"family": "trend"}, "unknown keys"),
        ({"summary": " "}, "summary: expected a non-empty string"),
        ({"line": "Up."}, "unknown keys"),  # the description is the preset's (ADR 0029)
        ({"summary": "Up.[^3]"}, r"marker \[\^3\] but there are 2 sources"),
        ({"summary": "Up.[^0]"}, r"marker \[\^0\]"),
        (
            {"sources": [{"title": "T", "url": "http://x.com", "note": "n"}]},
            "expected an https url",
        ),
        ({"sources": [{"title": "T", "note": "n", "extra": "x"}]}, "unknown keys"),
        ({"sources": ["A book"]}, "expected a list of tables"),
        (
            {"sources": [{"title": "T", "url": "https://x.com", "note": "n"}] * 2},
            "source urls",
        ),
        ({"before_acting": []}, "before_acting: expected one or more"),
        ({"related": [{"id": "alpha", "reason": "x"}]}, "not related to itself"),
        ({"related": [{"id": "b", "reason": "x"}] * 2}, "listed more than once"),
        ({"related": [{"id": "b"}]}, "reason: expected a non-empty string"),
        ({"related": {"id": "b"}}, "expected a list"),
        ({"asks": {"adv": ""}}, "adv: expected a non-empty string"),
        ({"asks": "adv"}, "expected a table"),
        ({"api_key": "x"}, "looks like a secret"),
    ],
)
def test_bad_documents_fail_naming_the_file(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        ScreenerProse.from_document("alpha", {**DOC, **change})


def test_every_screener_sits_in_the_folder_of_the_family_that_lists_it() -> None:
    """A folder per family keeps each under the 12-file cap: the file's folder is its family."""
    families = {f.id: f.presets for f in load_guide_sections(SHIPPED).families}
    files = list((REPO_ROOT / WHERE).glob("*/*.toml"))
    assert len({p.stem for p in files}) == len(files), "a screener id appears in two folders"
    placed = {p.stem: p.parent.name for p in files}
    assert not list((REPO_ROOT / WHERE).glob("*.toml")), "a screener goes in its family's folder"
    expected = {preset: fam for fam, presets in families.items() for preset in presets}
    assert placed == expected
