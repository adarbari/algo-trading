"""The user registry (ADR 0040): roles, defaults and validation of users.toml."""

import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.site.settings import load_users
from algotrade.config.site.users import Identity, Role, UserRecord, UsersSettings, identity
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
            return {"email": " Ana@Example.COM ", "subject": SUBJECT} if scope == "ana" else None

        def names(self, scope: str, kind: str) -> list[str]:
            return []

        def users(self) -> list[str]:
            return ["ana"]

    users = load_users(Docs())  # type: ignore[arg-type]
    assert users.role_of("ana") is Role.ADMIN
    assert users.by_email("ana@example.com") == users.get("ana")
    assert users.get("ana") == UserRecord("ana", Role.ADMIN, "", "ana@example.com", SUBJECT)
    assert ("site", "identity", "identity") not in loaded  # the site user never signs in


def test_emails_map_to_users_case_ignored() -> None:
    users = UsersSettings((UserRecord("ana", Role.ADMIN), UserRecord("tom", Role.TRADER)))
    users = users.with_identities({"ana": Identity("ana@example.com")})
    found = users.by_email("ANA@example.com")
    assert found is not None and found.user_id == "ana"
    assert users.by_email("tom@example.com") is None
    assert users.get("tom") == UserRecord("tom", Role.TRADER)


def test_an_email_belongs_to_one_user() -> None:
    users = UsersSettings((UserRecord("ana", Role.ADMIN), UserRecord("tom", Role.TRADER)))
    with pytest.raises(ConfigurationError, match="same email"):
        users.with_identities({"ana": Identity("a@example.com"), "tom": Identity("a@example.com")})


def test_a_records_identity_is_normalised_and_checked() -> None:
    record = UserRecord("ana", Role.ADMIN, email=" Ana@Example.com ", subject=SUBJECT)
    assert (record.email, record.subject) == ("ana@example.com", SUBJECT.lower())
    with pytest.raises(ConfigurationError, match="expected an email address"):
        UserRecord("ana", Role.ADMIN, email="nope")
    with pytest.raises(ConfigurationError, match="needs an email"):
        UserRecord("ana", Role.ADMIN, subject=SUBJECT)


def test_the_site_user_has_no_email() -> None:
    with pytest.raises(ConfigurationError, match="no identity"):
        UserRecord("site", Role.ADMIN, email="s@example.com")


SUBJECT = "7B1C1D2E-0000-4000-8000-000000000001"


@pytest.mark.parametrize(
    ("doc", "found"),
    [
        (None, Identity()),
        ({}, Identity()),
        ({"email": "A@Example.com"}, Identity("a@example.com")),
        ({"email": "a@x.io", "subject": SUBJECT}, Identity("a@x.io", SUBJECT.lower())),
    ],
)
def test_identity(doc: dict[str, object] | None, found: Identity) -> None:
    assert identity(doc, "ana") == found


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"email": "not-an-address"}, r"email: expected an email address"),
        ({"email": 3}, r"email: expected an email address"),
        ({"email": "a@example.com", "password": "x"}, r"unknown keys"),
        ({"email": "a@example.com", "subject": "not-an-address"}, r"subject: expected"),
        ({"subject": SUBJECT}, r"subject: needs an email"),
    ],
)
def test_invalid_identity_is_refused_without_echoing_it(
    doc: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message) as raised:
        identity(doc, "ana")
    assert "not-an-address" not in str(raised.value)


def test_licences_are_held_only_by_the_users_who_list_them() -> None:
    """ADR 0064 decision 10: personal-licence per-name values only to the licence holder."""
    users = UsersSettings.from_document(
        {"user": [{"id": "owner", "role": "admin", "licences": ["personal"]},
                  {"id": "guest", "role": "trader"}]}
    )  # fmt: skip
    assert users.holds("owner", "personal") and not users.holds("guest", "personal")
    assert users.holds("guest", "open") and not users.holds("nobody", "personal")
    with pytest.raises(ConfigurationError, match="licences"):
        UsersSettings.from_document({"user": [{"id": "a", "role": "admin", "licences": ["x"]}]})
    with pytest.raises(ConfigurationError, match="licences"):
        UsersSettings.from_document(
            {"user": [{"id": "a", "role": "admin", "licences": "personal"}]}
        )


def test_the_single_user_install_holds_the_personal_licence() -> None:
    """Without users.toml, ``local`` is the owner: their own personal-licence values show."""
    users = UsersSettings.from_document(None)
    assert users.holds("local", "personal") and not users.holds("site", "personal")
    assert users.holds("local", "yahoo") and not users.holds("site", "yahoo")  # ADR 0080


def test_the_committed_registry_gives_the_personal_licence_to_the_owner_only() -> None:
    doc = tomllib.loads(Path("config/site/users.toml").read_text())
    users = UsersSettings.from_document(doc)
    assert [u.user_id for u in users.users if "personal" in u.licences] == ["local"]
    assert [u.user_id for u in users.users if "yahoo" in u.licences] == ["local"]  # ADR 0080


def test_yahoo_requires_personal() -> None:
    """ADR 0080: ``yahoo`` is the strictest licence and gates by exact match, so holding it
    without ``personal`` would serve IBKR values inside an expression over both."""
    with pytest.raises(ConfigurationError, match="yahoo needs personal"):
        UserRecord("a", Role.TRADER, licences=("yahoo",))
    assert UserRecord("a", Role.TRADER, licences=("personal", "yahoo")).licences


class Folders:
    """A store of identity files by user id, over an optional ``users.toml`` document."""

    def __init__(
        self, identities: dict[str, dict[str, object]], users_toml: dict[str, Any] | None = None
    ) -> None:
        self._identities, self._users_toml = identities, users_toml

    def load(self, scope: str, kind: str, name: str) -> dict[str, object] | None:
        if (scope, kind, name) == ("site", "settings", "users"):
            return self._users_toml
        assert (kind, name) == ("identity", "identity")
        return self._identities.get(scope)

    def names(self, scope: str, kind: str) -> list[str]:
        return []

    def overrides(self, name: str) -> list[dict[str, str]]:
        return []

    def users(self) -> list[str]:
        return ["Not A Folder", *self._identities]


NAIVE = datetime(2026, 1, 1)  # noqa: DTZ001 - a naive time is the case refused
DECLARED_AT = datetime(2026, 11, 2, 9, 30, tzinfo=UTC)
ONBOARDED = {
    "email": "Zoe@Example.com",
    "name": "Zoe",
    "declared_by": "local",
    "declared_at": DECLARED_AT,
}


def test_an_identity_without_a_registry_entry_joins_as_a_trader_without_licences() -> None:
    users = load_users(Folders({"zoe": ONBOARDED}))
    zoe = users.get("zoe")
    assert zoe == UserRecord(
        "zoe", Role.TRADER, "Zoe", "zoe@example.com", declared="identity",
        declared_by="local", declared_at=DECLARED_AT,
    )  # fmt: skip
    assert users.by_email("ZOE@example.com") == zoe
    assert not users.holds("zoe", "personal") and users.holds("zoe", "open")
    assert users.may_enter("zoe", "trader") and not users.may_enter("zoe", "admin")
    assert users.get("local") is not None  # the defaults stay


def test_a_registry_entry_wins_over_its_identity_declaration() -> None:
    registry = {"user": [{"id": "local", "role": "admin", "licences": ["personal"]}]}
    users = load_users(Folders({"local": ONBOARDED | {"name": "Other"}}, registry))
    local = users.get("local")
    assert local is not None
    assert (local.role, local.licences, local.name, local.declared) == (
        Role.ADMIN,
        ("personal",),
        "",
        "",
    )
    assert local.email == "zoe@example.com"  # the file still supplies the sign-in email


def test_identities_without_an_email_site_and_stray_folders_never_join() -> None:
    users = load_users(Folders({"zed": {"name": "Zed"}, "site": ONBOARDED}))
    assert users.get("zed") is None and users.by_email("zoe@example.com") is None
    assert [u.user_id for u in users.users] == ["local", "site"]


def test_two_registry_users_cannot_share_an_email() -> None:
    registry = {"user": [{"id": "local", "role": "admin"}, {"id": "tom", "role": "trader"}]}
    folders = Folders(
        {"local": {"email": "a@example.com"}, "tom": {"email": "a@example.com"}}, registry
    )
    with pytest.raises(ConfigurationError, match="same email") as raised:
        load_users(folders)
    assert "a@example.com" not in str(raised.value)


def test_an_identity_user_repeating_a_registry_users_email_is_skipped() -> None:
    registry = {"user": [{"id": "local", "role": "admin"}]}
    folders = Folders(
        {"local": {"email": "z@example.com"}, "zoe": ONBOARDED | {"email": "z@example.com"}},
        registry,
    )
    users = load_users(folders)
    assert users.get("zoe") is None and users.by_email("z@example.com") == users.get("local")


def test_identity_reads_the_declaration_keys_and_refuses_bad_ones_without_echo() -> None:
    found = identity(ONBOARDED, "zoe")
    assert (found.name, found.declared_by, found.declared_at) == ("Zoe", "local", DECLARED_AT)
    for doc, message in (
        ({"email": "a@b.io", "name": 3}, "name: expected a string"),
        ({"email": "a@b.io", "declared_by": 3}, "declared_by: expected a user id"),
        ({"email": "a@b.io", "declared_at": "yesterday"}, "declared_at: expected a UTC date-time"),
        ({"email": "a@b.io", "declared_at": NAIVE}, "declared_at: expected"),
    ):
        with pytest.raises(ConfigurationError, match=message) as raised:
            identity(doc, "zoe")
        assert "a@b.io" not in str(raised.value) and "yesterday" not in str(raised.value)


@pytest.mark.parametrize(
    "declared_by", [None, "tom", "ghost", "site"], ids=["none", "trader", "unknown", "site"]
)
def test_an_identity_joins_only_when_a_current_admin_declared_it(declared_by: str | None) -> None:
    registry = {"user": [{"id": "local", "role": "admin"}, {"id": "tom", "role": "trader"}]}
    doc: dict[str, object] = {k: v for k, v in ONBOARDED.items() if k != "declared_by"}
    if declared_by is not None:
        doc["declared_by"] = declared_by
    users = load_users(Folders({"zoe": doc}, registry))
    assert users.get("zoe") is None and users.by_email("zoe@example.com") is None


def test_a_user_whose_declaring_admin_left_the_registry_no_longer_joins() -> None:
    registry = {"user": [{"id": "boss", "role": "admin"}]}  # local is gone
    users = load_users(Folders({"zoe": ONBOARDED}, registry))
    assert users.get("zoe") is None


def test_a_malformed_identity_of_an_undeclared_folder_is_skipped_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bad: dict[str, object] = {"email": "secret@example.com", "password": "x"}
    with caplog.at_level("WARNING"):
        users = load_users(Folders({"zoe": ONBOARDED, "stray": bad}))
    assert users.get("zoe") is not None and users.get("stray") is None
    assert "stray" in caplog.text and "secret@example.com" not in caplog.text


def test_a_malformed_identity_of_a_declared_user_stays_an_error() -> None:
    with pytest.raises(ConfigurationError, match="unknown keys"):
        load_users(Folders({"local": {"email": "a@b.io", "password": "x"}}))


def test_a_later_identity_user_repeating_an_email_is_skipped_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        users = load_users(Folders({"zoe": ONBOARDED, "zed": ONBOARDED | {"name": "Zed"}}))
    assert users.get("zoe") is not None and users.get("zed") is None
    assert "zed" in caplog.text and "zoe@example.com" not in caplog.text


def test_admin_is_a_reserved_scope_never_a_user_id() -> None:
    with pytest.raises(ConfigurationError, match="reserved config scope"):
        UserRecord("admin", Role.TRADER)
