"""A test Supabase project (``tokens`` in tests/apps/api/conftest.py) and a registry with
two signed-up users: ana (admin) and tom (trader)."""

import pytest

from algotrade.config.site.users import Role, UserRecord, UsersSettings


@pytest.fixture
def users() -> UsersSettings:
    return UsersSettings(
        (
            UserRecord("ana", Role.ADMIN, "Ana", "ana@example.com"),
            UserRecord("tom", Role.TRADER, "Tom", "tom@example.com"),
            UserRecord("site", Role.ADMIN),
        )
    )
