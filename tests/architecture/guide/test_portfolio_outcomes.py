"""Every value a portfolio_return outcome adds to an edge document has a Guide entry (ADR 0051,
ADR 0074): each weighting, the blended benchmark (the ``benchmark`` base and a ``mix:`` benchmark),
the ``CASH`` pick, the kind itself, the ensemble and its members and each out-of-sample haircut
class. A value added to ``WEIGHTINGS``, ``BASES`` or ``OOS_CLASSES`` fails here until its term is
written and mapped."""

import pytest

from algotrade.config.edges.document import BASES, OUTCOME_KINDS
from algotrade.config.edges.portfolio import (
    BENCHMARK_BASE,
    OOS_CLASSES,
    PORTFOLIO_KIND,
    WEIGHTINGS,
)
from algotrade.config.site.guide.glossary import GlossaryTerm, load_guide_glossary
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

WEIGHTING_TERMS = {
    "equal": "weighting_equal",
    "inverse_vol": "weighting_inverse_vol",
    "score": "weighting_score",
}
BASE_TERMS = {  # the other bases have terms of their own (event schedules, time-series edges)
    "event": None,
    "universe": None,
    "out_of_window": None,
    BENCHMARK_BASE: "blended_benchmark",
}
OOS_TERMS = {"trend": "oos_haircut"}  # an ``oos_class`` and the term explaining its haircut
OTHER_TERMS = {
    PORTFOLIO_KIND: "outcome_portfolio_return",
    "CASH": "cash_position",
    "ensemble": "edge_ensemble",
    "member": "ensemble_member",
    **OOS_TERMS,
}
FIX = "write the term in config/site/guide/glossary/edges/edge_outcomes.toml and map it here"


def _terms() -> dict[str, GlossaryTerm]:
    glossary = load_guide_glossary(FileConfigStore(REPO_ROOT / "config", local=False))
    return {t.id: t for t in glossary.terms}


def test_every_weighting_base_and_haircut_class_is_mapped_to_a_term() -> None:
    assert set(WEIGHTING_TERMS) == set(WEIGHTINGS), FIX
    assert set(OOS_TERMS) == set(OOS_CLASSES), FIX
    assert set(BASE_TERMS) == set(BASES), FIX
    assert PORTFOLIO_KIND in OUTCOME_KINDS


@pytest.mark.parametrize(
    "value,term",
    [
        *WEIGHTING_TERMS.items(),
        *((v, t) for v, t in BASE_TERMS.items() if t is not None),
        *OTHER_TERMS.items(),
    ],
)
def test_each_portfolio_value_has_a_guide_entry_that_links_the_outcome(
    value: str, term: str
) -> None:
    found = _terms()
    assert term in found, f"{value}: no Guide term {term!r}; {FIX}"
    entry = found[term]
    assert entry.next, f"{term}: a state-like term needs a next"
    if term not in ("outcome_portfolio_return", "oos_haircut"):
        assert "outcome_portfolio_return" in entry.see_also
