"""How much evidence an edge's verdict has (``EvidenceProgress``): the out-of-sample trades it
has against the count the verdict needs, the Works counts, and the criteria that say whether the
result is real, and the outlook (``EdgeOutlook``): the first test the verdict has not passed,
in words, and for a count what is missing and when it is expected. Pure: the counts and the
criteria are the verdict's own, nothing is read here. The date comes from the run's stored
projection (ADR 0064 decision 7: the harness writes the exit sessions of the schedule's next
decision sessions and the scheduled and measured counts on its ``all`` row): the missing trades
are scaled by how often the out-of-sample side filled (measured over scheduled, floored at
``FILL_FLOOR``) and read off the stored exits. Otherwise the outlook says which state the
projection is in, never a made-up date. An estimate: never an input to a verdict."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Final

from algotrade.config.edges.verdict import VerdictSettings

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


def _count(gap: "VerdictCriterion", oos: int, whole: int, t: VerdictSettings) -> tuple[int, int]:
    """``(have, needed)`` of a count criterion: its out-of-sample count, or for ``works_trades``
    whichever of the whole history's and the out-of-sample count is further from its bound."""
    if gap.id == "trades":
        return oos, t.min_oos_trades
    short_oos, short_whole = t.works_oos_trades - oos, t.works_trades - whole
    return (oos, t.works_oos_trades) if short_oos >= short_whole else (whole, t.works_trades)


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


def outlook_of(
    gap: "VerdictCriterion | None",
    sentence: str,
    oos_trades: int | None,
    whole_trades: int | None,
    t: VerdictSettings,
    schedule: str | None,
    hidden: bool,
    projection: Projection | None = None,
) -> EdgeOutlook | None:
    """The outlook for ``gap``, the first test the verdict has not passed (None: it passed
    every test), worded ``sentence``; ``schedule``: the edge's (None: not known);
    ``projection``: what the basis's ``all`` row stores (None: nothing)."""
    if gap is None:
        return None
    if gap.id not in COUNT_CRITERIA:
        return EdgeOutlook(gap.id, gap.level, sentence)
    have, needed = _count(gap, oos_trades or 0, whole_trades or 0, t)
    remaining = max(needed - have, 0)
    if hidden:
        state, by, ratio = OOS_HIDDEN, None, None
    elif schedule is not None and schedule.startswith("on_event:"):
        state, by, ratio = UNPROJECTABLE, None, None
    else:
        state, by, ratio = project(remaining, projection)
    return EdgeOutlook(gap.id, gap.level, sentence, have, needed, remaining, state, by, ratio)


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
