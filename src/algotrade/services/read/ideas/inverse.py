"""The inverse reads of the Ideas picks (ADR 0083 decision 2; plan V2, V5): a setup's picks
tonight and the setups that picked an instrument. Both read through ``of_setup`` (the public
``pick_edges`` read), for qualifying setups only: a setup that does not qualify (no ``works`` /
``promising`` verdict readable at the session) has no picks here, never an empty list. The
licence filter of ``of_setup`` applies, so a pick the viewer may not see is in neither."""

from dataclasses import dataclass

from algotrade.services.ideas.setup_rule import setup_key
from algotrade.services.read.context import ReadContext
from algotrade.services.read.ideas.of_setup import SetupPickSet, load_pick_set
from algotrade.services.read.ideas.setups import load_session_setups


@dataclass(frozen=True)
class InstrumentSetup:
    """A qualifying setup that picked the instrument: its ``place``, ``tab`` and ``level``."""

    edge_id: str
    edge_name: str
    tab: str
    level: str
    place: int


def load_picks_of_setup(ctx: ReadContext, edge_id: str) -> SetupPickSet | None:
    """``edge_id``'s picks at ``ctx.session``; None unless the setup qualifies for Ideas."""
    found = next((s for s in load_session_setups(ctx).qualifying if s.edge.id == edge_id), None)
    return None if found is None else load_pick_set(ctx, found)


def load_setups_of_instrument(ctx: ReadContext, instrument_id: str) -> tuple[InstrumentSetup, ...]:
    """The qualifying setups that picked ``instrument_id`` at ``ctx.session``, strongest first."""
    out = []
    for setup in sorted(load_session_setups(ctx).qualifying, key=lambda s: setup_key(s.standing)):
        for p in load_pick_set(ctx, setup).picks:
            if p.instrument_id == instrument_id:
                verdict = setup.summary.verdict
                out.append(
                    InstrumentSetup(setup.edge.id, setup.edge.name, setup.tab, verdict, p.place)
                )
    return tuple(out)
