"""Which site setups qualify for Ideas at the served session, and on which tab (ADR 0083
decision 2 and its amendment of 2026-11-01): a site setup whose stored verdict headline is
``works`` or ``promising``, read point in time (the canonical run committed on or before the
session, ``bounded``), with the screener the verdict rests on (``basis_screener``, ADR 0065). The
tab is the kind of the setup's position: any option leg is Premium, shares are Stocks (a shape
that is no position, ``position_of`` None, is Stocks unless it names an option ``structure``).

A setup with a committed run but no usable headline is not listed and is counted by kind, so a
stale or missing verdict never turns the page into Unproven silently: ``NEWER_RUN`` (its only
committed runs came after the session), ``NO_VERDICT`` (no stored row for the run, a fingerprint
that differs, or an unreadable row) and ``NO_BASIS`` (a row from before ``basis_screener``). A
setup that never had a run is untested, not left out. A setup whose evidence the viewer lacks the
licence of is not listed and not counted (``load_edges`` gates it, ADR 0084)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from algotrade.config.edges.positions.templates import load_templates, position_of
from algotrade.config.user import SITE_USER
from algotrade.services.ideas.setup_rule import LEVEL_ORDER, SetupStanding
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge, load_edges, parsed_edges
from algotrade.services.read.evaluation.verdict import EdgeSummary, load_stored_summary


class Tab(StrEnum):
    """An Ideas tab: Stocks (share setups) or Premium (option setups)."""

    STOCKS = "stocks"
    PREMIUM = "premium"


STOCKS = Tab.STOCKS.value
PREMIUM = Tab.PREMIUM.value
TABS = (STOCKS, PREMIUM)
NEWER_RUN = "newer_run"
NO_VERDICT = "no_verdict"
NO_BASIS = "no_basis"
LEFT_OUT_KINDS = (NEWER_RUN, NO_VERDICT, NO_BASIS)


@dataclass(frozen=True)
class QualifyingSetup:
    """A site setup that qualifies: its read document, ``tab``, headline and the basis screener
    and holding period the headline rests on."""

    edge: Edge
    tab: str
    summary: EdgeSummary
    basis_screener: str
    basis_horizon: int | None
    top_k: int | None

    @property
    def standing(self) -> SetupStanding:
        s = self.summary
        return SetupStanding(self.edge.id, s.verdict, s.lift_pts, s.oos_trades)


@dataclass(frozen=True)
class SessionSetups:
    """``qualifying``: the setups that qualify, by id order; ``left_out``: per tab and kind the
    ids of the setups listed by ``LEFT_OUT_KINDS`` that did not."""

    qualifying: tuple[QualifyingSetup, ...] = ()
    left_out: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)

    def of_tab(self, tab: str) -> tuple[QualifyingSetup, ...]:
        return tuple(s for s in self.qualifying if s.tab == tab)


def tab_of(ctx: ReadContext, outcome: object) -> str:
    """The tab of a setup with this ``outcome``: Premium when its position has an option leg."""
    named = position_of(outcome)
    if named is None:
        return PREMIUM if getattr(outcome, "structure", None) is not None else STOCKS
    templates = load_templates(ctx.configs)
    option = any(t in templates and templates[t].has_option for t in named)
    return PREMIUM if option else STOCKS


def in_tab(ctx: ReadContext, tab: str) -> Callable[[str], bool]:
    """Whether a screener (by config id) is in ``tab``'s Unproven section (ADR 0083 amendment
    (a)): the tab of the site setups that list it, a screener behind setups of both kinds in
    both, one that implements none (the viewer's own included) in Stocks."""
    found: dict[str, set[str]] = {}
    for doc in parsed_edges(ctx, ctx.user.user_id):
        if doc.owner == SITE_USER:
            for screener in doc.screeners:
                found.setdefault(screener, set()).add(tab_of(ctx, doc.outcome))
    return lambda config_id: tab in found.get(config_id, {STOCKS})


def load_session_setups(ctx: ReadContext) -> SessionSetups:
    """The qualifying setups of ``ctx.session`` and the left-out ones, for the viewer."""
    visible = {e.id: e for e in load_edges(ctx) if not e.mine}
    qualifying: list[QualifyingSetup] = []
    left: dict[tuple[str, str], list[str]] = {}
    for doc in sorted(parsed_edges(ctx, ctx.user.user_id), key=lambda d: d.id):
        edge = visible.get(doc.id)
        if edge is None or doc.owner != SITE_USER:
            continue
        tab = tab_of(ctx, doc.outcome)
        found = _qualify(ctx, edge, tab, doc.top_k)
        if isinstance(found, QualifyingSetup):
            if found.summary.verdict in LEVEL_ORDER:
                qualifying.append(found)
        elif found is not None:
            left.setdefault((tab, found), []).append(edge.id)
    return SessionSetups(
        tuple(qualifying),
        {k: tuple(v) for k, v in left.items()},
    )


def _qualify(
    ctx: ReadContext, edge: Edge, tab: str, top_k: int | None
) -> QualifyingSetup | str | None:
    """The setup with its headline, a ``LEFT_OUT_KINDS`` kind, or None: untested (no run)."""
    if runs.load_canonical_run(ctx, edge, bounded=True).run is None:
        newer = runs.load_canonical_run(ctx, edge).run
        return NEWER_RUN if newer is not None else None
    summary = load_stored_summary(ctx, edge, bounded=True)
    if summary is None:
        return NO_VERDICT
    if summary.basis_screener is None:
        return NO_BASIS
    return QualifyingSetup(edge, tab, summary, summary.basis_screener, summary.basis_horizon, top_k)
