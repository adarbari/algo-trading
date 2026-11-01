"""Which edges a pick of a screener's run counts toward (``PickEdge``), read from what each edge
itself took (ADR 0081), never decided from the run's own ranking: ``results/edge_picks`` holds,
per site edge and screener it lists, the picks the harness's one rule gave at the session (the
screener's qualified names inside the edge's universe, the first ``top_k``, ``picks.long_picks``)
or why there are none (not a decision day of its schedule, an outcome that is not the screener's
long picks, the data missing). A row counts toward an edge when its id is in that list, ``place``
its place there. Read for the served session only (ADR 0036): a run of another session, a session
the step has not stored, an edge with no row (a user's own edge, a new edge, a skipped night)
says ``not_stored``, never an older night's picks. A row the regime gate PAUSED is ``paused`` and
one whose rank is withheld by a licence ``withheld``: neither is counted or placed. An edge
whose evidence the viewer lacks the licence of is not listed at all, so it adds no pick (ADR 0084
decision 1: ``evidence_licence``). It reads no
outcome: it says what the edge would take, not what it has already earned."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from algotrade.config.user import SITE_USER
from algotrade.services.read.context import ReadContext, partition
from algotrade.services.read.evaluation.edges import load_edges, parsed_edges
from algotrade.services.read.screens.runs import ScreenerRun
from algotrade.services.read.values import Unknown

TABLE = "results/edge_picks"
COUNTS = "counts"
PAUSED = "paused"
NOT_COUNTED = "not_counted"
NOT_A_DECISION_DAY = "not_a_decision_day"
UNJUDGED = "unjudged"
NOT_STORED = "not_stored"
WITHHELD = "withheld"
CODES = (COUNTS, PAUSED, NOT_COUNTED, NOT_A_DECISION_DAY, UNJUDGED, NOT_STORED, WITHHELD)
PICKED = "picked"  # the stored row's status when the edge decided (``edge_picks.night``)
NOT_DECISION_DAY = "not_decision_day"
HELD_BACK = "PAUSED"


@dataclass(frozen=True)
class PickEdge:
    """One edge that lists the screener and what it did with one pick: ``counts`` and the ``code``
    that says why (``CODES``); ``top_k``: the edge's cut (None: every qualified name); ``place``:
    the pick's place among the edge's own picks (None: not one of them)."""

    edge_id: str
    edge_name: str
    counts: bool
    code: str
    top_k: int | None
    place: int | None


def _stored(ctx: ReadContext, run: ScreenerRun) -> dict[tuple[str, str], tuple[str, list[str]]]:
    """The served session's rows by (edge, screener): ``(status, pick ids)``; empty when the
    session has none stored or ``run`` is another session's."""
    if (
        run.session != ctx.session.date or run.owner != SITE_USER
    ):  # a viewer's own run: not the site's
        return {}
    found = partition(ctx, TABLE)
    if isinstance(found, Unknown) or found.empty:
        return {}
    site = found[found["user_id"] == SITE_USER]
    return {
        (str(r.edge_id), str(r.screener)): (str(r.status), _ids(r.pick_ids))
        for r in site.itertuples()
    }


def _ids(value: Any) -> list[str]:
    """A stored list column's ids (a null list reads as none)."""
    return [] if value is None or isinstance(value, float) else [str(i) for i in value]


def _judge(
    stored: tuple[str, list[str]] | None, iid: str, decision: str, rank: int | None
) -> tuple[str, int | None]:
    if rank is None:
        return WITHHELD, None
    if stored is None:
        return NOT_STORED, None
    status, picks = stored
    if status == NOT_DECISION_DAY:
        return NOT_A_DECISION_DAY, None
    if status != PICKED:  # unjudged, or skipped for missing data
        return (UNJUDGED if status == UNJUDGED else NOT_STORED), None
    if iid in picks:
        return COUNTS, picks.index(iid) + 1
    return (PAUSED if decision == HELD_BACK else NOT_COUNTED), None


def load_pick_edges(
    ctx: ReadContext, run: ScreenerRun, picks: Sequence[tuple[str, str, int | None]]
) -> Mapping[str, tuple[PickEdge, ...]]:
    """For each ``(instrument id, decision, rank)`` of ``picks`` (rows of ``run``), the edges that
    list ``run.config_id`` with what each did with it, edges by id; empty for a screener no edge
    lists."""
    edges = [e for e in parsed_edges(ctx, ctx.user.user_id) if run.config_id in e.screeners]
    if not edges or not picks:
        return {}
    shown = {e.id for e in load_edges(ctx, [e.id for e in edges])}  # evidence the viewer may see
    edges = [e for e in edges if e.id in shown]
    stored = _stored(ctx, run)
    out: dict[str, tuple[PickEdge, ...]] = {}
    for iid, decision, rank in picks:
        found = []
        for e in sorted(edges, key=lambda x: x.id):
            row = stored.get((e.id, run.config_id)) if e.owner == SITE_USER else None
            code, place = _judge(row, iid, decision, rank)
            found.append(PickEdge(e.id, e.name, code == COUNTS, code, e.top_k, place))
        out[iid] = tuple(found)
    return out
