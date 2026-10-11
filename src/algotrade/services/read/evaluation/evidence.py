"""How much evidence an edge's verdict has (``EvidenceProgress``): the out-of-sample trades it
has against the count the verdict needs, the Works counts, and the criteria that say whether the
result is real, and the outlook (``EdgeOutlook``): the first test the verdict has not passed,
in words, and for a count what is missing and when it is expected. Pure: the counts and the
criteria are the verdict's own, nothing is read here. The date comes from the run's stored
projection (ADR 0064 decision 7: the harness writes the exit sessions of the schedule's next
decision sessions and the scheduled and measured counts on its ``all`` row): the missing trades
are scaled by how often the out-of-sample side filled (measured over scheduled, floored at
``FILL_FLOOR``) and read off the stored exits. Otherwise the outlook says which state the
projection is in, never a made-up date. Both count criteria are projected (the page shows when
Promising's count and Works's are expected) and the next close is the first stored exit after the
run. ``AtTarget`` is the verdict as it would stand with the count gate met, on today's figures
(computed by the verdict, which owns the rule). An estimate: never an input to a verdict."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Final

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.core.time.calendar import sessions_to

if TYPE_CHECKING:
    from algotrade.services.read.evaluation.verdict import VerdictCriterion

CHECK_IDS: Final = ("win_rate", "random", "baselines", "trades")  # shown in this order
COUNT_CRITERIA: Final = ("trades", "works_trades")  # a count a later session can add to
PROJECTED, NOT_STORED, BEYOND_PROJECTION, UNPROJECTABLE, OOS_HIDDEN = (
    "projected",
    "not_stored",
    "beyond_projection",
    "unprojectable",
    "oos_hidden",
)
PROJECTION_STATES: Final = (PROJECTED, NOT_STORED, BEYOND_PROJECTION, UNPROJECTABLE, OOS_HIDDEN)
LEVEL_WORDS: Final = {
    "works": "Works",
    "promising": "Promising",
    "not_working": "Not working",
    "not_enough_data": "Not enough data",
    "waiting_on_data": "Waiting on data",
}
FILL_FLOOR: Final = 0.25  # the lowest share of decision sessions a projection counts on measuring


@dataclass(frozen=True)
class Projection:
    """What the basis's ``all`` row stores for a projection: ``exits`` (the exit sessions of the
    schedule's next decision sessions, in order) and how many decision sessions the run scheduled
    and measured (the ``_oos`` pair: from the split on; None without one)."""

    exits: tuple[date, ...] = ()
    scheduled: int | None = None
    measured: int | None = None
    scheduled_oos: int | None = None
    measured_oos: int | None = None


@dataclass(frozen=True)
class CountProjection:
    """One count criterion still short: ``have`` of ``needed`` (``oos``: out-of-sample trades,
    else the whole history's), ``remaining`` to come, the ``state`` of its projection and
    ``expected_by`` the exit of the trade that completes it, at ``fill_ratio`` of the decision
    sessions measured and one trade every ``cadence_sessions`` sessions."""

    criterion: str
    oos: bool
    have: int
    needed: int
    remaining: int
    state: str
    expected_by: date | None = None
    fill_ratio: float | None = None
    cadence_sessions: int | None = None


@dataclass(frozen=True)
class AtTarget:
    """The verdict with the count gate of the outlook's criterion met (``needed`` trades), on
    today's figures: its ``level``, the ``reasons`` it is not better (the failing tests, in
    words) and the server's ``sentence``."""

    needed: int
    level: str
    reasons: tuple[str, ...]
    sentence: str


@dataclass(frozen=True)
class EdgeOutlook:
    """What would change the verdict: ``criterion`` (the first test not passed, ``level``: the
    verdict it gates) and the server's ``sentence``. For a count (``trades``, ``works_trades``)
    ``have`` of ``needed`` trades, ``remaining`` still to come and ``projection_state``:
    ``projected`` (``expected_by``: the exit of the trade that completes the count, at
    ``fill_ratio`` of the decision sessions measured), ``beyond_projection`` (the count needs
    more sessions than the stored list reaches; the next run extends it), ``not_stored`` (the run
    stores no projection: an older one), ``unprojectable`` (an event schedule has no calendar) or
    ``oos_hidden`` (a copy's out-of-sample result is withheld). None for any other test: a t
    statistic is not projected."""

    criterion: str
    level: str
    sentence: str
    have: int | None = None
    needed: int | None = None
    remaining: int | None = None
    projection_state: str | None = None
    expected_by: date | None = None
    fill_ratio: float | None = None
    cadence_sessions: int | None = None
    projections: tuple[CountProjection, ...] = ()  # every count criterion still short
    next_close: date | None = None  # the first stored exit after the run: the next trade to close
    at_target: AtTarget | None = None


@dataclass(frozen=True)
class EvidenceProgress:
    """``oos_trades`` out-of-sample against ``needed`` (``min_oos_trades``: from there the
    verdict can say Promising or Not working; ``reached``: it has them), ``works_oos_needed`` the
    out-of-sample count Works asks and ``whole_trades`` against ``whole_needed`` the whole
    history's; ``checks``: the verdict's criteria that say whether the result is real."""

    oos_trades: int
    needed: int
    works_oos_needed: int
    whole_trades: int
    whole_needed: int
    reached: bool
    checks: tuple["VerdictCriterion", ...]
    outlook: EdgeOutlook | None = None


def count_of(cid: str, oos: int, whole: int, t: VerdictSettings) -> tuple[int, int, bool]:
    """``(have, needed, out_of_sample)`` of a count criterion: its out-of-sample count, or for
    ``works_trades`` whichever of the whole history's and the out-of-sample count is further
    from its bound."""
    if cid == "trades":
        return oos, t.min_oos_trades, True
    short_oos, short_whole = t.works_oos_trades - oos, t.works_trades - whole
    if short_oos >= short_whole:
        return oos, t.works_oos_trades, True
    return whole, t.works_trades, False


def _fill_ratio(p: Projection) -> float | None:
    """The share of decision sessions that were measured: the out-of-sample side's, else the
    whole run's (no split); floored at ``FILL_FLOOR``, at most 1; None: the counts are not
    stored."""
    pairs = ((p.measured_oos, p.scheduled_oos), (p.measured, p.scheduled))
    for measured, scheduled in pairs:
        if measured is not None and scheduled is not None and scheduled > 0:
            return min(max(measured / scheduled, FILL_FLOOR), 1.0)
    return None


def project(remaining: int, p: Projection | None) -> tuple[str, date | None, float | None]:
    """``(state, expected_by, fill_ratio)`` for ``remaining`` trades: the ``ceil(remaining /
    ratio)``-th stored exit."""
    ratio = None if p is None else _fill_ratio(p)
    if p is None or not p.exits or ratio is None:
        return NOT_STORED, None, None
    nth = max(math.ceil(max(remaining, 1) / ratio), 1)
    if nth > len(p.exits):
        return BEYOND_PROJECTION, None, ratio
    return PROJECTED, p.exits[nth - 1], ratio


def _cadence(p: Projection | None, ratio: float | None) -> int | None:
    """Sessions between two trades closing: the median gap between the stored exits, over the
    share of decision sessions that fill (None: fewer than two exits or no ratio)."""
    if p is None or ratio is None or len(p.exits) < 2:
        return None
    gaps = sorted(sessions_to(a, b) for a, b in zip(p.exits, p.exits[1:], strict=False))
    return max(round(gaps[len(gaps) // 2] / ratio), 1)


def _projection(
    cid: str,
    oos_trades: int,
    whole_trades: int,
    t: VerdictSettings,
    schedule: str | None,
    hidden: bool,
    p: Projection | None,
) -> CountProjection:
    have, needed, oos = count_of(cid, oos_trades, whole_trades, t)
    remaining = max(needed - have, 0)
    if hidden:
        return CountProjection(cid, oos, have, needed, remaining, OOS_HIDDEN)
    if schedule is not None and schedule.startswith("on_event:"):
        return CountProjection(cid, oos, have, needed, remaining, UNPROJECTABLE)
    state, by, ratio = project(remaining, p)
    return CountProjection(cid, oos, have, needed, remaining, state, by, ratio, _cadence(p, ratio))


def _count_sentence(level: str, c: CountProjection) -> str:
    """ "Promising needs 40 out-of-sample trades: 8 so far, 32 to go, about Sep 2028 at one trade
    every 15 sessions." (the date and cadence only when projected)."""
    kind = "out-of-sample trades" if c.oos else "trades"
    words = f"{LEVEL_WORDS.get(level, level)} needs {c.needed} {kind}: {c.have} so far"
    if c.remaining:
        words += f", {c.remaining} to go"
    if c.state == PROJECTED and c.expected_by is not None:
        words += f", about {c.expected_by:%b %Y}"
        if c.cadence_sessions:
            every = (
                "every session"
                if c.cadence_sessions == 1
                else f"every {c.cadence_sessions} sessions"
            )
            words += f" at one trade {every}"
    return words + "."


def _next_close(p: Projection | None, after: date | None) -> date | None:
    """The first stored exit after ``after`` (the run's last session): the next trade to close."""
    if p is None:
        return None
    return next((d for d in p.exits if after is None or d > after), None)


def outlook_of(
    gap: "VerdictCriterion | None",
    sentence: str,
    oos_trades: int | None,
    whole_trades: int | None,
    t: VerdictSettings,
    schedule: str | None,
    hidden: bool,
    projection: Projection | None = None,
    after: date | None = None,
    at_target: AtTarget | None = None,
) -> EdgeOutlook | None:
    """The outlook for ``gap``, the first test the verdict has not passed (None: it passed
    every test), worded ``sentence`` (a count: the server's own, with the date); ``schedule``:
    the edge's (None: not known); ``projection``: what the basis's ``all`` row stores (None:
    nothing); ``after``: the run's last session; ``at_target``: the verdict with the count met
    (from the verdict, only for a count)."""
    if gap is None:
        return None
    oos, whole = oos_trades or 0, whole_trades or 0
    every = tuple(
        c
        for cid in COUNT_CRITERIA
        if (c := _projection(cid, oos, whole, t, schedule, hidden, projection)).remaining > 0
    )
    close = None if hidden else _next_close(projection, after)
    if gap.id not in COUNT_CRITERIA:
        return EdgeOutlook(gap.id, gap.level, sentence, projections=every, next_close=close)
    mine = _projection(gap.id, oos, whole, t, schedule, hidden, projection)
    return EdgeOutlook(
        gap.id, gap.level, _count_sentence(gap.level, mine), mine.have, mine.needed,
        mine.remaining, mine.state, mine.expected_by, mine.fill_ratio, mine.cadence_sessions,
        every, close, at_target,
    )  # fmt: skip


def evidence_of(
    oos_trades: int | None,
    whole_trades: int | None,
    criteria: Sequence["VerdictCriterion"],
    t: VerdictSettings,
    outlook: EdgeOutlook | None = None,
) -> EvidenceProgress:
    """The progress of a verdict with ``oos_trades`` and ``whole_trades`` (None: none) and its
    ``criteria``, against the thresholds ``t``; ``outlook`` from ``outlook_of``."""
    by = {c.id: c for c in criteria}
    oos = oos_trades or 0
    return EvidenceProgress(
        oos_trades=oos,
        needed=t.min_oos_trades,
        works_oos_needed=t.works_oos_trades,
        whole_trades=whole_trades or 0,
        whole_needed=t.works_trades,
        reached=oos >= t.min_oos_trades,
        checks=tuple(by[i] for i in CHECK_IDS if i in by),
        outlook=outlook,
    )
