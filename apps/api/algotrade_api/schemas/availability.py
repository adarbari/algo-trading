"""``Unavailable`` as the REST routes serve it (ADR 0056): a kind, the catalogue features a gap
hides and the Guide term that explains the kind, public to every caller; its ``cause`` chain
(source -> step -> table -> features) is for admins, applied by ``redact`` (null for anyone
else)."""

from datetime import date

from pydantic import Field

from algotrade.services.read.availability.cause import ADMIN_CAUSE
from algotrade.services.read.availability.cause import Unavailable as Domain
from algotrade_api.schemas.health import Schema


class CauseLink(Schema):
    level: str = Field(description="SOURCE, STEP, TABLE, FEATURE or RUN")
    subject: str
    status: str
    message: str
    run_id: str | None
    session: date | None


class Unavailable(Schema):
    kind: str = Field(description="SYSTEM, NOT_STORED, NOT_APPLICABLE, ILLIQUID, LICENCE, NOT_RUN")
    features: list[str]
    guide_term: str = Field(description="the Guide glossary term that explains the kind")
    kind_text: str = Field(description="the kind in generic words")
    cause: list[CauseLink] | None = Field(
        description="the chain behind it, root cause first (admins only: null for anyone else)",
        json_schema_extra={ADMIN_CAUSE: None},
    )


def unavailable_of(found: Domain) -> Unavailable:
    """``found`` as served (``redact`` strips the cause for anyone but an admin)."""
    return Unavailable(
        kind=found.kind.value,
        features=list(found.features),
        guide_term=found.guide_term,
        kind_text=found.reason,
        cause=[CauseLink.model_validate(link) for link in found.cause.links],
    )
