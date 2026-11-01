"""``UserRegistry``: the people the site declares (``config/site/users.toml``) for the Admin Users
page: id, display name, role and the data licences they hold. Admin only (``PermissionDeniedError``
for anyone else, before anything is read). Never an email or a subject: identity stays on the
server (ADR 0040). What the site does not store (plan, last seen, brief delivery) is not a field."""

from dataclasses import dataclass

from algotrade.config.site.settings import load_users
from algotrade.config.site.users import Role
from algotrade.config.user import SITE_USER
from algotrade.core.model.errors import PermissionDeniedError
from algotrade.services.read.context import Stores
from algotrade.services.read.users.viewer import Viewer


@dataclass(frozen=True)
class Person:
    user_id: str
    name: str
    role: str  # "admin" or "trader"
    licences: tuple[str, ...]  # held beyond "open", sorted
    scheduled: bool  # the site's own scheduled-screens user, not a person who signs in


@dataclass(frozen=True)
class UserRegistry:
    people: tuple[Person, ...]  # declared order


def load_user_registry(ctx: Stores, viewer: Viewer) -> UserRegistry:
    """The declared users, in declaration order (admin only)."""
    if viewer.role != Role.ADMIN.value:
        raise PermissionDeniedError("only an admin can read the user registry")
    return UserRegistry(
        tuple(
            Person(
                u.user_id, u.name, u.role.value, tuple(sorted(u.licences)), u.user_id == SITE_USER
            )
            for u in load_users(ctx.configs).users
        )
    )
