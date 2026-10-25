"""``Appearance``: the user's stored Light / Dark / System choice (ADR 0085 decision 6)."""

from typing import Self

import strawberry

from algotrade.services.read.users import appearance


@strawberry.type(
    description="The theme the user chose: `light`, `dark` or `system` (the device decides); "
    "`system` when nothing valid is stored"
)
class Appearance:
    theme: str

    @classmethod
    def of(cls, d: appearance.Appearance) -> Self:
        return cls(theme=d.theme)
