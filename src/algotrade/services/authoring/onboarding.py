"""Onboard a user (ID5; ADR 0040, 0044, decision log 2026-11-02): one admin-only write that
declares a trader in the caller's own config folder and nothing else.

The write is ``config/users/<id>/identity.toml`` (``email``, ``name``, ``declared_by``,
``declared_at`` in UTC); ``settings.load_users`` then lists the user as a ``trader`` with no
licences (``declared = "identity"``). It never touches ``users.toml`` (public, changed by PR:
the only grant of ``admin`` or a licence), and never calls the identity provider: the API holds
no service-role key. The account itself is created by the admin in the provider's dashboard, so
the result carries ``pending_provider`` (until the first sign-in pins the user's ``subject``)
and the one remaining step as data (``ProviderStep``: the email and a fixed instruction id the
web maps to a Guide entry; no prose here).

Refused (``ConfigurationError`` 400, ``ConflictError`` 409, ``PermissionDeniedError`` 403): a
caller who is not an admin, an invalid id, ``site``, an id the registry already has (from
``users.toml`` or an identity file), an email already held by anyone, an invalid email. Messages
never repeat the email. The registry is read inside one lock together with the write, so two
onboardings cannot take the same id or email; ``publish`` is called with the registry after the
write, inside that lock (the API swaps its own there)."""

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from algotrade.config.site.settings import load_users
from algotrade.config.site.users import IDENTITY, Role, UsersSettings
from algotrade.config.user import SITE_USER, validate_id
from algotrade.core.model.errors import ConfigurationError, PermissionDeniedError
from algotrade.services.authoring.scope import ConfigWriter, ConflictError

PROVIDER_STEP = "supabase_add_user"  # the web's Guide key for: add the email in Supabase
MAX_EMAIL = 254
MAX_NAME = 80
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_LOCK = threading.Lock()


@dataclass(frozen=True)
class ProviderStep:
    """What the admin still does at the identity provider: ``instruction`` is a fixed id, never
    prose; ``email`` the address to add."""

    email: str
    instruction: str = PROVIDER_STEP


@dataclass(frozen=True)
class Onboarded:
    user_id: str
    role: str
    pending_provider: bool
    provider_step: ProviderStep
    users: UsersSettings  # the registry after the write


def _email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > MAX_EMAIL or not EMAIL.fullmatch(email):
        raise ConfigurationError("email: expected an email address")
    return email


def _name(value: str) -> str:
    name = value.strip()
    if len(name) > MAX_NAME or not name.isprintable():
        raise ConfigurationError(f"name: at most {MAX_NAME} printable characters")
    return name


def onboard_user(
    writer: ConfigWriter,
    admin: str,
    user_id: str,
    email: str,
    name: str = "",
    publish: Callable[[UsersSettings], None] | None = None,
) -> Onboarded:
    """Declare ``user_id`` (a trader) with ``email`` on behalf of ``admin``, who must be an
    admin of the current registry (``PermissionDeniedError`` otherwise). ``publish`` receives the
    registry after the write, inside the lock, so concurrent onboardings never publish a stale
    one."""
    wanted = _email(email)
    label = _name(name)
    if user_id == SITE_USER:
        raise ConfigurationError(f"user '{SITE_USER}' runs scheduled screens: it is not onboarded")
    who = validate_id("user", user_id)
    with _LOCK:
        users = load_users(writer)
        caller = users.get(admin)
        if caller is None or caller.role is not Role.ADMIN:
            raise PermissionDeniedError("only an admin onboards a user")
        if users.get(who) is not None or writer.load(who, IDENTITY, IDENTITY) is not None:
            raise ConflictError(f"user '{who}' already exists")
        held = (writer.load(u, IDENTITY, IDENTITY) or {} for u in writer.users())
        if users.by_email(wanted) is not None or any(
            str(doc.get("email", "")).strip().lower() == wanted for doc in held
        ):  # any identity file, an orphan of a departed admin included
            raise ConflictError("that email already belongs to a user")
        document: dict[str, object] = {"email": wanted}
        if label:
            document["name"] = label
        document["declared_by"] = admin
        document["declared_at"] = datetime.now(UTC).replace(microsecond=0)
        try:
            writer.save_identity(who, document, exclusive=True)
        except FileExistsError:
            raise ConflictError(f"user '{who}' already exists") from None
        after = load_users(writer)
        if publish is not None:
            publish(after)
    return Onboarded(who, Role.TRADER.value, True, ProviderStep(wanted), after)
