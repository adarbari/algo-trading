"""``Config``: a strategy or screener config the user sees (a site preset or their own),
resolved through its layers with its hash, or why it does not resolve."""

from typing import Self

import strawberry

from algotrade.services.read.ops import configs


@strawberry.type(
    description="A config the user sees: `scope` site (a preset) or the user's id; `kind` "
    "strategy or screener (null when it does not resolve); `selection` the named selection or "
    "inline; `error` why it does not resolve"
)
class Config:
    config_id: str
    scope: str
    kind: str | None
    impl: str | None
    selection: str | None
    hash: str | None
    error: str | None

    @classmethod
    def of(cls, d: configs.Config) -> Self:
        return cls(
            config_id=d.config_id,
            scope=d.scope,
            kind=d.kind,
            impl=d.impl,
            selection=d.selection,
            hash=d.hash,
            error=d.error,
        )
