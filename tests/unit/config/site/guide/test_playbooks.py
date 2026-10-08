"""``config/site/guide/playbooks/<id>.toml`` (ADR 0051): the fitness tests over the shipped
files first (every site preset has exactly one playbook and every playbook a preset; ``asks``
names exactly the criteria of the preset's latest version; every related id is a site
playbook; every catalogue name written in the prose is in the catalogue), then the loader's
shape checks."""

from typing import Any

import pytest

from algotrade.config.site.guide.playbooks import (
    FOLDER,
    GuidePlaybooks,
    PlaybookProse,
    RelatedPlaybook,
    load_guide_playbooks,
)
from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.guide.playbooks import site_playbooks
from algotrade.services.read.guide.prose import name_tokens
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import SCREENERS, FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
WHERE = "config/site/guide/playbooks"


@pytest.fixture(scope="module")
def site() -> StoreContext:
    return open_stores(StoreReader(MemoryBackend()), SHIPPED, UserContext(SITE_USER))


def test_every_site_preset_has_exactly_one_playbook_and_every_playbook_a_preset() -> None:
    presets = SHIPPED.names("site", SCREENERS)
    playbooks = SHIPPED.names("site", FOLDER)
    assert playbooks == presets, (
        f"write one {WHERE}/<id>.toml per site rule-screen preset: missing "
        f"{sorted(set(presets) - set(playbooks))}, no such preset "
        f"{sorted(set(playbooks) - set(presets))}"
    )


def test_asks_names_exactly_the_criteria_of_the_latest_preset_version(site: StoreContext) -> None:
    prose = load_guide_playbooks(SHIPPED)
    playbooks = site_playbooks(site)
    assert [p.id for p in playbooks] and len(playbooks) == len(SHIPPED.names("site", SCREENERS))
    for playbook in playbooks:
        written = prose.get(playbook.id)
        assert written is not None, playbook.id
        assert written.version == playbook.spec.version, (
            f"{WHERE}/{playbook.id}.toml was written for version {written.version}, the preset "
            f"is at {playbook.spec.version}: re-read its prose and thresholds, then raise version"
        )
        criteria = [c.id for c in playbook.spec.criteria]
        asks = [name for name, _ in written.asks]
        assert sorted(asks) == sorted(criteria), (
            f"{WHERE}/{playbook.id}.toml [asks]: one entry per criterion of version "
            f"{playbook.spec.version}: missing {sorted(set(criteria) - set(asks))}, no such "
            f"criterion {sorted(set(asks) - set(criteria))}"
        )


def test_every_related_id_is_a_site_playbook() -> None:
    presets = set(SHIPPED.names("site", SCREENERS))
    for playbook in load_guide_playbooks(SHIPPED).playbooks:
        unknown = [r.id for r in playbook.related if r.id not in presets]
        assert not unknown, f"{WHERE}/{playbook.id}.toml related: no such playbook {unknown}"


def test_every_catalogue_name_in_the_prose_is_in_the_catalogue(site: StoreContext) -> None:
    fields = catalog_of(site.features).fields
    for p in load_guide_playbooks(SHIPPED).playbooks:
        texts = [p.summary, p.hit, p.not_checked, *p.before_acting, *(a for _, a in p.asks)]
        named = {n for text in texts for n in name_tokens(text) if not n[0].isdigit()}
        unknown = sorted(n for n in named if n not in fields)
        assert not unknown, f"{WHERE}/{p.id}.toml names fields not in the catalogue: {unknown}"


DOC: dict[str, Any] = {
    "id": "alpha",
    "version": 2,
    "summary": "Finds  leaders.",
    "hit": "Up.",
    "not_checked": "News.",
    "before_acting": ["Check feature.atr_pct."],
    "related": [{"id": "beta", "reason": "the dip"}],
    "sources": ["A book"],
    "asks": {"adv": "Trades $50M a day", "close": "Closes above $5"},
}


def test_a_document_is_typed_and_a_missing_folder_has_nothing() -> None:
    found = load_guide_playbooks(MemoryConfigStore({("site", FOLDER, "alpha"): DOC}))
    (alpha,) = found.playbooks
    assert alpha.summary == "Finds leaders."  # whitespace collapsed
    assert alpha.version == 2
    assert alpha.related == (RelatedPlaybook("beta", "the dip"),)
    assert alpha.asks == (("adv", "Trades $50M a day"), ("close", "Closes above $5"))
    assert alpha.ask("close") == "Closes above $5" and alpha.ask("nope") is None
    assert found.get("alpha") is alpha and found.get("beta") is None
    assert load_guide_playbooks(MemoryConfigStore({})) == GuidePlaybooks()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": "beta"}, "id: expected 'alpha'"),
        ({"version": None}, "version: required"),
        ({"version": 0}, "version"),
        ({"family": "trend"}, "unknown keys"),
        ({"summary": " "}, "summary: expected a non-empty string"),
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
        PlaybookProse.from_document("alpha", {**DOC, **change})


def test_every_playbook_sits_in_the_folder_of_the_family_that_lists_it() -> None:
    """A folder per family keeps each under the 12-file cap: the file's folder is its family."""
    families = {f.id: f.presets for f in load_guide_sections(SHIPPED).families}
    placed = {p.stem: p.parent.name for p in (REPO_ROOT / WHERE).glob("*/*.toml")}
    assert not list((REPO_ROOT / WHERE).glob("*.toml")), "a playbook goes in its family's folder"
    expected = {preset: fam for fam, presets in families.items() for preset in presets}
    assert placed == expected
