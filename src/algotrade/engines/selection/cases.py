"""``resolve_case``: the concrete value of a case-valued parameter at one session (ADR 0088,
design 2.4): the first case whose rule is TRUE gives its value, ``default`` only when every case
is FALSE, and a case that is UNKNOWN before a TRUE one makes the name unselectable
(``CASE_UNKNOWN``): missing data never chooses a branch. Pure, over one session's fields (the
instrument and market fields of the name at the decision session). Called by the harness at each
decision session and by the picks task at the served session, never by the option engine, which
receives the resolved point."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from algotrade.config.edges.positions.cases import CaseValue, Scalar
from algotrade.core.model.predicates import FieldValue, evaluate_group

CASE_UNKNOWN = "CASE_UNKNOWN"


@dataclass(frozen=True)
class CaseResolution:
    """``value`` the parameter takes, or ``None`` with ``reason`` ``CASE_UNKNOWN`` and the index
    of the case (``unknown_at``) whose rule could not be decided."""

    value: Scalar | None
    reason: str | None = None
    unknown_at: int | None = None

    @property
    def selectable(self) -> bool:
        return self.reason is None


def resolve_case(
    case_value: CaseValue,
    row: Mapping[str, FieldValue],
    domains: Mapping[str, Sequence[str]] | None = None,
) -> CaseResolution:
    """``domains``: a string field's declared values (``FieldCatalog.domains``); a value outside
    it is read as missing, so ``ne`` / ``not_in`` on a label we never saw is UNKNOWN, never TRUE.
    The caller passes the catalogue's domains; the function applies them itself."""
    read = {
        k: None if domains and k in domains and v not in domains[k] else v for k, v in row.items()
    }
    for i, case in enumerate(case_value.cases):
        truth = evaluate_group(case.when, read)
        if truth is None:
            return CaseResolution(None, CASE_UNKNOWN, i)
        if truth:
            return CaseResolution(case.value)
    return CaseResolution(case_value.default)
