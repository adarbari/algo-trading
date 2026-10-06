"""``Viewer``: who the request is for (ADR 0040 decision 4): the registry user the API
authenticated, their role and the workspaces it opens (``apps/web`` ``WorkspaceId``), the one
field the web's role gate ``guard.ts`` reads. Never the email or the subject: identity stays
on the server."""

from dataclasses import dataclass

from algotrade.config.site.users import UserRecord


@dataclass(frozen=True)
class Viewer:
    user_id: str
    name: str
    role: str  # "admin" or "trader"
    workspaces: tuple[str, ...]  # sorted


def load_viewer(user: UserRecord) -> Viewer:
    """The viewer of the request ``user`` made (no store read: the registry is in memory)."""
    return Viewer(user.user_id, user.name, user.role.value, tuple(sorted(user.role.workspaces)))
