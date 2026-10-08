"""What a screener picks, and who was eligible, at one session (ADR 0053): both read only what
was known at the session, never an outcome (the harness joins those, ``harness.py``).

``screen_variant`` runs a resolved screener through ``services.screening.run.screen_session``
and returns its rows best-first: a rule screen by its stored rank (score, tie-break, id), a
Python screener by (score, id). ``eligible`` is the edge's universe at the session: the base
rate and the decile spread are taken over it."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.views.feature_view import FeatureView
from algotrade.data import StoreReader
from algotrade.data.reference import InstrumentView
from algotrade.engines.screening.runner import RunCoverage
from algotrade.engines.selection.evaluate import evaluate_selection
from algotrade.services.screening.run import screen_session
from algotrade.services.selection import fields_view, select
from algotrade.strategies.screeners.base import Decision


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


@dataclass(frozen=True)
class Eligible:
    ids: frozenset[str]
    pre_snapshot: bool


def screen_variant(reader: StoreReader, config: ResolvedConfig, session: date) -> RankedRun:
    """``config`` screened at ``session`` on what was known then."""
    screened = screen_session(reader, config, session)
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
        pre_snapshot=screened.universe.pre_snapshot,
        coverage=screened.run.coverage,
        snapshot=screened.universe.snapshot_date,
        scores=scores,
    )


def eligible(reader: StoreReader, universe: Selection, session: date) -> Eligible:
    """The ids ``universe`` selects at ``session`` (the edge's own, over the site's features)."""
    chosen = select(reader, universe, session)
    return Eligible(frozenset(chosen.instruments), chosen.pre_snapshot)


class SelectionReads:
    """``select`` for several universes at one session with one read of the fields: the last
    (fields, session) read is kept, so universes over the same fields at the same session
    (the edge's variants, asked one after the other) read the partitions once. The result is
    ``select``'s."""

    def __init__(self, reader: StoreReader):
        self._reader = reader
        self._last: tuple[tuple[tuple[str, ...], date], FeatureView, InstrumentView] | None = None

    def eligible(self, universe: Selection, session: date) -> Eligible:
        fields = {r.field for r in universe.where.rules()}
        if universe.order_by:
            fields.add(universe.order_by)
        key = (tuple(sorted(fields)), session)
        if self._last is None or self._last[0] != key:
            view, source = fields_view(self._reader, key[0], session)
            self._last = (key, view, source)
        _, view, source = self._last
        chosen = evaluate_selection(universe, view)
        return Eligible(frozenset(chosen.instruments), source.pre_snapshot)
