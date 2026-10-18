"""Every value an edge document's ``[outcome]`` can name has a Guide entry (ADR 0051, ADR 0053):
each ``option_model_pnl`` structure (and the ``model`` basis label) is explained by a glossary
term, so a value added to ``MODEL_STRUCTURES`` fails here until its entry is written and mapped.
The kinds themselves are covered through ``EdgeSettings.kind`` in ``guide_coverage.toml``."""

import pytest

from algotrade.config.edges.chain import CHAIN_BASIS, CHAIN_STRUCTURES, MODEL_STRUCTURES, STRUCTURES
from algotrade.config.edges.document import MODEL_BASIS
from algotrade.config.site.guide.glossary import GlossaryTerm, load_guide_glossary
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.schemas import OPTION_PNL_REASONS, OPTION_PNL_STATUSES
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


CHAIN_TERMS = {
    "atm_straddle_long": "straddle_long",
    "atm_straddle_short": "straddle_short",
    "delta_hedged_atm": "delta_hedged_straddle",
    "delta_hedged_atm_short": "delta_hedged_straddle_short",
    "put_short": "put_short",
}
STATUS_TERMS = {"COMPLETE": "chain_outcome_complete", "UNMEASURED": "chain_outcome_unmeasured"}


def test_every_chain_structure_status_reason_and_the_basis_has_a_term() -> None:
    assert set(CHAIN_TERMS) == set(CHAIN_STRUCTURES), FIX
    assert set(STATUS_TERMS) == set(OPTION_PNL_STATUSES), FIX
    found = _terms()
    for value, term in {**CHAIN_TERMS, **STATUS_TERMS, CHAIN_BASIS: "chain_basis"}.items():
        assert term in found, f"{value}: no Guide term {term!r}; {FIX}"
    for term in ("chain_outcome_complete", "chain_outcome_unmeasured", "chain_basis", "put_short"):
        assert found[term].next, f"{term}: a state-like term needs a next"
    body = found["chain_outcome_unmeasured"].body
    missing = [code for code in OPTION_PNL_REASONS if code not in body]
    assert not missing, f"the chain_outcome_unmeasured entry does not explain {missing}"
    assert "outcome_option_pnl" in found["chain_basis"].see_also
