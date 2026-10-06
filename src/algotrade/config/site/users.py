"""The user registry (ADR 0040): ``config/site/users.toml`` typed into ``UsersSettings``.

Every user the API and the CLIs may act for is declared here with a role (``admin`` enters the
ADMIN workspace and the ops reads; ``trader`` the TRADER workspace). Their configs stay in
``config/users/<id>/`` (ADR 0015): the registry only says who exists and what they may do. A
missing file is the single-user install: ``local`` as ``admin`` and ``site`` for scheduled
site screens, so nothing changes until a second user is declared. How a user proves who they
are (login) is the API's concern (ADR 0040); the email a sign-in maps to is not in the public
site file but in the user's own git-ignored ``config/users/<id>/identity.toml`` (``email``),
attached by ``with_emails``. ``settings.load_users`` reads the files, this module does no I/O.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.config.user import DEFAULT_USER, SITE_USER, validate_id
from algotrade.core.model.errors import ConfigurationError

WHERE = "users.toml"
USER_KEYS = ("id", "role", "name")
IDENTITY = "identity"  # config/users/<id>/identity.toml: the user's sign-in email
IDENTITY_KEYS = ("email",)


class Role(StrEnum):
    """What a user may enter: ADMIN (everything) or TRADER (the trading workspace)."""

    ADMIN = "admin"
    TRADER = "trader"

    @property
    def workspaces(self) -> frozenset[str]:
        """The workspace ids (``apps/web`` ``WorkspaceId``) this role may enter."""
        return frozenset({"trader", "admin"}) if self is Role.ADMIN else frozenset({"trader"})


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    role: Role
    name: str = ""
    email: str | None = None  # lowercased; from identity.toml (never committed: ADR 0040)

    def __post_init__(self) -> None:
        validate_id("user", self.user_id)
        if self.email is not None and self.user_id == SITE_USER:
            raise ConfigurationError(f"user '{SITE_USER}' runs scheduled screens: no email")


DEFAULT_USERS: tuple[UserRecord, ...] = (
    UserRecord(DEFAULT_USER, Role.ADMIN, "Local user"),
    UserRecord(SITE_USER, Role.ADMIN, "Scheduled site screens"),
)


@dataclass(frozen=True)
class UsersSettings:
    users: tuple[UserRecord, ...] = DEFAULT_USERS

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for user in self.users:
            if user.user_id in seen:
                raise ConfigurationError(f"{WHERE}: user '{user.user_id}' is declared twice")
            seen.add(user.user_id)
        if not any(u.role is Role.ADMIN for u in self.users):
            raise ConfigurationError(f"{WHERE}: at least one user must have role = 'admin'")
        emails = [u.email for u in self.users if u.email is not None]
        if len(emails) != len(set(emails)):
            raise ConfigurationError(f"{IDENTITY}.toml: two users have the same email")

    def get(self, user_id: str) -> UserRecord | None:
        """The declared user, or ``None`` for an unknown id (callers refuse it)."""
        return next((u for u in self.users if u.user_id == user_id), None)

    def by_email(self, email: str) -> UserRecord | None:
        """The user whose identity email is ``email`` (case ignored), or ``None``."""
        wanted = email.strip().lower()
        return next((u for u in self.users if u.email is not None and u.email == wanted), None)

    def with_emails(self, emails: Mapping[str, str | None]) -> "UsersSettings":
        """These users with the emails ``emails`` maps their ids to (``identity_email``)."""
        return UsersSettings(tuple(replace(u, email=emails.get(u.user_id)) for u in self.users))

    def role_of(self, user_id: str) -> Role:
        user = self.get(user_id)
        if user is None:
            raise ConfigurationError(f"{WHERE}: unknown user '{user_id}'")
        return user.role

    def may_enter(self, user_id: str, workspace: str) -> bool:
        """Whether ``user_id`` may enter ``workspace`` (unknown users enter nothing)."""
        user = self.get(user_id)
        return user is not None and workspace in user.role.workspaces

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "UsersSettings":
        """``users.toml`` (``[[user]]`` id, role, name); the defaults when the file is missing."""
        if doc is None:
            return cls()
        table = Table(doc, WHERE)
        table.only(("user",))
        raw = table.raw("user")
        if raw is None:
            return cls()
        if not isinstance(raw, list) or not all(isinstance(u, Mapping) for u in raw):
            raise ConfigurationError(f"{WHERE} user: expected an array of tables [[user]]")
        return cls(tuple(_user(u, i) for i, u in enumerate(raw)))


def _user(doc: Mapping[str, Any], index: int) -> UserRecord:
    where = f"{WHERE} [[user]] #{index + 1}"
    table = Table(doc, where)
    table.only(USER_KEYS)
    user_id = table.raw("id")
    if not isinstance(user_id, str) or not user_id:
        raise ConfigurationError(f"{where} id: expected a non-empty string")
    role = table.choice("role", Role.TRADER.value, [r.value for r in Role])
    name = table.raw("name")
    if name is not None and not isinstance(name, str):
        raise ConfigurationError(f"{where} name: expected a string")
    return UserRecord(user_id, Role(role), name or "")


def identity_email(doc: Mapping[str, Any] | None, user_id: str) -> str | None:
    """The sign-in email in ``user_id``'s ``identity.toml`` (lowercased), ``None`` without
    the file or the key. The message never repeats the value (personal data)."""
    if doc is None:
        return None
    where = f"users/{user_id}/{IDENTITY}.toml"
    table = Table(doc, where)
    table.only(IDENTITY_KEYS)
    email = table.raw("email")
    if email is None:
        return None
    if not isinstance(email, str) or "@" not in email.strip():
        raise ConfigurationError(f"{where} email: expected an email address")
    return email.strip().lower()
