"""``FeatureValue`` and ``FeatureInfo`` (ADR 0038): a catalogue field's value for an
instrument and the session, the reason when it is UNKNOWN, and the field's metadata with the
display ``format`` the server derives (the client never guesses one from the name)."""

from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read import values
from algotrade.services.read.instruments import catalogue, features

strawberry.enum(values.UnknownCode, description="Why a value is UNKNOWN for the session")
strawberry.enum(
    values.NullReason, description="Why a value is null when the null is the fact (EXPLAINED)"
)
strawberry.enum(catalogue.FeatureFormat, description="How a client shows a feature's value")


@strawberry.type(
    description="A value not known for the session: why, and where it looked; `reason` is "
    "set exactly when `code` is EXPLAINED"
)
class Unknown:
    code: values.UnknownCode
    detail: str
    reason: values.NullReason | None

    @classmethod
    def of(cls, d: values.Unknown) -> Self:
        return cls(code=d.code, detail=d.detail, reason=d.reason)


@strawberry.type(description="One catalogue field: what it is and how to show it")
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
