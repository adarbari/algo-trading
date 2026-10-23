"""Which edges a pick of a screener's run counts toward (``PickEdge``), decided here, never in the
browser: the edge harness takes a screener's QUALIFIED names in stored rank order and keeps the
first ``top_k`` (``services/evaluation/cross_section/picks.py``), so a row counts toward an edge
that lists the screener when it is QUALIFIED and its place among the run's qualified rows is
within the edge's ``top_k`` (no ``top_k``: every qualified name). A name the regime gate PAUSED or
that failed a rule is a pick the edge does not count; a row whose rank is withheld (a licence)
is not judged. Only an edge that picks long on every session is judged: a short or long-short edge
ranks shortable names by its own score, and a month-end, calendar or event edge counts nothing on
other sessions, so those say ``unjudged`` and never ``counts``. The edge's own universe is not
applied here (the Guide says so). Reads the run's cached rows and the edge documents, nothing
else; it does not read an outcome, so it says what the edge would take, not what it has
already earned."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.edges import parsed_edges
from algotrade.services.read.screens.runs import ScreenerRun, run_rows

COUNTS = "counts"
PAUSED = "paused"
NOT_QUALIFIED = "not_qualified"
BELOW_TOP_K = "below_top_k"
WITHHELD = "withheld"
UNJUDGED = "unjudged"
CODES = (COUNTS, PAUSED, NOT_QUALIFIED, BELOW_TOP_K, WITHHELD, UNJUDGED)
EVERY_SESSION = "every_session"
LONG = "long"
QUALIFIED = "QUALIFIED"
HELD_BACK = "PAUSED"


@dataclass(frozen=True)
class PickEdge:
    """One edge that lists the screener and what it does with one pick: ``counts`` and the
    ``code`` that says why (``CODES``); ``top_k``: the edge's cut (None: every qualified name);
    ``place``: the pick's place among the run's qualified rows (None: not qualified or not
    judged)."""

    edge_id: str
    edge_name: str
    counts: bool
    code: str
    top_k: int | None
    place: int | None


def _judge(
    decision: str, rank: int | None, qualified: np.ndarray, top_k: int | None
) -> tuple[str, int | None]:
    if rank is None:
        return WITHHELD, None
    if decision == HELD_BACK:
        return PAUSED, None
    if decision != QUALIFIED:
        return NOT_QUALIFIED, None
    place = int(np.searchsorted(qualified, rank, side="right"))
    if top_k is not None and place > top_k:
        return BELOW_TOP_K, place
    return COUNTS, place


def load_pick_edges(
    ctx: ReadContext, run: ScreenerRun, picks: Sequence[tuple[str, str, int | None]]
) -> dict[str, tuple[PickEdge, ...]]:
    """For each ``(instrument id, decision, rank)`` of ``picks`` (rows of ``run``), the edges
    that list ``run.config_id`` with what each does with it, edges by id; empty for a screener no
    edge lists."""
    edges = [e for e in parsed_edges(ctx, ctx.user.user_id) if run.config_id in e.screeners]
    if not edges or not picks:
        return {}
    rows = run_rows(ctx, run)
    qualified = np.sort(rows.loc[rows["decision"] == QUALIFIED, "rank"].to_numpy(dtype=float))
    out: dict[str, tuple[PickEdge, ...]] = {}
    for iid, decision, rank in picks:
        found = []
        for e in sorted(edges, key=lambda x: x.id):
            if e.schedule != EVERY_SESSION or e.outcome.side != LONG:
                code, place = UNJUDGED, None
            else:
                code, place = _judge(decision, rank, qualified, e.top_k)
            found.append(PickEdge(e.id, e.name, code == COUNTS, code, e.top_k, place))
        out[iid] = tuple(found)
    return out
