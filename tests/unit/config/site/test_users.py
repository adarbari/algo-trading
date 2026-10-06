"""The user registry (ADR 0040): roles, defaults and validation of users.toml."""

import pytest

from algotrade.config.site.settings import load_users
from algotrade.config.site.users import Role, UserRecord, UsersSettings, identity_email
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


def test_load_users_reads_the_site_document_and_each_users_identity() -> None:
    loaded: list[tuple[str, str, str]] = []

    class Docs:
        def load(self, scope: str, kind: str, name: str) -> dict[str, object] | None:
            loaded.append((scope, kind, name))
            if (scope, kind, name) == ("site", "settings", "users"):
                return {"user": [{"id": "ana", "role": "admin"}, {"id": "site", "role": "admin"}]}
            assert (kind, name) == ("identity", "identity")
            return {"email": " Ana@Example.COM "} if scope == "ana" else None

        def names(self, scope: str, kind: str) -> list[str]:
            return []

    users = load_users(Docs())  # type: ignore[arg-type]
    assert users.role_of("ana") is Role.ADMIN
    assert users.by_email("ana@example.com") == users.get("ana")
    assert ("site", "identity", "identity") not in loaded  # the site user never signs in


def test_emails_map_to_users_case_ignored() -> None:
    users = UsersSettings((UserRecord("ana", Role.ADMIN), UserRecord("tom", Role.TRADER)))
    users = users.with_emails({"ana": "ana@example.com"})
    found = users.by_email("ANA@example.com")
    assert found is not None and found.user_id == "ana"
    assert users.by_email("tom@example.com") is None
    assert users.get("tom") == UserRecord("tom", Role.TRADER)


def test_an_email_belongs_to_one_user() -> None:
    users = UsersSettings((UserRecord("ana", Role.ADMIN), UserRecord("tom", Role.TRADER)))
    with pytest.raises(ConfigurationError, match="same email"):
        users.with_emails({"ana": "a@example.com", "tom": "a@example.com"})


def test_the_site_user_has_no_email() -> None:
    with pytest.raises(ConfigurationError, match="no email"):
        UserRecord("site", Role.ADMIN, email="s@example.com")


@pytest.mark.parametrize(
    ("doc", "email"),
    [(None, None), ({}, None), ({"email": "A@Example.com"}, "a@example.com")],
)
def test_identity_email(doc: dict[str, object] | None, email: str | None) -> None:
    assert identity_email(doc, "ana") == email


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"email": "not-an-address"}, r"email: expected an email address"),
        ({"email": 3}, r"email: expected an email address"),
        ({"email": "a@example.com", "password": "x"}, r"unknown keys"),
    ],
)
def test_invalid_identity_is_refused_without_echoing_it(
    doc: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message) as raised:
        identity_email(doc, "ana")
    assert "not-an-address" not in str(raised.value)
