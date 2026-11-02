"""A setup's state at the served session (ADR 0088 decision 16, design 2.3, v1): ``ON``, ``OFF``,
``PAUSED`` or ``UNKNOWN``, each with its reason, computed on read by one pure, versioned rule
(``decide_state``) over two stored facts and never stored itself:

- the verdict: the stored headline of the site setup's canonical run committed on or before the
  session (``load_stored_summary(bounded=True)``, as Ideas reads it, ADR 0083 decision 2);
- the night: what the setup stored in ``results/edge_picks`` for the session
  (``pick_edges.load_edge_night``), whose ``gate_closed`` status is its gate closed.

**ON**: the verdict is works or promising and the gate is open (or the setup has none). **OFF**:
the verdict is anything else that was judged (not working, not enough data, a diagnostic).
**PAUSED**: the verdict is good and the gate is closed (stand aside), with the gate's reason.
**UNKNOWN**: no usable stored verdict (none, another fingerprint, waiting on data), or a gated setup
whose gate the night does not say (not stored, skipped, unjudged), with an ``Unknown`` whose cause
chain only an admin reads (ADR 0056). The gate is checked on the setup's decision days only (the
nightly writer asks it after the schedule), so a good setup's other sessions read ON with that
said. Per-regime rows are display only: no state mines the slices (design M4). A setup whose
evidence the viewer lacks the licence of is not listed at all, so it has no state for them (N6);
a user's own setup stores no nightly picks, so its state is UNKNOWN (NOT_APPLICABLE)."""

from dataclasses import dataclass
from enum import StrEnum

from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation import pick_edges
from algotrade.services.read.evaluation.edges import Edge, parsed_edges
from algotrade.services.read.evaluation.verdict import (
    PROMISING,
    WAITING,
    WORKS,
    load_stored_summary,
)
from algotrade.services.read.values import Unknown, UnknownCode

STATE_VERSION = 1  # bump on any change to ``decide_state``


class SetupStateCode(StrEnum):
    """A setup's state at one session; each has its Guide entry."""

    ON = "ON"
    OFF = "OFF"
    PAUSED = "PAUSED"
    UNKNOWN = "UNKNOWN"


GOOD = (WORKS, PROMISING)  # the verdicts a setup is ON with (ADR 0083 decision 2)


@dataclass(frozen=True)
class SetupState:
    """``state`` of ``edge_id`` at the session; ``reason``: the public sentence (empty for
    UNKNOWN, whose ``unknown`` says why)."""

    edge_id: str
    state: SetupStateCode
    reason: str
    unknown: Unknown | None = None


@dataclass(frozen=True)
class _Decided:
    state: SetupStateCode
    reason: str


# The gate's part of a good setup's state, by the night's stored status (any other: UNKNOWN).
_GATE = {
    pick_edges.PICKED: (SetupStateCode.ON, "the gate is open"),
    pick_edges.NOT_DECISION_DAY: (SetupStateCode.ON, "the gate is checked on decision days"),
    pick_edges.GATE_CLOSED: (SetupStateCode.PAUSED, "the gate is closed"),
}


def decide_state(verdict: str | None, gated: bool, night: pick_edges.EdgeNight | None) -> _Decided:
    """The rule: ``verdict`` is the stored headline's level (None: no usable stored headline),
    ``gated`` whether the setup declares a gate, ``night`` what it stored at the session."""
    if verdict is None or verdict == WAITING:
        why = "no stored verdict for the session" if verdict is None else "the verdict is waiting"
        return _Decided(SetupStateCode.UNKNOWN, why)
    if verdict not in GOOD:
        return _Decided(SetupStateCode.OFF, f"the verdict is {verdict.replace('_', ' ')}")
    if not gated:
        return _Decided(SetupStateCode.ON, f"the verdict is {verdict}; the setup has no gate")
    if night is None or night.status not in _GATE:
        why = "no picks stored for the session" if night is None else night.reason
        return _Decided(SetupStateCode.UNKNOWN, why or f"the night was {night and night.status}")
    state, gate = _GATE[night.status]
    if state == SetupStateCode.PAUSED:  # the gate's own reason, in field terms (never a value)
        return _Decided(state, night.reason or gate)
    return _Decided(state, f"the verdict is {verdict}; {gate}")


def load_setup_state(ctx: ReadContext | None, edge: Edge) -> SetupState | None:
    """``setup_state_at`` for the served session (None: no session is served)."""
    return None if ctx is None else setup_state_at(ctx, edge)


def setup_state_at(ctx: ReadContext, edge: Edge) -> SetupState:
    """``edge``'s state at ``ctx.session``."""
    if edge.mine:
        why = "a setup's state is published for site setups, which store nightly picks"
        return _unknown(ctx, edge, UnknownCode.NOT_APPLICABLE, why)
    doc = next((e for e in parsed_edges(ctx, ctx.user.user_id) if e.id == edge.id), None)
    gated = doc is not None and doc.gate is not None
    summary = load_stored_summary(ctx, edge, bounded=True)
    night = pick_edges.load_edge_night(ctx, edge.id) if gated else None
    decided = decide_state(None if summary is None else summary.verdict, gated, night)
    if decided.state == SetupStateCode.UNKNOWN:
        code = UnknownCode.NOT_RUN if summary is None else UnknownCode.NOT_STORED
        return _unknown(ctx, edge, code, decided.reason)
    return SetupState(edge.id, decided.state, decided.reason)


def _unknown(ctx: ReadContext, edge: Edge, code: UnknownCode, why: str) -> SetupState:
    cause = run_cause(edge.id, why, ctx.session.date)
    return SetupState(edge.id, SetupStateCode.UNKNOWN, "", Unknown(code, cause))
