"""One decision session's statistic of one variant (ADR 0053, ADR 0074): the names of a variant, the
scored outcomes (``_outcomes``), the screener and ensemble statistic (``_stat``) and the
portfolio_return book's value (``_valued``). Split from ``measuring.py`` (at its line cap),
behaviour unchanged."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.edges.identity import LONG, LONG_SHORT, SHORT
from algotrade.config.edges.portfolio import CASH, PORTFOLIO_KIND, blend
from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.config.edges.verdict import OptionCosts
from algotrade.engines.screening.runner import RunCoverage
from algotrade.quant.edges.statistics import moments
from algotrade.services.evaluation.cross_section.baselines.variant import (
    Variant,
    _Scope,
)
from algotrade.services.evaluation.cross_section.hit import (
    INVALID_IMPLIED_VOL,
    NO_IMPLIED_VOL,
    UNMEASURED,
    Pairs,
    apply_outcome,
    needs_implied_vol,
    needs_pairs,
    short_view,
)
from algotrade.services.evaluation.cross_section.measures import (
    SessionStat,
    band_picks,
    decile_means,
    held_counts,
)
from algotrade.services.evaluation.cross_section.picks import (
    MIN_SCORE_COVERAGE,
    RankedRun,
    long_picks,
    side_picks,
)
from algotrade.services.evaluation.cross_section.portfolio.book import book_at, held_book
from algotrade.services.evaluation.cross_section.portfolio.session import (
    cash_return,
    portfolio_stat,
    ranking_deciles,
    session_value,
    window_returns,
)
from algotrade.services.evaluation.cross_section.portfolio.weights import (
    Weights,
    average_books,
)
from algotrade.services.evaluation.cross_section.reads.entry import Entered
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from algotrade.services.evaluation.cross_section.reporting.report_containment import window_end
from algotrade.services.evaluation.cross_section.scoring.pick_rows import _picks
from algotrade.services.evaluation.cross_section.sessions import Leg
from algotrade.services.evaluation.evidence.shapes import roc_moments

# A stale universe stays measured (it is flagged pre_snapshot); partial or empty screens are not.
# A session is measured only when at least ``picks.MIN_SCORE_COVERAGE`` of the eligible names
# carries the edge's score. The screen's own coverage (``DEFAULT_MIN_COVERAGE``) is another check.
MEASURED_COVERAGE = (RunCoverage.COMPLETE, RunCoverage.UNIVERSE_INCOMPLETE)


@dataclass(frozen=True)
class Names:
    """The names of one edge variant at one decision session: ``ids`` the base (the rate and
    the deciles are over them), ``pickable`` those a pick may be."""

    ids: frozenset[str]
    pickable: frozenset[str]


def names_for(edge: Edge, eligible: frozenset[str], event_names: frozenset[str] | None) -> Names:
    """The base and the pickable names: an event schedule narrows them to the event's names
    (``base = "event"``; ``picks = "universe"`` keeps every eligible name pickable)."""
    pickable = (
        eligible if event_names is None or edge.picks == "universe" else event_names & eligible
    )
    ids = (
        (eligible if event_names is None else event_names & eligible)
        if edge.base == "event"
        else eligible
    )
    return Names(ids, pickable)


def _outcomes(
    scope: _Scope,
    session: SessionReads,
    leg: Leg,
    horizon: int,
    rows: pd.DataFrame,
    eligible: frozenset[str],
    ids: frozenset[str],
    option_costs: OptionCosts | None = None,
) -> pd.DataFrame:
    """The stored outcomes of ``ids`` scored by the edge's outcome (``apply_outcome``), indexed
    by instrument; ``excluded`` is non-empty for a name that does not count. It depends only on
    the scope, the horizon and D (``rows`` are that horizon's at the entry), so it is kept."""
    day = leg.decision

    def score() -> pd.DataFrame:
        inside = rows[rows["instrument_id"].isin(ids)]
        implied = (
            session.implied(scope.iv_field, eligible, day)
            if needs_implied_vol(scope.edge)
            else None
        )
        pairs = (
            Pairs(
                session.siblings(scope.edge.outcome.pair_field or "", eligible, day), eligible, rows
            )
            if needs_pairs(scope.edge)
            else None
        )
        return apply_outcome(scope.edge, inside, implied, pairs, option_costs).set_index(
            "instrument_id"
        )

    return session.outcomes(scope.key, horizon, day, score)


def _stat(
    scope: _Scope,
    session: SessionReads,
    variant: Variant,
    leg: Leg,
    horizon: int,
    rows: pd.DataFrame,
    event_names: frozenset[str] | None,
    costs: Sequence[float],
    adv_floor: float | None = None,
    option_costs: OptionCosts | None = None,
    entered: Entered | None = None,
) -> SessionStat:
    """One variant at one decision session: ``rows`` are the stored outcomes at the entry
    session (``entered``, an entry condition's: each entered name's row at its own S, the rest
    counted by reason). The eligible names, the screen, the implied vol and the ADV are at D.
    ``event_names`` (an event schedule): the picks are the qualified names within them, and the
    base is them (``base = "event"``) or every eligible name. ``costs``: the site's cost grid
    (bp), whose hits a return outcome's leg also counts. ``adv_floor``: the least 20-day dollar
    volume of a name a short leg may hold (``picks.side_picks``); ``option_costs``: an
    ``option_pnl`` edge's levels and commission."""
    edge, day = scope.edge, leg.decision
    if variant.members:
        return _ensemble_stat(scope, session, variant, leg, horizon, rows, event_names)
    run, eligible = session.run(variant, day), session.eligible(scope.universe, day)
    if (
        run is None or run.coverage not in MEASURED_COVERAGE
    ):  # read incomplete data: not measured, counted
        return SessionStat(session=day, regime=session.label(day), excluded_coverage=1)
    names = names_for(scope.edge, eligible, event_names)
    if edge.outcome.kind == PORTFOLIO_KIND:
        return _portfolio_stat(scope, session, run, names, leg, horizon, rows)
    pickable, ids = names.pickable, names.ids
    scored = {i: v for i, v in run.scores.items() if i in ids}
    thin = len(scored) < MIN_SCORE_COVERAGE * len(ids)  # too few scores to rank: no deciles
    res = _outcomes(scope, session, leg, horizon, rows, eligible, ids, option_costs)
    counted = res[res["excluded"] == ""]
    adv = session.adv(eligible, day)
    side = edge.outcome.side
    hold = edge.outcome.hold_rank  # a buy/hold band: the names ranked top_k + 1 .. hold are stored
    if side == LONG:
        in_universe = [i for i in run.qualified if i in eligible]
        chosen = [i for i in in_universe if i in pickable]
        legs = [(LONG, long_picks(edge, chosen, pickable))]
        below = chosen[edge.top_k : hold] if hold is not None and edge.top_k else []
    else:  # a short leg is ranked by score: too few scores and there is no honest bottom
        if thin:  # fail closed: the session is not measured, as an incomplete screen is not
            return SessionStat(session=day, regime=session.label(day), excluded_coverage=1)
        in_universe = []
        legs, below = side_picks(edge, run.scores, pickable, adv, adv_floor, hold)
    picks = [i for _, ids_ in legs for i in ids_]
    pick_set = set(picks)
    unmeasured = set(res.index[res["excluded"] == UNMEASURED])  # a window over a bad bar (ADR 0061)
    lost = [i for i in picks if i in unmeasured]
    if picks and len(lost) * 2 > len(picks):  # most picks unmeasured: the session is not measured
        return SessionStat(session=day, regime=session.label(day), excluded_coverage=1)
    have = set(res.index)
    held = entered.reasons if entered is not None else {}  # names the entry condition kept out
    views = {LONG: counted, SHORT: counted if side == LONG else short_view(res).loc[counted.index]}
    lead = SHORT if side == SHORT else LONG  # the leg ``pick_values`` hold; the base is its view
    base = views[lead]
    got = [i for i in legs[0][1] if i in base.index] if legs else []
    short_got = [i for i in legs[1][1] if i in views[SHORT].index] if side == LONG_SHORT else []
    no_iv = set(res.index[res["excluded"].isin((NO_IMPLIED_VOL, INVALID_IMPLIED_VOL))])
    implied = (
        session.implied(scope.iv_field, eligible, day)  # cached by ``_outcomes``
        if needs_implied_vol(edge)
        else {}
    )
    ranked = (
        []
        if thin
        else sorted((i for i in scored if i in counted.index), key=lambda i: (-scored[i], i))
    )
    deciles = decile_means(counted.loc[ranked, "oriented"].to_list()) if ranked else ()
    frames = session.level_frames(
        scope.key, scope.edge, horizon, leg.decision, rows, ids, costs, option_costs
    )
    column = "short_hit" if side == SHORT else "hit"
    levels = [frame[column] for frame in frames]
    at_levels = frames if option_costs is not None and edge.outcome.kind == CHAIN_KIND else ()
    all_got = got + short_got
    return SessionStat(
        session=day,
        regime=session.label(day),
        pick_values=tuple(float(v) for v in base.loc[got, "oriented"]),
        pick_hits=int(base.loc[got, "hit"].sum()),
        rest=moments(base.loc[~base.index.isin(pick_set), "oriented"].to_numpy(dtype=float)),
        base_hits=int(base["hit"].sum()),
        top_decile=deciles[0] if deciles else None,
        spread=deciles[0] - deciles[-1] if deciles else None,
        deciles=deciles,
        ranked=len(ranked),
        unscored=0 if thin else len(ids) - len(scored),
        excluded_score_coverage=int(thin),
        excluded_missing=sum(
            1 for i in picks if i in have and i not in counted.index and i not in unmeasured
        ),
        excluded_unmeasured=len(lost),
        unmeasured_base=len(unmeasured),
        delisted=int(counted.loc[all_got, "delisted"].sum()),
        pre_snapshot=run.pre_snapshot,
        outside_universe=len(run.qualified) - len(in_universe) if side == LONG else 0,
        no_entry_bar=len(ids - have - held.keys()),
        **held_counts(held, ids),  # names an entry condition or a case kept out, by reason
        pick_reference=tuple(float(v) for v in counted.loc[got, "reference"].dropna()),
        pick_touches=int(counted.loc[got, "touch"].fillna(0).sum()),
        no_implied_vol=sum(1 for i in picks if i in no_iv),
        implied_stored=any(v is not None for v in implied.values()),
        siblings_stored=_siblings_stored(edge, session, eligible, day),
        picks=tuple(
            p
            for side_, ids_ in legs
            for p in _picks(
                scope.edge,
                ids_,
                run.scores,
                res,
                rows,
                adv,
                side_,
                leg.entry,
                window_end(leg.entry, horizon),
                at_levels,
                option_costs,
                entered,
                horizon,
            )
        ),
        base_hits_at=tuple(int(hits.sum()) for hits in levels),
        pick_hits_at=tuple(int(hits.loc[got].sum()) for hits in levels),
        band=band_picks(below, (edge.top_k or 0) + 1, base["oriented"].to_dict()),
        base_roc=roc_moments(edge, rows, counted, leg.entry, option_costs),
        short_values=(
            tuple(float(v) for v in views[SHORT].loc[short_got, "oriented"])
            if side == LONG_SHORT
            else None
        ),
    )


def _siblings_stored(
    edge: Edge, session: SessionReads, eligible: frozenset[str], day: date
) -> bool:
    """Whether a ``pair_spread``'s ``pair_field`` has a value for some eligible name at D (true
    for every other outcome): a field stored for no name would read as a quiet ``no_sibling``."""
    if not needs_pairs(edge):
        return True
    siblings = session.siblings(edge.outcome.pair_field or "", eligible, day)
    return any(v is not None for v in siblings.values())


def _valued(
    scope: _Scope,
    session: SessionReads,
    leg: Leg,
    horizon: int,
    rows: pd.DataFrame,
    weights: Weights,
    why: str,
    deciles: tuple[float, ...] = (),
    ranked: int = 0,
) -> SessionStat:
    """The statistic of a session whose book is ``weights`` (``why``: it could not be formed),
    valued at S against the blended benchmark with the cash at the bill yield read at D
    (``portfolio/session.py``)."""
    o, day = scope.edge.outcome, leg.decision
    regime = session.label(day)
    book_vol: float | None = None
    risk_off: float | None = None
    if not why:
        weights, book_vol, risk_off, why = held_book(scope.edge, session, day, (weights,))
    if why:
        return portfolio_stat(day, regime, None, why, (), o.cost_bps)
    constituents = blend(o.benchmark)
    held_cash = any(name == CASH for name, _ in weights)
    value, why = session_value(
        weights,
        constituents,
        session.instruments(tuple(t for t, _ in constituents), leg.entry),
        window_returns(rows),
        cash_return(session.bill_yield(day), horizon) if held_cash else None,
    )
    return portfolio_stat(
        day, regime, value, why, weights, o.cost_bps, deciles, ranked, book_vol, risk_off
    )


def _portfolio_stat(
    scope: _Scope,
    session: SessionReads,
    run: RankedRun,
    names: Names,
    leg: Leg,
    horizon: int,
    rows: pd.DataFrame,
) -> SessionStat:
    """One ``portfolio_return`` session (ADR 0074): one screener's book, valued at S; the decile
    figures are its ranking of the eligible names, when enough were scored."""
    weights, why = book_at(scope.edge, session, run, names.pickable, leg.decision)
    scored = {i: v for i, v in run.scores.items() if i in names.ids}
    thin = len(scored) < MIN_SCORE_COVERAGE * len(names.ids)  # too few scores to rank
    deciles = (
        ()
        if thin or why
        else ranking_deciles(
            rows[rows["instrument_id"].isin(names.ids)], scored, scope.edge.outcome.cost_bps
        )
    )
    return _valued(scope, session, leg, horizon, rows, weights, why, deciles, len(scored))


def _ensemble_stat(
    scope: _Scope,
    session: SessionReads,
    variant: Variant,
    leg: Leg,
    horizon: int,
    rows: pd.DataFrame,
    event_names: frozenset[str] | None,
) -> SessionStat:
    """One session of an ensemble (ADR 0074 amendment): the average of its members' books, valued
    as one. A member whose screen could not be read, or whose book cannot be formed, leaves the
    session out (never a book of the members that could): the grid is pre-registered whole. There
    is no single ranking, so no decile figures."""
    day = leg.decision
    eligible = session.eligible(scope.universe, day)
    names = names_for(scope.edge, eligible, event_names)
    books: list[Weights] = []
    for member in variant.members:
        run = session.run(member, day)
        if run is None or run.coverage not in MEASURED_COVERAGE:
            lost = session.lost.get((member.id, day))
            if lost is not None:
                session.lost[variant.id, day] = lost  # counted as the lost session it is
            return SessionStat(session=day, regime=session.label(day), excluded_coverage=1)
        book, why = book_at(scope.edge, session, run, names.pickable, day)
        if why:
            return _valued(scope, session, leg, horizon, rows, (), f"{why}:{member.id}")
        books.append(book)
    return _valued(scope, session, leg, horizon, rows, average_books(books), "")
