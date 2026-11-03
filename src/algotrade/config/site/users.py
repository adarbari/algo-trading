"""The user registry (ADR 0040): ``config/site/users.toml`` typed into ``UsersSettings``.

Every user the API and the CLIs may act for is declared here with a role (``admin`` enters the
ADMIN workspace and the ops reads; ``trader`` the TRADER workspace). Their configs stay in
``config/users/<id>/`` (ADR 0015): the registry only says who exists and what they may do. A
missing file is the single-user install: ``local`` as ``admin`` and ``site`` for scheduled
site screens, so nothing changes until a second user is declared. How a user proves who they
are (login) is the API's concern (ADR 0040); the email a sign-in maps to is not in the public
site file but in the user's own git-ignored ``config/users/<id>/identity.toml`` (``email``, and
optionally ``subject``: the Supabase user id a token's ``sub`` must then equal), attached by
``with_identities``. ``settings.load_users`` reads the files, this module does no I/O.

An identity file may also carry ``name``, ``declared_by`` (the admin's id) and ``declared_at``
(UTC): the onboarding write (ID5, ``services.authoring.onboarding``) declares a user there. A
user with an identity email and no ``users.toml`` entry joins the registry as a ``trader`` with
no licences (``declared = "identity"``) only when its ``declared_by`` names an admin of the
registry (a file without one, or from a user no longer an admin, grants nothing); a
``users.toml`` entry always wins, and ``admin`` or a licence
is granted only by the public file (ADR 0040, decision log 2026-11-02).

``licences`` lists the data licences a user holds beyond the open one (ADR 0064 decision 10,
ADR 0028): ``personal`` and ``yahoo`` (Yahoo-derived analyst values, ADR 0080) are the owner's
alone today. Only a holder is served per-name values derived from a feature under that licence;
everyone else sees them as ``LICENCE``.
"""

import logging
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.config.site.macro import HELD_LICENCES
from algotrade.config.user import DEFAULT_USER, SITE_USER, validate_id
from algotrade.core.model.errors import ConfigurationError

log = logging.getLogger(__name__)
WHERE = "users.toml"
USER_KEYS = ("id", "role", "name", "licences")
IDENTITY = "identity"  # config/users/<id>/identity.toml: the user's sign-in identity
IDENTITY_KEYS = ("email", "subject", "name", "declared_by", "declared_at")
DECLARED_BY_IDENTITY = "identity"  # ``UserRecord.declared`` of a user only an identity file names


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
    subject: str | None = None  # the pinned Supabase user id (a UUID), when set
    licences: tuple[str, ...] = ()  # data licences held beyond "open" (ADR 0064): "personal"
    declared: str = ""  # "identity": not in users.toml, declared by the onboarding write
    declared_by: str | None = None  # the admin who onboarded the user (identity.toml)
    declared_at: datetime | None = None  # when (UTC; identity.toml)

    def __post_init__(self) -> None:
        validate_id("user", self.user_id)
        unknown = sorted(set(self.licences) - set(HELD_LICENCES))
        if unknown:
            raise ConfigurationError(f"user '{self.user_id}' licences: unknown {unknown}")
        if "yahoo" in self.licences and "personal" not in self.licences:
            # a column's licence is the strictest of what it reads (``yahoo`` over ``personal``),
            # and the gate asks for that exact licence: a holder of ``yahoo`` alone would be
            # served an expression over an IBKR (``personal``) and an analyst feature (ADR 0080)
            raise ConfigurationError(f"user '{self.user_id}' licences: yahoo needs personal")
        if self.subject is not None:
            object.__setattr__(self, "subject", _subject(self.subject, f"user '{self.user_id}'"))
        if self.email is None and self.subject is None:
            return
        if self.user_id == SITE_USER:
            raise ConfigurationError(f"user '{SITE_USER}' runs scheduled screens: no identity")
        if self.email is None:
            raise ConfigurationError(f"user '{self.user_id}': a subject needs an email")
        email = self.email.strip().lower()
        if "@" not in email:
            raise ConfigurationError(f"user '{self.user_id}' email: expected an email address")
        object.__setattr__(self, "email", email)  # frozen: normalised once, here


DEFAULT_USERS: tuple[UserRecord, ...] = (
    UserRecord(DEFAULT_USER, Role.ADMIN, "Local user", licences=("personal", "yahoo")),  # the owner
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

    def with_identities(self, identities: Mapping[str, "Identity"]) -> "UsersSettings":
        """These users with the identities ``identities`` maps their ids to (``identity``)."""
        none = Identity()
        known = tuple(
            replace(
                u,
                email=found.email,
                subject=found.subject,
                declared_by=found.declared_by,
                declared_at=found.declared_at,
            )
            for u in self.users
            for found in (identities.get(u.user_id, none),)
        )
        taken = {u.email for u in known if u.email is not None}
        joined: list[UserRecord] = []
        for uid, found in identities.items():  # an identity with an email, no users.toml entry
            if found.email is None or uid == SITE_USER or self.get(uid) is not None:
                continue
            if not self._is_admin(found.declared_by):
                continue
            if found.email in taken:  # a later duplicate is skipped, never an error
                log.warning("identity.toml of user folder %r repeats an email: ignored", uid)
                continue
            taken.add(found.email)
            joined.append(
                UserRecord(
                    uid,
                    Role.TRADER,
                    found.name,
                    found.email,
                    found.subject,
                    declared=DECLARED_BY_IDENTITY,
                    declared_by=found.declared_by,
                    declared_at=found.declared_at,
                )
            )
        return UsersSettings(known + tuple(joined))

    def _is_admin(self, user_id: str | None) -> bool:
        """Whether ``user_id`` is an admin of this registry (``users.toml`` or the defaults)."""
        admin = None if user_id is None or user_id == SITE_USER else self.get(user_id)
        return admin is not None and admin.role is Role.ADMIN

    def read_identities(
        self, load: Callable[[str], Mapping[str, Any] | None], folders: Iterable[str]
    ) -> dict[str, "Identity"]:
        """The identity of every candidate (``identity_candidates``): strict for a declared user,
        while a malformed file of any other folder is skipped and logged (no values), so one
        stray file never takes the registry down."""
        found: dict[str, Identity] = {}
        for uid in self.identity_candidates(folders):
            try:
                found[uid] = identity(load(uid), uid)
            except ConfigurationError:
                if self.get(uid) is not None:
                    raise
                log.warning("identity.toml of user folder %r is malformed: ignored", uid)
        return found

    def identity_candidates(self, folders: Iterable[str]) -> list[str]:
        """The ids whose ``identity.toml`` is read: every declared user but ``site``, then the
        user folders that are valid ids (a stray folder is not an error)."""
        ids = [u.user_id for u in self.users] + [f for f in folders if _valid_id(f)]
        return [i for i in dict.fromkeys(ids) if i != SITE_USER]

    def role_of(self, user_id: str) -> Role:
        user = self.get(user_id)
        if user is None:
            raise ConfigurationError(f"{WHERE}: unknown user '{user_id}'")
        return user.role

    def holds(self, user_id: str, licence: str) -> bool:
        """Whether ``user_id`` may see values under ``licence`` (``open``: everyone; any other
        only a user who lists it; unknown users hold nothing but ``open``)."""
        if licence == "open":
            return True
        user = self.get(user_id)
        return user is not None and licence in user.licences

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
    licences = table.strings("licences", ())
    return UserRecord(user_id, Role(role), name or "", licences=licences)


@dataclass(frozen=True)
class Identity:
    """What ``identity.toml`` says about a user: the sign-in email and the pinned subject."""

    email: str | None = None
    subject: str | None = None
    name: str = ""
    declared_by: str | None = None
    declared_at: datetime | None = None


def _valid_id(value: str) -> bool:
    try:
        validate_id("user", value)
    except ConfigurationError:
        return False
    return True


def identity(doc: Mapping[str, Any] | None, user_id: str) -> Identity:
    """``user_id``'s ``identity.toml``: the email (lowercased) and the optional ``subject``
    (the Supabase user id, a UUID); empty without the file. Messages never repeat a value
    (personal data)."""
    if doc is None:
        return Identity()
    where = f"users/{user_id}/{IDENTITY}.toml"
    table = Table(doc, where)
    table.only(IDENTITY_KEYS)
    email, subject = table.raw("email"), table.raw("subject")
    name, by, at = table.raw("name"), table.raw("declared_by"), table.raw("declared_at")
    if name is not None and not isinstance(name, str):
        raise ConfigurationError(f"{where} name: expected a string")
    if by is not None and not isinstance(by, str):
        raise ConfigurationError(f"{where} declared_by: expected a user id")
    if at is not None and (not isinstance(at, datetime) or at.tzinfo is None):
        raise ConfigurationError(f"{where} declared_at: expected a UTC date-time")
    if email is not None and (not isinstance(email, str) or "@" not in email):
        raise ConfigurationError(f"{where} email: expected an email address")
    if subject is not None and email is None:
        raise ConfigurationError(f"{where} subject: needs an email")
    return Identity(
        email.strip().lower() if isinstance(email, str) else None,
        _subject(subject, where) if subject is not None else None,
        (name or "").strip(),
        by,
        at,
    )


def _subject(value: object, where: str) -> str:
    """A Supabase user id, normalised (lowercase, hyphenated); never echoed."""
    try:
        return str(uuid.UUID(str(value))) if isinstance(value, str) else _bad(where)
    except ValueError:
        return _bad(where)


def _bad(where: str) -> str:
    raise ConfigurationError(f"{where} subject: expected the Supabase user id (a UUID)")
