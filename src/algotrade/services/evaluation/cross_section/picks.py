"""What a screener picks, and who was eligible, at one session (ADR 0053): both read only what
was known at the session, never an outcome (the harness joins those, ``harness.py``).

``screen_variant`` runs a resolved screener through ``services.screening.run.screen_session``
and returns its rows best-first: a rule screen by its stored rank (score, tie-break, id), a
Python screener by (score, id). ``eligible`` is the edge's universe at the session: the base
rate and the decile spread are taken over it. ``long_picks`` is the long leg's one rule and
``side_picks`` a ``short`` or ``long_short`` outcome's (each leg ranked by the edge's own score, a
short ascending), shared by the harness and the stored picks (``edge_picks``)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

from algotrade.config.edges.document import Edge
from algotrade.config.edges.identity import LONG, SHORT
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.views.feature_view import FeatureView
from algotrade.data import StoreReader
from algotrade.data.listings.identity import PROXY, TODAY_FLAG
from algotrade.data.reference import InstrumentView
from algotrade.engines.screening.runner import RunCoverage
from algotrade.engines.selection.evaluate import SelectionResult, evaluate_selection
from algotrade.services.evaluation.cross_section.historical import require_liquidity_rule
from algotrade.services.licences import HARNESS_ALL
from algotrade.services.screening.run import screen_session
from algotrade.services.selection import fields_view, select, selection_fields
from algotrade.strategies.screeners.base import Decision

# A short or long-short leg is ranked by score only when at least this share of the eligible names
# carries one; the rest are ``unscored`` and never ranked (recent listings lack a year of history,
# but a session where the signal was not computed at all has no honest bottom).
MIN_SCORE_COVERAGE = 0.8


@dataclass(frozen=True)
class RankedRun:
    """One screener's run at one session: ``ranking`` the ids with a decision (UNKNOWN and
    SKIPPED rows have no rank) best-first, ``qualified`` the QUALIFIED ones in that order
    (a name the regime gate PAUSED is not one). ``scores`` is the edge's own score per
    instrument (the rank-by field, higher is better; None when not stored): the deciles are
    taken over it, never over the rule rank, which puts rejected names after qualified ones."""

    session: date
    ranking: tuple[str, ...]
    qualified: tuple[str, ...]
    pre_snapshot: bool
    coverage: RunCoverage
    snapshot: date  # the universe snapshot the screen read (the run itself is not kept)
    scores: Mapping[str, float]
    identity: Mapping[str, int] = field(default_factory=dict)  # historical: ranked names by path


@dataclass(frozen=True)
class Eligible:
    ids: frozenset[str]
    pre_snapshot: bool
    identity: Mapping[str, int] = field(default_factory=dict)  # historical: names by path


def screen_variant(reader: StoreReader, config: ResolvedConfig, session: date) -> RankedRun:
    """``config`` screened at ``session`` on what was known then."""
    screened = screen_session(reader, config, session, historical=True, held=HARNESS_ALL)
    if screened.selected.historical and config.selection is not None:
        require_liquidity_rule(config.selection)
    if screened.rules is not None:
        rows = sorted(screened.rules.rows, key=lambda r: r.rank)
        ranked = [(r.instrument_id, r.decision) for r in rows]
        spec = screened.rules.spec
        if spec.tie_break is None:
            raise ConfigurationError("an edge screener needs [rank].tie_break")
        sign = 1.0 if spec.tie_break_descending else -1.0
        scores = {r.instrument_id: sign * r.tie_break for r in rows if r.tie_break is not None}
    else:
        by_score = sorted(
            screened.run.rows, key=lambda r: (r.score is None, -(r.score or 0.0), r.instrument_id)
        )
        ranked = [(r.instrument_id, r.decision) for r in by_score]
        scores = {r.instrument_id: r.score for r in screened.run.rows if r.score is not None}
    ranked = [(i, d) for i, d in ranked if d.processed]
    return RankedRun(
        session=session,
        ranking=tuple(i for i, _ in ranked),
        qualified=tuple(i for i, d in ranked if d is Decision.QUALIFIED),
        pre_snapshot=screened.universe.pre_snapshot and not screened.selected.historical,
        coverage=screened.run.coverage,
        snapshot=screened.universe.snapshot_date,
        scores=scores,
        identity=_paths(screened.selected, [i for i, _ in ranked]),
    )


def long_picks(edge: Edge, qualified: Sequence[str], pickable: frozenset[str]) -> list[str]:
    """The long leg of ``edge`` at one session, place 1 first: the screener's qualified names (best
    first) that are pickable (inside the edge's universe, and an event schedule's event names),
    the first ``top_k`` of them (none: every one). The one rule the harness (``measuring``), the
    paper record (``forward.signals``) and the stored picks (``edge_picks``, ADR 0081) share."""
    chosen = [i for i in qualified if i in pickable]
    return chosen if edge.top_k is None else chosen[: edge.top_k]


def side_picks(
    edge: Edge,
    scores: Mapping[str, float],
    pickable: frozenset[str],
    adv: Mapping[str, float | None],
    adv_floor: float | None,
    hold: int | None = None,
) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """The legs of a ``short`` or ``long_short`` outcome at one session (ADR 0053 amendment,
    outcome sides), each ``(side, ids)`` with rank 1 first: the scored pickable names ranked by
    score (never by the rule rank; a name with no score is in neither leg, as the deciles
    leave it out), the long leg the best ``top_k``, the short leg the worst ``top_k`` among the
    names whose 20-day dollar volume at D is known and at least ``adv_floor`` (the microcap short
    cannot be done by an individual: ``capacity_adv_floor_usd``; unknown volume is not liquid).
    Also the ids of a ``short`` outcome's buy/hold band, the shortable names ranked ``top_k + 1``
    to ``hold`` (none for any other side)."""
    assert edge.top_k is not None  # the document requires it for a side other than long
    ranked = sorted((i for i in pickable if i in scores), key=lambda i: (-scores[i], i))
    floor = adv_floor or 0.0
    shortable = [i for i in ranked if (volume := adv.get(i)) is not None and volume >= floor]
    short = shortable[::-1][: edge.top_k]
    if edge.outcome.side == SHORT:
        below = shortable[::-1][edge.top_k : hold] if hold is not None else []
        return [(SHORT, short)], below
    return [(LONG, ranked[: edge.top_k]), (SHORT, short)], []


def _paths(chosen: SelectionResult, ids: Sequence[str]) -> dict[str, int]:
    """Historical sessions only: how many of ``ids`` took each identity path (empty otherwise)."""
    if not chosen.historical:
        return {}
    proxy = len(set(ids) & chosen.proxy_ids)
    return {TODAY_FLAG: len(ids) - proxy, PROXY: proxy}


def _eligible(chosen: SelectionResult, universe: Selection, pre_snapshot: bool) -> Eligible:
    if chosen.historical:
        require_liquidity_rule(universe)
    ids = frozenset(chosen.instruments)
    return Eligible(ids, pre_snapshot and not chosen.historical, _paths(chosen, tuple(ids)))


def eligible(reader: StoreReader, universe: Selection, session: date) -> Eligible:
    """The ids ``universe`` selects at ``session`` (the edge's own, over the site's features).
    Before the first reference snapshot: the listing history's names alive then, with today's
    optionable flag or the universe's liquidity floor (``historical.py``)."""
    chosen = select(reader, universe, session, historical=True, held=HARNESS_ALL)
    return _eligible(chosen, universe, chosen.pre_snapshot)


class SelectionReads:
    """``select`` for several universes at one session with one read of the fields: the last
    (fields, session) read is kept, so universes over the same fields at the same session
    (the edge's variants, asked one after the other) read the partitions once. The result is
    ``select``'s."""

    def __init__(self, reader: StoreReader):
        self._reader = reader
        self._last: tuple[tuple[tuple[str, ...], date], FeatureView, InstrumentView] | None = None

    def eligible(self, universe: Selection, session: date) -> Eligible:
        key = (tuple(selection_fields(universe)), session)
        if self._last is None or self._last[0] != key:
            view, source = fields_view(
                self._reader, key[0], session, historical=True, held=HARNESS_ALL
            )
            self._last = (key, view, source)
        _, view, source = self._last
        chosen = evaluate_selection(universe, view)
        identity = source.identity
        chosen = replace(
            chosen,
            historical=identity is not None,
            proxy_ids=frozenset() if identity is None else identity.proxy_ids,
        )
        return _eligible(chosen, universe, source.pre_snapshot)
