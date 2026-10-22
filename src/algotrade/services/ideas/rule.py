"""The Ideas ranking rule (owner decision 2026-10-22; docs/decisions/log.md "Ideas list"): a pure
function of the viewer's screener pool and the rule's parameters, with no read, no clock and no
float in any ordering, so the same inputs give the same list byte for byte.

The pool is one ``PoolRun`` per screener the viewer has (the site presets and their own; a
screener of the viewer's with a preset's id replaces it). Each run brings its picked rows in
the run's stored rank order. A site screener counts its first ``site_top`` picks and a viewer's
own its first ``user_top``; the pick at position ``p`` scores ``weight / p`` (weight 1 for a
site screener, ``user_weight`` for the viewer's own), an exact fraction compared by integer
cross-multiplication. An idea is one ticker, scored by its BEST pick (the max, never a sum: a
ticker in twelve site top-fives must not bury every pick of the viewer's own); ``best`` is that
pick (a tie goes to the viewer's own screener, then the screener id) and ``picked_by`` lists
every pool pick of the ticker, best first. The order is the idea score, then consensus
(``len(picked_by)``), then the sum of the pick scores, then the instrument id.

Licence: a run withheld from the viewer (``run_withheld``: its rank follows values their
licences do not cover) contributes nothing, because its top picks by rank would leak the
ranking; it is listed ``WITHHELD``. A screener with no run for the session contributes nothing
and is listed ``NOT_RUN`` with its reason, never as "0 picks". The picks the regime gate held
back (``paused``) follow the same rule in a section of their own, one entry per screener and
ticker. Nothing here reads a store: the loader builds the pool (``services/read/screens``)."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction

from algotrade.config.ranking.ideas import IdeasRule

RAN = "RAN"
NOT_RUN = "NOT_RUN"
WITHHELD = "WITHHELD"
STATUSES = (RAN, NOT_RUN, WITHHELD)
SUMMARY_TOP = 3  # a screener's summary lists its first this many pool picks


@dataclass(frozen=True)
class PoolRow:
    """One picked (or paused) row of a run: the ticker and the decision the run gave it."""

    instrument_id: str
    decision: str


@dataclass(frozen=True)
class PoolRun:
    """One screener of the viewer's pool: its run for the session (``run_id``; None for none)
    and ``status``. ``own``: it is the viewer's (weight ``user_weight``, first ``user_top``); a
    site preset is not. ``picked`` and ``paused`` are in the run's stored rank order and are
    ignored unless ``status`` is ``RAN``. ``reason``: the cause a run is ``NOT_RUN`` for."""

    owner: str
    config_id: str
    own: bool
    status: str = RAN
    run_id: str | None = None
    reason: str | None = None
    picked: tuple[PoolRow, ...] = ()
    paused: tuple[PoolRow, ...] = ()


@dataclass(frozen=True)
class PoolPick:
    """One screener's pick of ``instrument_id``: its ``position`` in the run (1 is the first)
    and the exact ``score`` weight / position."""

    instrument_id: str
    owner: str
    config_id: str
    run_id: str
    own: bool
    position: int
    decision: str
    score: Fraction


@dataclass(frozen=True)
class RankedIdea:
    """A ticker some pool screener picked: ``score`` is its best pick's, ``best`` that pick,
    ``picked_by`` every pool pick of it (best first, ``best`` included)."""

    rank: int
    instrument_id: str
    score: Fraction
    best: PoolPick
    picked_by: tuple[PoolPick, ...]


@dataclass(frozen=True)
class PausedPick:
    """A ticker one screener picked and the regime gate held back, scored like a pick."""

    rank: int
    instrument_id: str
    pick: PoolPick


@dataclass(frozen=True)
class PoolStanding:
    """What a screener of the pool did: its ``status``, the ``reason`` of a ``NOT_RUN`` and its
    first ``SUMMARY_TOP`` pool picks (``top``, best first; none unless it ran)."""

    owner: str
    config_id: str
    own: bool
    status: str
    run_id: str | None
    reason: str | None
    top: tuple[PoolPick, ...]


def _preferred(pick: PoolPick) -> tuple[int, str, str]:
    """Ties between equal scores: the viewer's own screener, then the screener id."""
    return (0 if pick.own else 1, pick.config_id, pick.owner)


def _by_score(pick: PoolPick) -> tuple[Fraction, int, str, str]:
    # Fraction orders by integer cross-multiplication; negated for best first.
    return (-pick.score, *_preferred(pick))


def effective_pool(pool: Iterable[PoolRun]) -> list[PoolRun]:
    """``pool`` with a preset replaced by the viewer's own screener of the same id, in a fixed
    order (the viewer's own first, then by id): the order the caller gave is not meaningful."""
    own_ids = {r.config_id for r in pool if r.own}
    kept = [r for r in pool if r.own or r.config_id not in own_ids]
    return sorted(kept, key=lambda r: (0 if r.own else 1, r.config_id, r.owner))


def _picks_of(run: PoolRun, rows: Sequence[PoolRow], rule: IdeasRule) -> list[tuple[str, PoolPick]]:
    """``(ticker, pick)`` of the first ``top`` distinct tickers of ``rows`` (a run's picked or
    paused rows), each at its position among them; none unless the run ran."""
    if run.status != RAN or run.run_id is None:
        return []
    top = rule.user_top if run.own else rule.site_top
    weight = rule.user_weight if run.own else 1
    out: list[tuple[str, PoolPick]] = []
    seen: set[str] = set()
    for row in rows:
        if row.instrument_id in seen:
            continue
        seen.add(row.instrument_id)
        if len(out) == top:
            break
        position = len(out) + 1
        pick = PoolPick(
            row.instrument_id, run.owner, run.config_id, run.run_id, run.own, position,
            row.decision, Fraction(weight, position),
        )  # fmt: skip
        out.append((row.instrument_id, pick))
    return out


def _tickers(
    pool: Sequence[PoolRun], rule: IdeasRule, *, paused: bool
) -> dict[str, list[PoolPick]]:
    found: dict[str, list[PoolPick]] = {}
    for run in pool:
        for iid, pick in _picks_of(run, run.paused if paused else run.picked, rule):
            found.setdefault(iid, []).append(pick)
    return found


def rank_ideas(pool: Iterable[PoolRun], rule: IdeasRule) -> list[RankedIdea]:
    """The viewer's ideas, best first (``RankedIdea.rank`` from 1)."""
    runs = effective_pool(list(pool))
    found = _tickers(runs, rule, paused=False)
    entries = []
    for iid, picks in found.items():
        ordered = sorted(picks, key=_by_score)
        entries.append((iid, ordered, sum((p.score for p in ordered), Fraction(0))))
    entries.sort(key=lambda e: (-e[1][0].score, -len(e[1]), -e[2], e[0]))
    return [
        RankedIdea(n, iid, picks[0].score, picks[0], tuple(picks))
        for n, (iid, picks, _) in enumerate(entries, start=1)
    ]


def rank_paused(pool: Iterable[PoolRun], rule: IdeasRule) -> list[PausedPick]:
    """The picks the regime gate held back, one entry per screener and ticker, by the same
    rule (first ``site_top`` / ``user_top`` of each screener's paused rows, weight / position):
    score, then the viewer's own screener first, then screener id and ticker."""
    runs = effective_pool(list(pool))
    held = [
        (iid, pick) for iid, picks in _tickers(runs, rule, paused=True).items() for pick in picks
    ]
    held.sort(key=lambda e: (_by_score(e[1]), e[0]))
    return [PausedPick(n, iid, pick) for n, (iid, pick) in enumerate(held, start=1)]


def pool_standing(pool: Iterable[PoolRun], rule: IdeasRule) -> list[PoolStanding]:
    """Every screener of the pool with its status and first picks: ``NOT_RUN`` with its reason,
    ``WITHHELD`` (the licence rule), or ran."""
    out = []
    for run in effective_pool(list(pool)):
        top = [pick for _, pick in _picks_of(run, run.picked, rule)[:SUMMARY_TOP]]
        reason = run.reason if run.status == NOT_RUN else None
        out.append(
            PoolStanding(
                run.owner, run.config_id, run.own, run.status, run.run_id, reason, tuple(top)
            )
        )
    return out
