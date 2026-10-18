"""Every value an edge document's ``[outcome]`` can name has a Guide entry (ADR 0051, ADR 0053):
each ``option_model_pnl`` structure (and the ``model`` basis label) is explained by a glossary
term, so a value added to ``MODEL_STRUCTURES`` fails here until its entry is written and mapped.
The kinds themselves are covered through ``EdgeSettings.kind`` in ``guide_coverage.toml``."""

import pytest

from algotrade.config.edges.document import MODEL_BASIS, MODEL_STRUCTURES, STRUCTURES
from algotrade.config.site.guide.glossary import GlossaryTerm, load_guide_glossary
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

STRUCTURE_TERMS = {
    "atm_straddle_long": "straddle_long",
    "atm_straddle_short": "straddle_short",
    "delta_hedged_atm": "delta_hedged_straddle",
    "delta_hedged_atm_short": "delta_hedged_straddle_short",
}
BASIS_TERMS = {MODEL_BASIS: "model_basis"}
FIX = "write the term in config/site/guide/glossary/edges/edge_outcomes.toml and map it here"


def _terms() -> dict[str, GlossaryTerm]:
    glossary = load_guide_glossary(FileConfigStore(REPO_ROOT / "config", local=False))
    return {t.id: t for t in glossary.terms}


def test_every_model_structure_is_mapped_to_a_term() -> None:
    assert set(STRUCTURE_TERMS) == set(MODEL_STRUCTURES), FIX


@pytest.mark.parametrize("value,term", [*STRUCTURE_TERMS.items(), *BASIS_TERMS.items()])
def test_each_model_value_has_a_guide_entry_that_names_it(value: str, term: str) -> None:
    found = _terms()
    assert term in found, f"{value}: no Guide term {term!r}; {FIX}"
    entry = found[term]
    assert entry.next, f"{term}: a state-like term needs a next"
    assert "outcome_option_model_pnl" in entry.see_also


def test_the_expires_otm_structures_are_not_model_structures() -> None:
    assert not set(STRUCTURES) & set(MODEL_STRUCTURES)
