"""The API over the ``explore`` store (tests/conftest.py)."""

import pytest
from fastapi.testclient import TestClient

from algotrade.services.explore.store import ReadStore
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app


@pytest.fixture(scope="session")
def ids(explore: tuple[ReadStore, dict[str, str]]) -> dict[str, str]:
    return explore[1]


@pytest.fixture(scope="session")
def client(explore: tuple[ReadStore, dict[str, str]]) -> TestClient:
    return TestClient(create_app(ApiSettings("memory://", "config"), explore[0]))
