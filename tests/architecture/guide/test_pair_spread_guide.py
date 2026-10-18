"""Every value the pair spread adds has a Guide entry (ADR 0051, ADR 0053 amendment, EB H9): the
``pair_spread`` kind, the ``PAIRED`` / ``AMBIGUOUS`` statuses of ``share_classes@v1`` and each
reason a name is excluded from a pair, so a value added to any of them fails here until its
words are written. The kind is also covered through ``EdgeSettings.kind`` in
``guide_coverage.toml``."""

import pytest

from algotrade.config.edges.document import OUTCOME_KINDS, PAIR_KIND
from algotrade.config.site.guide.glossary import GlossaryTerm, load_guide_glossary
from algotrade.features.rollups.reference.share_classes import STATUSES
from algotrade.services.evaluation.cross_section import hit
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

FIX = "write the term in config/site/guide/glossary/edges/edge_outcomes.toml"
REASONS = (
    hit.NO_SIBLING, hit.SIBLING_NOT_ELIGIBLE, hit.SIBLING_MISMATCH, hit.NO_SIBLING_ROW,
    hit.SIBLING_UNMEASURED,
)  # fmt: skip


def _terms() -> dict[str, GlossaryTerm]:
    glossary = load_guide_glossary(FileConfigStore(REPO_ROOT / "config", local=False))
    return {t.id: t for t in glossary.terms}


def test_the_pair_kind_is_an_outcome_kind() -> None:
    assert PAIR_KIND in OUTCOME_KINDS


def test_the_pair_spread_kind_has_a_term_that_points_at_the_pair_term() -> None:
    entry = _terms()["outcome_pair_spread"]
    assert entry.next, "a kind term needs a next"
    assert "share_class_pair" in entry.see_also, FIX


@pytest.mark.parametrize("status", STATUSES)
def test_each_share_class_status_is_explained_by_the_pair_term(status: str) -> None:
    found = _terms()
    assert "share_class_pair" in found, FIX
    assert status in found["share_class_pair"].body, f"{status}: not in the term; {FIX}"


def test_the_pair_term_says_when_a_name_is_left_out_of_a_pair() -> None:
    """The reasons are the code's words (``no_sibling`` ...); the Guide says them in plain words,
    so the test holds the count: a reason added to ``hit.py`` and to ``REASONS`` fails until the
    term's exclusion sentence is reviewed (it names each case)."""
    body = _terms()["outcome_pair_spread"].body
    for phrase in ("no sibling", "not in the universe", "does not name it back", "no return"):
        assert phrase in body, f"the pair term does not say {phrase!r}; {FIX}"
    assert len(REASONS) == 5
