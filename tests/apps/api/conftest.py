"""The API over the golden ``api_golden`` store (tests/conftest.py)."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.storage.configs.files import FileConfigStore
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.conftest import REPO_ROOT


@pytest.fixture(scope="session")
def ids(api_golden: tuple[ReadStore, dict[str, str]]) -> dict[str, str]:
    return api_golden[1]


@pytest.fixture(scope="session")
def client(api_golden: tuple[ReadStore, dict[str, str]]) -> TestClient:
    return TestClient(create_app(ApiSettings("memory://", "config"), api_golden[0]))


# A user feature of alice's (config/users/alice/features/vol.toml): hv20 in percent.
USER_FEATURES = """[hv20_pct]
expr = "price_stats.hv20 * 100"
dtype = "float"
unit = "pct_points"
description = "20-session historical volatility, in percent"
null_meaning = "hv20 is null"
"""


@pytest.fixture(scope="session")
def user_client(
    api_golden: tuple[ReadStore, dict[str, str]], tmp_path_factory: pytest.TempPathFactory
) -> Callable[[str], TestClient]:
    """A client for ``user`` (``ALGOTRADE_USER``) over configs where alice has a feature."""
    root: Path = tmp_path_factory.mktemp("configs")
    (root / "site").symlink_to(REPO_ROOT / "config" / "site")
    (root / "users" / "alice" / "features").mkdir(parents=True)
    (root / "users" / "alice" / "features" / "vol.toml").write_text(USER_FEATURES)
    (root / "users" / "bob").mkdir()

    def client_for(user: str) -> TestClient:
        store = replace(api_golden[0], configs=FileConfigStore(root), user=UserContext(user))
        return TestClient(create_app(ApiSettings("memory://", str(root), user), store))

    return client_for
