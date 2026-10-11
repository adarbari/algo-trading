"""How much evidence an edge's verdict has (``EvidenceProgress``): the out-of-sample trades it
has against the count the verdict needs, the Works counts, and the criteria that say whether the
result is real, and the outlook (``EdgeOutlook``): the first test the verdict has not passed,
in words, and for a count what is missing. Pure: the counts and the criteria are the verdict's
own, nothing is read here. The date a count will be reached is the harness's to project (ADR
0064 decision 7: it writes the exit sessions of the schedule's next decisions on the run, which
no run stores yet), so the outlook says which state the projection is in, never a date."""

from collections.abc import Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True)
class EdgeOutlook:
    """What would change the verdict: ``criterion`` (the first test not passed, ``level``: the
    verdict it gates) and the server's ``sentence``. For a count (``trades``, ``works_trades``)
    ``have`` of ``needed`` trades, ``remaining`` still to come, and ``projection_state``: why
    there is no date (``not_stored``: no run stores the schedule's exits yet; ``unprojectable``:
    an event schedule has no calendar; ``oos_hidden``: a copy's out-of-sample result is withheld;
    ``projected`` and ``beyond_projection`` once a run stores them). None for any other test: a
    t statistic is not projected."""

    criterion: str
    level: str
    sentence: str
    have: int | None = None
    needed: int | None = None
    remaining: int | None = None
    projection_state: str | None = None


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


def outlook_of(
    gap: "VerdictCriterion | None",
    sentence: str,
    oos_trades: int | None,
    whole_trades: int | None,
    t: VerdictSettings,
    schedule: str | None,
    hidden: bool,
) -> EdgeOutlook | None:
    """The outlook for ``gap``, the first test the verdict has not passed (None: it passed
    every test), worded ``sentence``; ``schedule``: the edge's (None: not known)."""
    if gap is None:
        return None
    if gap.id not in COUNT_CRITERIA:
        return EdgeOutlook(gap.id, gap.level, sentence)
    have, needed = _count(gap, oos_trades or 0, whole_trades or 0, t)
    state = (
        OOS_HIDDEN
        if hidden
        else UNPROJECTABLE
        if schedule is not None and schedule.startswith("on_event:")
        else NOT_STORED
    )
    return EdgeOutlook(gap.id, gap.level, sentence, have, needed, max(needed - have, 0), state)


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
