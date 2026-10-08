"""``FeatureValue`` and ``FeatureInfo`` (ADR 0038): a catalogue field's value for an
instrument and the session, the reason when it is UNKNOWN, and the field's metadata with the
display ``format`` the server derives (the client never guesses one from the name) and, on
the catalogue read, the site field guide's entry (``FieldGuide``: how to read it, the
criterion per intent, caveats; ADR 0041 amended)."""

from typing import Self

import strawberry
from strawberry.scalars import JSON
from strawberry.types import Info

from algotrade.services.read import values
from algotrade.services.read.availability.cause import UnavailableKind
from algotrade.services.read.instruments import catalogue, features
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.permissions import AdminCause
from algotrade_api.graphql.types.availability import Cause

strawberry.enum(values.UnknownCode, description="Why a value is UNKNOWN for the session")
strawberry.enum(
    values.NullReason, description="Why a value is null when the null is the fact (EXPLAINED)"
)
strawberry.enum(catalogue.FeatureFormat, description="How a client shows a feature's value")


@strawberry.type(
    description="A value not known for the session: `code` and, in public words, `kind` (with "
    "its Guide term `guideTerm`); `reason` is set exactly when `code` is EXPLAINED. `cause` is "
    "the chain behind it, source to table: admins only (null for anyone else). `detail` is "
    "legacy: the chain as one line for an admin, the generic words for anyone else"
)
class Unknown:
    code: values.UnknownCode
    reason: values.NullReason | None
    kind: UnavailableKind
    guide_term: str
    unknown: strawberry.Private[values.Unknown]

    @classmethod
    def of(cls, d: values.Unknown) -> Self:
        return cls(code=d.code, reason=d.reason, kind=d.kind, guide_term=d.guide_term, unknown=d)

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Legacy (ADR 0056; the web moves to `cause` / `kind`): why and where it "
        "looked, as one line for an admin; the generic words for anyone else",
        extensions=[AdminCause(public=lambda source, _: source.unknown.public_reason)],
    )
    def detail(self) -> str:
        return self.unknown.cause.text

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The chain behind it, source to table; null unless the caller is an admin",
        extensions=[AdminCause()],
    )
    async def cause(self, info: Info[RequestContext, None]) -> Cause | None:
        return Cause.of(await info.context.cause_of(self.unknown.cause))


@strawberry.type(
    description="One intent a trader has for a field and the criterion that expresses it, as "
    "a rule screen takes it: `op`, `value` (in the field's unit), `mode`, `tolerance` (a "
    "number in the unit, or `{relative}` as a share of the threshold), `onMiss` for soft; "
    "`note` says how to combine it"
)
class GuideUse:
    intent: str
    op: str
    value: JSON | None
    mode: str
    tolerance: JSON | None
    on_miss: str | None
    note: str

    @classmethod
    def of(cls, d: catalogue.GuideUse) -> Self:
        return cls(
            intent=d.intent,
            op=d.op,
            value=d.value,
            mode=d.mode,
            tolerance=None if d.tolerance is None else JSON(d.tolerance),
            on_miss=d.on_miss,
            note=d.note,
        )


@strawberry.type(
    description="The site field guide's entry for a field (docs/data/field-guide.md): how to "
    "read it (`reads`; `summary` is its first sentence, for a hover), the criterion per "
    "intent, when the reading lies (each caveat names the field that exposes it), and the "
    "sources"
)
class FieldGuide:
    theme: str
    reads: str
    summary: str
    uses: list[GuideUse]
    caveats: list[str]
    sources: list[str]

    @classmethod
    def of(cls, d: catalogue.FieldGuide) -> Self:
        return cls(
            theme=d.theme,
            reads=d.reads,
            summary=d.summary,
            uses=[GuideUse.of(u) for u in d.uses],
            caveats=list(d.caveats),
            sources=list(d.sources),
        )


@strawberry.type(
    description="One catalogue field: what it is and how to show it; `guide` is the site "
    "field guide's entry (on the catalogue read; null for a field without one)"
)
class FeatureInfo:
    name: str
    kind: str
    source: str
    dtype: str
    format: catalogue.FeatureFormat
    description: str
    null_meaning: str
    version: int | None
    group: str | None
    key: str | None
    inputs: list[str]
    unit: str | None
    range: list[float | None] | None
    categories: list[str]
    scope: str
    owner: str | None
    licence: str
    guide: FieldGuide | None

    @classmethod
    def of(cls, d: catalogue.FeatureInfo) -> Self:
        return cls(
            name=d.name,
            kind=d.kind,
            source=d.source,
            dtype=d.dtype,
            format=d.format,
            description=d.description,
            null_meaning=d.null_meaning,
            version=d.version,
            group=d.group,
            key=d.key,
            inputs=list(d.inputs),
            unit=d.unit,
            range=list(d.range) if d.range is not None else None,
            categories=list(d.categories),
            scope=d.scope,
            owner=d.owner,
            licence=d.licence,
            guide=FieldGuide.of(d.guide) if d.guide is not None else None,
        )


@strawberry.type(
    description="A catalogue field's value for one instrument and the session: `value` is "
    "null exactly when `unknown` says why; format it with `info.format`"
)
class FeatureValue:
    name: str
    value: JSON | None
    unknown: Unknown | None
    info: FeatureInfo

    @classmethod
    def of(cls, d: features.FeatureValue) -> Self:
        return cls(
            name=d.name,
            value=JSON(d.value),
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
            info=FeatureInfo.of(d.info),
        )
