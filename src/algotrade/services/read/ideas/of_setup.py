"""One qualifying setup's picks for the served session (ADR 0083 decision 2): the picks of its
basis screener's run that the setup itself took, read through ``pick_edges.load_pick_edges`` (the
public read of ``results/edge_picks``; this module never names the table). The run's rows are the
candidates, the edge's own row says which counted and their place; a probe row says what the
night was when nobody counted (not a decision day, nothing picked, or not stored / unjudged, which
is UNKNOWN with its reason, never "no picks", ADR 0081 decision 6). A run whose rank follows
values the viewer's licences do not cover (``run_withheld``) yields no picks for them: the pick
is not listed and its rank never shown, only counted as dropped (ADR 0083 amendment (a))."""

from dataclasses import dataclass

from algotrade.config.user import SITE_USER
from algotrade.services.ideas.setup_rule import CandidatePick
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation import pick_edges
from algotrade.services.read.ideas.setups import QualifyingSetup
from algotrade.services.read.screens.results import run_withheld
from algotrade.services.read.screens.runs import ScreenerRun, load_latest_runs, run_picks
from algotrade.services.read.values import Unknown, UnknownCode

PICKED = "picked"
NOTHING_PICKED = "nothing_picked"
NOT_A_DECISION_DAY = "not_a_decision_day"
UNKNOWN = "unknown"
STATES = (PICKED, NOTHING_PICKED, NOT_A_DECISION_DAY, UNKNOWN)
PROBE = "~probe"  # an id no run holds: the edge's row says what the night was, whoever counted


@dataclass(frozen=True)
class SetupPickSet:
    """``state``: PICKED, NOTHING_PICKED, NOT_A_DECISION_DAY or UNKNOWN (``unknown`` says why);
    ``picks``: the setup's own picks, place 1 first; ``dropped``: picks a licence the viewer
    lacks keeps off their list; ``run``: the basis screener's run (None: it has none)."""

    setup: QualifyingSetup
    state: str
    unknown: Unknown | None
    run: ScreenerRun | None
    picks: tuple[CandidatePick, ...] = ()
    dropped: int = 0


def _unknown(setup: QualifyingSetup, ctx: ReadContext, text: str) -> Unknown:
    return Unknown(UnknownCode.NOT_STORED, run_cause(setup.edge.id, text, ctx.session.date))


def load_pick_set(ctx: ReadContext, setup: QualifyingSetup) -> SetupPickSet:
    """``setup``'s picks at ``ctx.session``."""
    found = load_latest_runs(ctx, [(SITE_USER, setup.basis_screener)])[
        (SITE_USER, setup.basis_screener)
    ]
    run = found.run
    if run is None:
        return SetupPickSet(setup, UNKNOWN, found.not_run, None)
    rows = run_picks(ctx, run)
    asked = [
        (str(i), str(d), n)
        for n, (i, d) in enumerate(zip(rows["instrument_id"], rows["decision"], strict=True), 1)
    ]
    found_edges = pick_edges.load_pick_edges(ctx, run, [*asked, (PROBE, "", 1)])
    probe = _own(found_edges.get(PROBE, ()), setup)
    if probe is None or probe.code in (pick_edges.NOT_STORED, pick_edges.UNJUDGED):
        text = f"{setup.edge.id} stored no picks for {ctx.session.date}"
        return SetupPickSet(setup, UNKNOWN, _unknown(setup, ctx, text), run)
    if probe.code == pick_edges.NOT_A_DECISION_DAY:
        return SetupPickSet(setup, NOT_A_DECISION_DAY, None, run)
    mine = sorted(
        (
            (e.place, iid)
            for iid, _, _ in asked
            if (e := _own(found_edges.get(iid, ()), setup)) is not None
            and e.counts
            and e.place is not None
        ),
    )
    if run_withheld(ctx, run):
        return SetupPickSet(setup, NOTHING_PICKED, None, run, (), len(mine))
    picks = tuple(CandidatePick(iid, setup.standing, place) for place, iid in mine)
    return SetupPickSet(setup, PICKED if picks else NOTHING_PICKED, None, run, picks)


def _own(
    found: tuple[pick_edges.PickEdge, ...], setup: QualifyingSetup
) -> pick_edges.PickEdge | None:
    return next((e for e in found if e.edge_id == setup.edge.id), None)
