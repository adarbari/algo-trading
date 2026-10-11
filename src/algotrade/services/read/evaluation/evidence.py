"""How much evidence an edge's verdict has (``EvidenceProgress``): the out-of-sample trades it
has against the count the verdict needs, the Works counts, and the criteria that say whether the
result is real. Pure: the counts and the criteria are the verdict's own, nothing is read or
projected here (when the count will be reached is not served: decisions are at least one holding
period apart, so it grows by about one trade per holding period)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from algotrade.config.edges.verdict import VerdictSettings

if TYPE_CHECKING:
    from algotrade.services.read.evaluation.verdict import VerdictCriterion

CHECK_IDS: Final = ("win_rate", "random", "baselines", "trades")  # shown in this order


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


def evidence_of(
    oos_trades: int | None,
    whole_trades: int | None,
    criteria: Sequence["VerdictCriterion"],
    t: VerdictSettings,
) -> EvidenceProgress:
    """The progress of a verdict with ``oos_trades`` and ``whole_trades`` (None: none) and its
    ``criteria``, against the thresholds ``t``."""
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
    )
