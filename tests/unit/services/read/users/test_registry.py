"""The user registry: the declared people for an admin, never the identity, nothing for a trader."""

from unittest.mock import MagicMock, patch

import pytest

from algotrade.config.site.users import Role, UserRecord, UsersSettings
from algotrade.config.user import SITE_USER
from algotrade.core.model.errors import PermissionDeniedError
from algotrade.services.read.users import registry
from algotrade.services.read.users.viewer import Viewer

USERS = UsersSettings(
    (
        UserRecord("ana", Role.ADMIN, "Ana", "ana@example.com", licences=("personal",)),
        UserRecord("tom", Role.TRADER, "Tom"),
        UserRecord(SITE_USER, Role.ADMIN, "Scheduled site screens"),
    )
)


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.configs = object()
    return ctx


def test_an_admin_reads_the_declared_people_without_identity() -> None:
    with patch.object(registry, "load_users", return_value=USERS):
        found = registry.load_user_registry(_ctx(), Viewer("ana", "Ana", "admin", ("admin",)))
    assert [(p.user_id, p.role, p.licences, p.scheduled) for p in found.people] == [
        ("ana", "admin", ("personal",), False),
        ("tom", "trader", (), False),
        (SITE_USER, "admin", (), True),
    ]
    assert "ana@example.com" not in repr(found)


def test_a_trader_is_refused_before_anything_is_read() -> None:
    trader = Viewer("tom", "", "trader", ())
    with (
        patch.object(registry, "load_users", side_effect=AssertionError("read")),
        pytest.raises(PermissionDeniedError),
    ):
        registry.load_user_registry(_ctx(), trader)
