"""The user registry (ADR 0040): roles, defaults and validation of users.toml."""

import pytest

from algotrade.config.site.settings import load_users
from algotrade.config.site.users import Role, UserRecord, UsersSettings
from algotrade.core.model.errors import ConfigurationError


def test_missing_file_is_the_single_user_install() -> None:
    users = UsersSettings.from_document(None)
    assert users.role_of("local") is Role.ADMIN
    assert users.role_of("site") is Role.ADMIN
    assert users.get("nobody") is None
    assert UsersSettings.from_document({}) == users


def test_roles_gate_workspaces() -> None:
    users = UsersSettings.from_document(
        {"user": [{"id": "ana", "role": "admin"}, {"id": "tom", "role": "trader", "name": "Tom"}]}
    )
    assert users.may_enter("ana", "admin") and users.may_enter("ana", "trader")
    assert users.may_enter("tom", "trader") and not users.may_enter("tom", "admin")
    assert not users.may_enter("nobody", "trader")
    assert users.get("tom") == UserRecord("tom", Role.TRADER, "Tom")


def test_role_defaults_to_trader() -> None:
    users = UsersSettings.from_document({"user": [{"id": "ana", "role": "admin"}, {"id": "t"}]})
    assert users.role_of("t") is Role.TRADER


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"user": "ana"}, r"expected an array of tables"),
        ({"users": []}, r"unknown keys"),
        ({"user": [{"id": "ana", "role": "root"}]}, r"role: expected one of"),
        ({"user": [{"id": "", "role": "admin"}]}, r"id: expected a non-empty string"),
        ({"user": [{"id": "ana", "role": "admin", "email": "x"}]}, r"unknown keys"),
        ({"user": [{"id": "ana", "role": "admin", "name": 3}]}, r"name: expected a string"),
        ({"user": [{"id": "ana", "role": "admin"}, {"id": "ana"}]}, r"declared twice"),
        ({"user": [{"id": "tom", "role": "trader"}]}, r"at least one user must have role"),
    ],
)
def test_invalid_documents_name_the_key(doc: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        UsersSettings.from_document(doc)


def test_unknown_user_is_refused() -> None:
    with pytest.raises(ConfigurationError, match="unknown user 'x'"):
        UsersSettings().role_of("x")


def test_load_users_reads_the_site_document() -> None:
    class Docs:
        def load(self, scope: str, kind: str, name: str) -> dict[str, object] | None:
            assert (scope, kind, name) == ("site", "settings", "users")
            return {"user": [{"id": "ana", "role": "admin"}]}

        def names(self, scope: str, kind: str) -> list[str]:
            return []

    assert load_users(Docs()).role_of("ana") is Role.ADMIN  # type: ignore[arg-type]
