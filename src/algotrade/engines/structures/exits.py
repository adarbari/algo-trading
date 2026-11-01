"""The one ordered exit rule list, evaluated over a trade's closes (ADR 0088, design 2.4a): a pure
function of a sequence of closes, each a mapping of field name to value, and the compiled
``ExitRule`` list (take profit, stop loss, DTE, then the exit condition). It knows nothing of
option pricing, so the option engine feeds it ``position.*`` fields from its marks and a later
share walker (E3c) feeds it the same fields from ``bars/1d``.

Rules, by the one point-in-time rule: a rule observed at close t acts at t when it names only
``position.*`` fields (t's own closing marks) and at t + 1 when it names a catalogue field
(``exit_delay``); the earliest acting close wins, several acting at one close: the first in
declared order. A rule UNKNOWN at a close never fires (no exit on data we do not have) and the
closes where any rule was UNKNOWN are counted. A rule that would act after the last close does not
act: the hold cap, expiry and the other fixed rules of the caller end the trade there."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from algotrade.config.edges.positions.spec import ExitRule, exit_delay
from algotrade.core.model.predicates import FieldValue, evaluate_group


@dataclass(frozen=True)
class ExitHit:
    """The exit that ended the trade: its ``kind`` (``TAKE_PROFIT`` ...), the index of the close it
    acts at (``at``), the close it was observed at (``observed``) and how many closes up to ``at``
    had a rule UNKNOWN (``unknown_closes``)."""

    kind: str
    at: int
    observed: int
    unknown_closes: int


@dataclass(frozen=True)
class ExitScan:
    """``hit`` is None when no rule acted within the closes; ``unknown_closes`` counts the closes
    scanned (to the hit, else all) on which at least one rule was UNKNOWN."""

    hit: ExitHit | None
    unknown_closes: int


def scan_exits(rules: Sequence[ExitRule], closes: Sequence[Mapping[str, FieldValue]]) -> ExitScan:
    """The first exit of ``rules`` over ``closes`` (index 0 is the first close after entry: a
    caller holding the entry close's marks, as ``Marks.mids`` does, drops it)."""
    delays = [exit_delay(r.rule) for r in rules]
    pending: dict[int, tuple[int, str, int]] = {}  # acting index -> (rule order, kind, observed)
    unknown = [False] * len(closes)
    for t, row in enumerate(closes):
        for order, (rule, delay) in enumerate(zip(rules, delays, strict=True)):
            truth = evaluate_group(rule.rule, row)
            if truth is None:
                unknown[t] = unknown[t] or t + delay < len(closes)  # one that cannot act is moot
            elif truth and t + delay < len(closes):
                best = pending.get(t + delay)
                if best is None or order < best[0]:
                    pending[t + delay] = (order, rule.kind, t)
        # an exit acting at t is known once every rule observed up to t has been read
        if t in pending:
            _, kind, observed = pending[t]
            return ExitScan(
                ExitHit(kind, t, observed, sum(unknown[: t + 1])), sum(unknown[: t + 1])
            )
    return ExitScan(None, sum(unknown))
