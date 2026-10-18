"""The ideas researched but not built (ADR 0051; spec ``docs/ui/guide.md``, "Edges"): every idea
of the edge-idea catalogue that no edge document files (``config/site/guide/ideas/<family>.toml``,
``config.site.guide.ideas``; an idea ``filed_as`` an edge is not shown), each with the mechanism
it would rest on, the catalogue's verdict and build feasibility (published grades, never the
harness's: no idea here has been run), and one plain sentence on why it is not built. Grouped by
mechanism for the mechanism pages (``ideas_of``) and in the Guide's mechanism order, then the
catalogue's family and file order, for the section's index (``not_built``)."""

from dataclasses import dataclass

from algotrade.config.edges.document import MECHANISM_KINDS
from algotrade.config.site.guide.ideas import Idea, load_guide_ideas
from algotrade.services.read.context import Stores

VERDICT_TEXT = {
    "strong": "Strong",
    "promising": "Promising",
    "weak": "Weak",
    "decayed": "Decayed",
    "dead": "Dead",
    "not_graded": "Not graded",
}
FEASIBILITY_TEXT = {
    "data_ready": "Data ready",
    "needs_data": "Needs data",
    "needs_code": "Needs code",
    "out_of_scope": "Out of scope",
}
FEASIBILITY_TERM = "idea_feasibility"


@dataclass(frozen=True)
class GuideIdea:
    """An idea not built: ``mechanism`` (its page's id), ``verdict`` (``IDEA_VERDICTS``) with
    ``verdict_text``, ``feasibility_text`` (with the glossary term ``feasibility_term``) and
    ``why_not_built``."""

    id: str
    title: str
    mechanism: str
    verdict: str
    verdict_text: str
    feasibility_text: str
    feasibility_term: str
    why_not_built: str


def not_built(ctx: Stores) -> tuple[GuideIdea, ...]:
    """Every idea not filed as an edge: the Guide's mechanism order, then catalogue order."""
    unfiled = load_guide_ideas(ctx.configs).unfiled
    ordered = sorted(unfiled, key=lambda i: _rank(i.mechanism_kind))  # stable: file order kept
    return tuple(_idea(i) for i in ordered)


def ideas_of(ctx: Stores, mechanism_id: str) -> tuple[GuideIdea, ...]:
    """The ideas not built that rest on mechanism ``mechanism_id``, in catalogue order."""
    return tuple(i for i in not_built(ctx) if i.mechanism == mechanism_id)


def _rank(mechanism: str) -> int:
    return (
        MECHANISM_KINDS.index(mechanism) if mechanism in MECHANISM_KINDS else len(MECHANISM_KINDS)
    )


def _idea(i: Idea) -> GuideIdea:
    assert i.verdict is not None and i.feasibility is not None and i.why_not_built is not None
    return GuideIdea(
        id=i.id,
        title=i.title,
        mechanism=i.mechanism_kind,
        verdict=i.verdict,
        verdict_text=VERDICT_TEXT[i.verdict],
        feasibility_text=FEASIBILITY_TEXT[i.feasibility],
        feasibility_term=FEASIBILITY_TERM,
        why_not_built=i.why_not_built,
    )
