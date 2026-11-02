"""``first_entry``: which close of an entry condition's wait a name enters after (ADR 0088, design
2.4a): the first close t whose rule is TRUE; a FALSE close continues the wait; an UNKNOWN close
before any TRUE one stops it (``ENTRY_UNKNOWN``: missing data never decides an entry, as it never
chooses a case); never TRUE in the wait is ``NOT_TRIGGERED`` (counted, not a missing P&L). Pure,
over one name's fields at each close of the wait, each row read from that close's partition only;
the caller places S = t + ``start_offset_sessions`` (>= 1), so nothing of t's close is traded at
t. Called by the harnesses (cross-section and time-series), never by an engine."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from algotrade.core.model.predicates import FieldValue, Group, evaluate_group

NOT_TRIGGERED = "NOT_TRIGGERED"
ENTRY_UNKNOWN = "ENTRY_UNKNOWN"


@dataclass(frozen=True)
class EntryDecision:
    """``close``: the index in the wait (0 = the decision session D) of the close the name enters
    after, or ``None`` with ``reason`` (``NOT_TRIGGERED`` / ``ENTRY_UNKNOWN``)."""

    close: int | None
    reason: str | None = None

    @property
    def entered(self) -> bool:
        return self.close is not None


def first_entry(
    when: Group,
    closes: Sequence[Mapping[str, FieldValue]],
    domains: Mapping[str, Sequence[str]] | None = None,
) -> EntryDecision:
    """``closes``: the name's fields at each close of the wait, D first. ``domains``: a string
    field's declared values (``FieldCatalog.domains``); a value outside it is read as missing, so
    ``ne`` / ``not_in`` on a label never seen is UNKNOWN, never TRUE (a strict site)."""
    for i, row in enumerate(closes):
        read = {
            k: None if domains and k in domains and v not in domains[k] else v
            for k, v in row.items()
        }
        truth = evaluate_group(when, read)
        if truth is None:
            return EntryDecision(None, ENTRY_UNKNOWN)
        if truth:
            return EntryDecision(i)
    return EntryDecision(None, NOT_TRIGGERED)
