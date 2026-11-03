"""Onboard a user (ID5): the identity file it writes, and every refusal."""

import threading
import tomllib
from datetime import UTC, datetime
from typing import Any

import pytest

from algotrade.config.site.settings import load_users
from algotrade.config.site.users import Role
from algotrade.core.model.errors import ConfigurationError, PermissionDeniedError
from algotrade.services.authoring.onboarding import PROVIDER_STEP, onboard_user
from algotrade.services.authoring.scope import ConflictError
from algotrade.storage.configs.writer import MemoryConfigWriter

USERS = {"user": [{"id": "local", "role": "admin"}, {"id": "tom", "role": "trader"}]}


@pytest.fixture
def store() -> MemoryConfigWriter:
    return MemoryConfigWriter(
        {
            ("site", "settings", "users"): USERS,
            ("local", "identity", "identity"): tomllib.loads('email = "boss@example.com"'),
        }
    )


def test_an_admin_onboards_a_trader_with_the_remaining_provider_step(
    store: MemoryConfigWriter,
) -> None:
    before = datetime.now(UTC).replace(microsecond=0)
    done = onboard_user(store, "local", "zoe", " Zoe@Example.COM ", " Zoe Z ")
    assert (done.user_id, done.role, done.pending_provider) == ("zoe", "trader", True)
    assert (done.provider_step.email, done.provider_step.instruction) == (
        "zoe@example.com",
        PROVIDER_STEP,
    )
    assert done.users.get("zoe") is not None
    document = store.load("zoe", "identity", "identity")
    assert document is not None
    assert (document["email"], document["name"], document["declared_by"]) == (
        "zoe@example.com", "Zoe Z", "local",
    )  # fmt: skip
    assert before <= document["declared_at"] <= datetime.now(UTC)
    zoe = load_users(store).get("zoe")
    assert zoe is not None and (zoe.role, zoe.licences, zoe.declared) == (
        Role.TRADER,
        (),
        "identity",
    )
    assert done.users.get("zoe") == zoe  # the registry after the write
    assert store.generation("zoe") > 0 and store.generation("tom") == 0  # user-scoped


def test_the_name_is_optional(store: MemoryConfigWriter) -> None:
    onboard_user(store, "local", "zoe", "zoe@example.com")
    assert "name" not in (store.load("zoe", "identity", "identity") or {})


@pytest.mark.parametrize(
    ("admin", "user_id", "email", "name", "error"),
    [
        ("tom", "zoe", "zoe@example.com", "", PermissionDeniedError),  # a trader
        ("nobody", "zoe", "zoe@example.com", "", PermissionDeniedError),
        ("local", "Bad Id", "zoe@example.com", "", ConfigurationError),
        ("local", "site", "zoe@example.com", "", ConfigurationError),
        ("local", "../x", "zoe@example.com", "", ConfigurationError),
        ("local", "zoe", "not-an-email", "", ConfigurationError),
        ("local", "zoe", "a@b", "", ConfigurationError),
        ("local", "zoe", "z@example.com", "x" * 81, ConfigurationError),
        ("local", "tom", "zoe@example.com", "", ConflictError),  # a users.toml id
        ("local", "local", "zoe@example.com", "", ConflictError),
        ("local", "zoe", "BOSS@example.com", "", ConflictError),  # an email already held
    ],
)
def test_refusals_write_nothing_and_never_echo_the_email(
    store: MemoryConfigWriter,
    admin: str,
    user_id: str,
    email: str,
    name: str,
    error: type[Exception],
) -> None:
    with pytest.raises(error) as raised:
        onboard_user(store, admin, user_id, email, name)
    assert email not in str(raised.value)
    assert store.load("zoe", "identity", "identity") is None
    assert store.generation("tom") == 0


def test_an_id_or_email_already_declared_by_identity_is_taken(store: MemoryConfigWriter) -> None:
    onboard_user(store, "local", "zoe", "zoe@example.com")
    with pytest.raises(ConflictError):
        onboard_user(store, "local", "zoe", "other@example.com")
    with pytest.raises(ConflictError):
        onboard_user(store, "local", "zed", "ZOE@example.com")


def test_an_identity_file_without_an_email_still_holds_its_id(store: MemoryConfigWriter) -> None:
    store.save_identity("zed", {"name": "Zed"})
    with pytest.raises(ConflictError):
        onboard_user(store, "local", "zed", "zed@example.com")


def test_an_identity_declared_user_is_not_an_admin(store: MemoryConfigWriter) -> None:
    onboard_user(store, "local", "zoe", "zoe@example.com")
    with pytest.raises(PermissionDeniedError):
        onboard_user(store, "zoe", "zed", "zed@example.com")


def test_the_registry_is_published_inside_the_write(store: MemoryConfigWriter) -> None:
    seen: list[bool] = []
    onboard_user(
        store,
        "local",
        "zoe",
        "zoe@example.com",
        publish=lambda u: seen.append(u.get("zoe") is not None),
    )
    assert seen == [True]


def test_two_concurrent_onboardings_both_end_in_the_published_registry(
    store: MemoryConfigWriter,
) -> None:
    published: list[object] = []
    names = ["za", "zb", "zc", "zd"]
    threads = [
        threading.Thread(
            target=onboard_user,
            args=(store, "local", n, f"{n}@example.com"),
            kwargs={"publish": published.append},
        )
        for n in names
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    last: Any = published[-1]
    assert len(published) == 4
    assert all(last.get(n) is not None for n in names)


def test_a_lost_race_on_the_identity_file_is_a_conflict(store: MemoryConfigWriter) -> None:
    real = store.save_identity

    def racing(user: str, document: object, *, exclusive: bool = False) -> None:
        real(user, {"email": "other@example.com"})  # someone else got there first
        real(user, document, exclusive=exclusive)

    store.save_identity = racing  # type: ignore[method-assign]
    with pytest.raises(ConflictError):
        onboard_user(store, "local", "zoe", "zoe@example.com")


def test_an_email_in_an_orphan_identity_file_is_taken(store: MemoryConfigWriter) -> None:
    store.save_identity("ghost", {"email": "Ghost@Example.com", "declared_by": "departed"})
    with pytest.raises(ConflictError) as raised:
        onboard_user(store, "local", "zoe", "ghost@example.com")
    assert "example.com" not in str(raised.value)
    with pytest.raises(ConflictError):
        onboard_user(store, "local", "ghost", "new@example.com")  # its id too
