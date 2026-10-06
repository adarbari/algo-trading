"""``Viewer``: the signed-in user, their role and the workspaces they may enter (ADR 0040)."""

from typing import Self

import strawberry

from algotrade.services.read.users import viewer


@strawberry.type(
    description="The user this request is for: the registry user the token maps to, their "
    "`role` (admin or trader) and the `workspaces` (trader, admin) the role opens; the web's "
    "role gate reads it, the server enforces it"
)
class Viewer:
    user_id: str = strawberry.field(name="id")
    name: str
    role: str
    workspaces: list[str]

    @classmethod
    def of(cls, d: viewer.Viewer) -> Self:
        return cls(user_id=d.user_id, name=d.name, role=d.role, workspaces=list(d.workspaces))
