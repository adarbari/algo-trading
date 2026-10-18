"""Every measure an ``excess_return`` outcome can name has a Guide entry (ADR 0051, ADR 0053
amendment EB H11): a value added to ``EXCESS_MEASURES`` fails here until its term is written and
mapped, and the term says the figure is factor-neutral where the measure is."""

import pytest

from algotrade.config.edges.document import EXCESS_MEASURES
from algotrade.config.site.guide.glossary import GlossaryTerm, load_guide_glossary
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

MEASURE_TERMS = {"residual_return": "outcome_residual_return"}
FIX = "write the term in config/site/guide/glossary/edges/edge_outcomes.toml and map it here"


def _terms() -> dict[str, GlossaryTerm]:
    glossary = load_guide_glossary(FileConfigStore(REPO_ROOT / "config", local=False))
    return {t.id: t for t in glossary.terms}


def test_every_excess_measure_is_mapped_to_a_term() -> None:
    assert set(MEASURE_TERMS) == set(EXCESS_MEASURES), FIX


@pytest.mark.parametrize("value,term", MEASURE_TERMS.items())
def test_each_excess_measure_has_a_guide_entry(value: str, term: str) -> None:
    found = _terms()
    assert term in found, f"{value}: no Guide term {term!r}; {FIX}"
    entry = found[term]
    assert entry.next, f"{term}: a state-like term needs a next"
    assert "factor-neutral" in (entry.term + entry.short + entry.body).lower()
    assert "outcome_excess_return" in entry.see_also
