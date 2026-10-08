"""``Unavailable`` and ``Cause`` (ADR 0056): why a fact is not available, role-scoped.

``Unavailable`` is public: a ``kind``, the catalogue ``features`` it hides and the Guide term
that explains the kind. ``Cause`` (source -> step -> table -> features, root first) is served
only to admins: every field of this type that returns one carries ``AdminCause`` (null for
anyone else; ``tests/apps/api/graphql/test_causes.py`` enforces it)."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.availability import cause as domain
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.permissions import AdminCause

Ctx = Info[RequestContext, None]

strawberry.enum(domain.UnavailableKind, description="Why a gap is there, in public words")
strawberry.enum(domain.CauseLevel, description="What one link of a cause chain is")


@strawberry.type(
    description="One link of a cause chain: `subject` is the thing (a step, a table, a "
    "feature), `status` its state as recorded, `message` the stored words, `runId` the run "
    "record it came from"
)
class CauseLink:
    level: domain.CauseLevel
    subject: str
    status: str
    message: str
    run_id: str | None
    session: dt.date | None

    @classmethod
    def of(cls, d: domain.CauseLink) -> Self:
        return cls(
            level=d.level,
            subject=d.subject,
            status=d.status,
            message=d.message,
            run_id=d.run_id,
            session=d.session,
        )


@strawberry.type(description="Why a fact is not available, root cause first. Admins only")
class Cause:
    links: list[CauseLink]

    @classmethod
    def of(cls, d: domain.Cause) -> Self:
        return cls(links=[CauseLink.of(link) for link in d.links])


@strawberry.type(
    description="Features a page cannot show, and why in public words: `kind`, the Guide "
    "glossary term `guideTerm` that explains it. `cause` is the chain behind it: admins only "
    "(null for anyone else)"
)
class Unavailable:
    kind: domain.UnavailableKind
    features: list[str]
    guide_term: str
    leaf: strawberry.Private[domain.Cause]

    @classmethod
    def of(cls, d: domain.Unavailable) -> Self:
        return cls(kind=d.kind, features=list(d.features), guide_term=d.guide_term, leaf=d.cause)

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The chain behind it, source to features; null unless the caller is an admin",
        extensions=[AdminCause()],
    )
    async def cause(self, info: Ctx) -> Cause | None:
        return Cause.of(await info.context.cause_of(self.leaf))
