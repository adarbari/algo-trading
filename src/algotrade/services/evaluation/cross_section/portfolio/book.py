"""A ``portfolio_return`` outcome's book at one decision session D (ADR 0074): the harness's own
rule, which the stored picks share (``edge_picks``, ADR 0088 decision 9). ``book_at`` is one
screener's book before the overlays; ``held_book`` the book held, after them (an ensemble
averages its members' ``book_at`` first). Both read only what was known at D: the vol field at D
and, for ``vol_target``, the trailing returns of sessions ending at D. Earlier books feed only the
turnover cost, never the weights, so the book at D needs no replay of earlier sessions."""

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from algotrade.config.edges.document import Edge
from algotrade.services.evaluation.cross_section.picks import RankedRun
from algotrade.services.evaluation.cross_section.portfolio.overlays import apply_overlays
from algotrade.services.evaluation.cross_section.portfolio.weights import (
    Weights,
    average_books,
    book_weights,
)

if TYPE_CHECKING:
    from algotrade.services.evaluation.cross_section.reads.session import SessionReads


def book_at(
    edge: Edge, reads: "SessionReads", run: RankedRun, pickable: frozenset[str], day: date
) -> tuple[Weights, str]:
    """The book one screener's run gives at D: the qualified names among the pickable ones, best
    first, ``top_k`` of them, weighted (``portfolio/weights.py``); ``()`` and the reason when it
    cannot be formed. No picks is a cash book."""
    o = edge.outcome
    chosen = [i for i in run.qualified if i in pickable]
    picks = chosen if edge.top_k is None else chosen[: edge.top_k]
    vols = reads.numbers(o.vol_field, frozenset(picks), day) if o.vol_field and picks else {}
    return book_weights(picks, o.weighting, run.scores, vols, edge.top_k)


def held_book(
    edge: Edge, reads: "SessionReads", day: date, books: Sequence[Weights]
) -> tuple[Weights, float | None, float | None, str]:
    """``(weights, book_vol, risk_off, reason)``: the book held at D from one screener's book or
    an ensemble's members' (averaged), after the outcome's overlays (``apply_overlays``)."""
    weights = books[0] if len(books) == 1 else average_books(books)
    return apply_overlays(edge.outcome, reads, day, weights)
