"""``config/site/guide/glossary.toml`` (ADR 0051): the fitness tests over the shipped file first
(every term the spec lists is written; every ``see_also`` id is a term; ``short`` is one
sentence; every catalogue name in the prose is in the catalogue), then the loader's shape
checks."""

import re
from typing import Any

import pytest

from algotrade.config.site.guide.glossary import (
    FOLDER,
    NAME,
    GlossaryTerm,
    GuideGlossary,
    load_guide_glossary,
)
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import open_stores
from algotrade.services.read.guide.prose import name_tokens
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
WHERE = "config/site/guide/glossary.toml"
# The terms docs/ui/guide.md section 3 and the GD6 brief name: the app's words, the rule
# grammar, the decisions a result shows and the regime gate.
SPEC_TERMS = {
    "session", "knowledge_time", "unknown", "not_run", "run", "selection", "draft", "op",
    "mode", "hard", "soft", "score_mode", "tolerance", "on_miss", "watch", "liquidity_risk",
    "event_risk", "paused", "gating_criterion", "near_miss", "preset", "playbook",
}  # fmt: skip
# A sentence ends at ., ! or ? followed by a space and a capital (not "e.g. a" or "$5.50").
SENTENCE_BREAK = re.compile(r"[.!?] +[A-Z]")


def test_every_term_the_spec_lists_is_written() -> None:
    written = {t.id for t in load_guide_glossary(SHIPPED).terms}
    assert not SPEC_TERMS - written, f"{WHERE}: write [[term]] {sorted(SPEC_TERMS - written)}"


def test_every_see_also_is_a_term() -> None:
    glossary = load_guide_glossary(SHIPPED)
    ids = {t.id for t in glossary.terms}
    for term in glossary.terms:
        unknown = [other for other in term.see_also if other not in ids]
        assert not unknown, f"{WHERE} {term.id} see_also: no such term {unknown}"


def test_short_is_one_sentence() -> None:
    for term in load_guide_glossary(SHIPPED).terms:
        assert term.short.endswith(".") and not SENTENCE_BREAK.search(term.short), (
            f"{WHERE} {term.id} short: one sentence, ending with a full stop (the hover)"
        )


def test_every_catalogue_name_in_the_prose_is_in_the_catalogue() -> None:
    site = open_stores(StoreReader(MemoryBackend()), SHIPPED, UserContext(SITE_USER))
    fields = catalog_of(site.features).fields
    for term in load_guide_glossary(SHIPPED).terms:
        named = {n for text in (term.short, term.body) for n in name_tokens(text)}
        unknown = sorted(n for n in named if not n[0].isdigit() and n not in fields)
        assert not unknown, f"{WHERE} {term.id} names fields not in the catalogue: {unknown}"


TERM: dict[str, Any] = {
    "id": "alpha",
    "term": "Alpha",
    "short": "The first.",
    "body": "Comes  before\n beta.",
    "see_also": ["beta"],
}


def test_a_document_is_typed_and_a_missing_file_has_no_terms() -> None:
    doc = {"term": [TERM, {**TERM, "id": "beta", "term": "Beta", "see_also": []}]}
    found = load_guide_glossary(MemoryConfigStore({("site", FOLDER, NAME): doc}))
    alpha, beta = found.terms
    assert alpha == GlossaryTerm("alpha", "Alpha", "The first.", "Comes before beta.", ("beta",))
    assert beta.see_also == ()
    assert found.get("beta") is beta and found.get("gamma") is None
    assert load_guide_glossary(MemoryConfigStore({})) == GuideGlossary()


@pytest.mark.parametrize(
    ("terms", "message"),
    [
        ([{**TERM, "id": ""}], "id: expected a non-empty string"),
        ([{**TERM, "short": " "}], "short: expected a non-empty string"),
        ([{**TERM, "colour": "red"}], "unknown keys"),
        ([{**TERM, "see_also": ["alpha"]}], "does not refer to itself"),
        ([{**TERM, "see_also": ["b", "b"]}], "see_also ids listed more than once"),
        ([TERM, {**TERM, "term": "Other"}], "term ids listed more than once"),
        ([TERM, {**TERM, "id": "other", "term": "ALPHA"}], "terms listed more than once"),
        ([{**TERM, "api_key": "x"}], "looks like a secret"),
    ],
)
def test_bad_documents_fail_naming_the_file(terms: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        GuideGlossary.from_document({"term": terms})


def test_terms_must_be_a_list_of_tables() -> None:
    with pytest.raises(ConfigurationError, match=r"guide/glossary.toml term: expected a list"):
        GuideGlossary.from_document({"term": {"id": "alpha"}})
    with pytest.raises(ConfigurationError, match="unknown keys"):
        GuideGlossary.from_document({"terms": []})
