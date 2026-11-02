"""``UserRegistry``: the declared people for the Admin Users page (admin only; no email)."""

from typing import Self

import strawberry

from algotrade.services.read.users import registry


@strawberry.type(
    description="One declared user (`config/site/users.toml`): `role` admin or trader, "
    "`licences` the data licences held beyond open, `scheduled` the site's own scheduled-screens "
    "user (never signs in). No email or subject: identity stays on the server"
)
class Person:
    user_id: str = strawberry.field(name="id")
    name: str
    role: str
    licences: list[str]
    scheduled: bool

    @classmethod
    def of(cls, d: registry.Person) -> Self:
        return cls(
            user_id=d.user_id,
            name=d.name,
            role=d.role,
            licences=list(d.licences),
            scheduled=d.scheduled,
        )


@strawberry.type(description="The people the site declares, in declaration order. Admin only")
class UserRegistry:
    people: list[Person]

    @classmethod
    def of(cls, d: registry.UserRegistry) -> Self:
        return cls(people=[Person.of(p) for p in d.people])
