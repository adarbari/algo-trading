"""Every event class an edge schedule may trigger on, and every subtype of one, has its own Guide
term (ADR 0051, ADR 0053 amendment, EB H4): ``edge.schedule`` is a plain String, so
``guide_coverage.toml`` cannot map its values; this test keeps the closed set of classes and
subtypes (``EVENT_CLASSES``, ``EVENT_SUBTYPES``) and the Guide in step. A class is
``event_class_<class>``, a subtype ``event_class_<class>_<subtype>`` (a dot is an underscore)."""

from algotrade.config.edges.document import EVENT_CLASSES, EVENT_SUBTYPES, MARKET_TRIGGERS
from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT


def _expected() -> set[str]:
    classes = {f"event_class_{c}" for c in EVENT_CLASSES}
    subtypes = {
        f"event_class_{c}_{s.replace('.', '_')}" for c, subs in EVENT_SUBTYPES.items() for s in subs
    }
    return classes | subtypes


def test_every_event_class_and_subtype_has_its_own_guide_term() -> None:
    terms = {t.id for t in load_guide_glossary(FileConfigStore(REPO_ROOT / "config")).terms}
    missing = sorted(_expected() - terms)
    assert not missing, f"write a glossary term in config/site/guide/glossary/edges/: {missing}"
    stray = sorted(t for t in terms if t.startswith("event_class_") and t not in _expected())
    assert not stray, f"an event_class_ term for no class or subtype: {stray}"


def test_every_market_trigger_has_its_own_guide_term() -> None:
    """``on_market:<trigger>`` (ADR 0075): ``market_trigger_<trigger>``, and the family's own."""
    terms = {t.id for t in load_guide_glossary(FileConfigStore(REPO_ROOT / "config")).terms}
    expected = {f"market_trigger_{m}" for m in MARKET_TRIGGERS}
    assert not expected - terms, f"write a term in edge_events.toml: {sorted(expected - terms)}"
    assert "schedule_on_market" in terms
    stray = sorted(t for t in terms if t.startswith("market_trigger_") and t not in expected)
    assert not stray, f"a market_trigger_ term for no trigger: {stray}"
