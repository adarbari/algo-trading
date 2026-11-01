"""The Ideas list of a tab from the picks of qualifying setups (ADR 0083 decision 2 and its
amendment of 2026-11-01): ``load_setup_picks(ctx, tab)``. Every qualifying setup of the tab
contributes its own picks (``of_setup``), the one rule ranks them (``rank``: a ticker several
setups picked is one idea at its best position, the others in ``also_in``), and the list is cut
at ``CAP`` after the licence filter, which has already dropped what the viewer may not see. Each
idea is served from its best pick's stored result (values, regime, watch-outs).

``state`` is ``LISTED`` when any setup qualifies for the tab (a night that picks nothing is then
an empty list with the reason on each group, never a fall back) and ``UNPROVEN`` when none does:
the page then shows the tab's pool of screeners, ``Query.ideas(tab:)``, labelled Unproven, with
the left-out counts beside it. A setup left out for want of a readable verdict, and the picks a
licence dropped, are counted by kind in ``left_out`` (counts never name a pick or a setup)."""

from dataclasses import dataclass
from datetime import date

from algotrade.services.ideas.setup_rule import RULE_VERSION, CandidatePick, rank_picks, setup_key
from algotrade.services.read.context import ReadContext
from algotrade.services.read.ideas import of_setup
from algotrade.services.read.ideas.setups import (
    LEFT_OUT_KINDS,
    QualifyingSetup,
    SessionSetups,
    load_session_setups,
)
from algotrade.services.read.instruments.identity import Instrument
from algotrade.services.read.screens.ideas import (
    IdeaMetric,
    display_metrics,
    earnings_first,
    watch_out,
)
from algotrade.services.read.screens.results import ScreenResult, load_results
from algotrade.services.read.values import Unknown

CAP = 15
LISTED = "listed"
UNPROVEN = "unproven"
LICENCE = "licence"
STATES = (LISTED, UNPROVEN)
LEFT_OUT_ALL = (*LEFT_OUT_KINDS, LICENCE)  # every kind of ``LeftOut``


@dataclass(frozen=True)
class LeftOut:
    """``count`` setups (or, for ``licence``, picks) left out for ``kind``."""

    kind: str
    count: int


@dataclass(frozen=True)
class AlsoIn:
    """Another setup that picked the ticker, at its ``place`` there."""

    edge_id: str
    edge_name: str
    place: int


@dataclass(frozen=True)
class SetupIdea:
    """A ticker at its best pick: the ``setup_id`` it ranks under, its ``place`` there and the
    stored ``result`` of that pick (None: its row could not be read)."""

    rank: int
    instrument_id: str
    instrument: Instrument | None
    setup_id: str
    place: int
    also_in: tuple[AlsoIn, ...]
    result: ScreenResult | None
    metrics: tuple[IdeaMetric, ...]
    watch_out: tuple[str, ...]


@dataclass(frozen=True)
class SetupGroup:
    """A qualifying setup of the tab with what it picked: ``state`` as ``of_setup`` (UNKNOWN
    carries ``unknown``), ``picked``: its picks on the viewer's list before the cap, ``shown``:
    how many of the ideas under the cap rank under it."""

    edge_id: str
    name: str
    level: str
    lift_pts: float | None
    oos_trades: int | None
    basis_screener: str
    basis_horizon: int | None
    state: str
    unknown: Unknown | None
    picked: int
    shown: int


@dataclass(frozen=True)
class SetupPicks:
    """The tab's list: ``groups`` (setups, strongest evidence first), ``ideas`` (best first, at
    most ``CAP``), ``total``: ideas before the cap, ``left_out`` counts by kind."""

    session: date
    tab: str
    state: str
    rule_version: int
    groups: tuple[SetupGroup, ...]
    ideas: tuple[SetupIdea, ...]
    total: int
    left_out: tuple[LeftOut, ...]


def _left_out(found: SessionSetups, tab: str, dropped: int) -> tuple[LeftOut, ...]:
    counts = [LeftOut(k, len(found.left_out.get((tab, k), ()))) for k in LEFT_OUT_KINDS]
    counts.append(LeftOut(LICENCE, dropped))
    return tuple(c for c in counts if c.count)


def _group(pick_set: of_setup.SetupPickSet, shown: int) -> SetupGroup:
    s = pick_set.setup
    return SetupGroup(
        s.edge.id,
        s.edge.name,
        s.summary.verdict,
        s.summary.lift_pts,
        s.summary.oos_trades,
        s.basis_screener,
        s.basis_horizon,
        pick_set.state,
        pick_set.unknown,
        len(pick_set.picks),
        shown,
    )


def load_setup_picks(ctx: ReadContext, tab: str) -> SetupPicks:
    """``tab``'s Ideas at ``ctx.session``: see the module docstring."""
    found = load_session_setups(ctx)
    setups = sorted(found.of_tab(tab), key=lambda s: s.edge.id)
    sets = [of_setup.load_pick_set(ctx, s) for s in setups]
    dropped = sum(p.dropped for p in sets)
    left = _left_out(found, tab, dropped)
    if not setups:
        return SetupPicks(ctx.session.date, tab, UNPROVEN, RULE_VERSION, (), (), 0, left)
    ranked = rank_picks([p for ps in sets for p in ps.picks])
    shown = ranked[:CAP]
    runs_of = {ps.setup.edge.id: ps.run for ps in sets}
    names = {s.edge.id: s.edge.name for s in setups}
    wanted: dict[str, list[str]] = {}
    for idea in shown:
        run = runs_of[idea.best.setup.edge_id]
        if run is not None:
            wanted.setdefault(run.run_id, []).append(idea.instrument_id)
    runs = [r for r in runs_of.values() if r is not None]
    results = load_results(ctx, wanted, list({r.run_id: r for r in runs}.values()))
    early = earnings_first(ctx, [i.instrument_id for i in shown])
    ideas = []
    for idea in shown:
        run = runs_of[idea.best.setup.edge_id]
        result = None if run is None else results.get((run.run_id, idea.instrument_id))
        ideas.append(
            SetupIdea(
                idea.rank,
                idea.instrument_id,
                None if result is None else result.instrument,
                idea.best.setup.edge_id,
                idea.best.place,
                _also_in(idea.also_in, names),
                result,
                () if result is None else display_metrics(result),
                () if result is None else watch_out(result, idea.instrument_id in early),
            )
        )
    under = {s.edge.id: sum(1 for i in shown if i.best.setup.edge_id == s.edge.id) for s in setups}
    groups = sorted(
        (_group(ps, under[ps.setup.edge.id]) for ps in sets),
        key=lambda g: _group_key(g, setups),
    )
    return SetupPicks(
        ctx.session.date, tab, LISTED, RULE_VERSION, tuple(groups), tuple(ideas), len(ranked), left
    )


def _also_in(also: tuple[CandidatePick, ...], names: dict[str, str]) -> tuple[AlsoIn, ...]:
    return tuple(AlsoIn(p.setup.edge_id, names[p.setup.edge_id], p.place) for p in also)


def _group_key(
    group: SetupGroup, setups: list[QualifyingSetup]
) -> tuple[int, int, float, int, str]:
    return setup_key(next(s.standing for s in setups if s.edge.id == group.edge_id))
