"""``AcceptedFormulaList``: the formulas traders accepted in Describe it, grouped by fingerprint,
for the Admin "Accepted formulas" page (ADR 0066 note 2026-10-11). Counts only: no user id is a
field."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.formulas import accepted


@strawberry.type(
    description="One distinct formula (a fingerprint: the same formula written differently is "
    "one) that traders accepted. `users` is the distinct accepters and `acceptedCount` the "
    "distinct acceptances, never who. `expression`, `unit` and `description` are the newest "
    "acceptance's. `duplicateOf` is the site feature with the same fingerprint now (empty: "
    "none) and `backlogKey` the backlog item it exactly matches (empty: none)"
)
class AcceptedFormula:
    fingerprint: str
    canonical: str
    expression: str
    unit: str
    description: str
    accepted_count: int
    users: int
    first_accepted: dt.date
    last_accepted: dt.date
    duplicate_of: str
    backlog_key: str

    @classmethod
    def of(cls, d: accepted.AcceptedFormula) -> Self:
        return cls(
            fingerprint=d.fingerprint,
            canonical=d.canonical,
            expression=d.expression,
            unit=d.unit,
            description=d.description,
            accepted_count=d.accepted_count,
            users=d.users,
            first_accepted=d.first_accepted,
            last_accepted=d.last_accepted,
            duplicate_of=d.duplicate_of,
            backlog_key=d.backlog_key,
        )


@strawberry.type(
    description="The formulas accepted in the last `days` days up to `today` (exchange date): a "
    "date range, not one session. Most users first. Admin only; counts, never a user"
)
class AcceptedFormulaList:
    today: dt.date
    days: int
    rows: list[AcceptedFormula]

    @classmethod
    def of(cls, d: accepted.AcceptedFormulaList) -> Self:
        return cls(today=d.today, days=d.days, rows=[AcceptedFormula.of(r) for r in d.rows])
