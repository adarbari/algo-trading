"""A client over a temporary config root (site defaults + features from the repo, a rule
preset ``vrp@3``) whose user configs the write routes change."""

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.services.explore.store import ReadStore
from algotrade.storage.configs.writer import FileConfigWriter
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.conftest import REPO_ROOT

SELECTION = """name = "all_active"
[where]
all = [{field = "instrument.status", op = "eq", value = "ACTIVE"}]
"""
PRESET = """id = "vrp"
kind = "screener"
impl = "rules"
version = 3
selection = "all_active"

[criteria.price]
field = "rollup.price_stats@v2.close"
op = "gt"
value = 5
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    (site / "presets" / "selections").mkdir(parents=True)
    (site / "presets" / "screeners").mkdir()
    (site / "features").symlink_to(REPO_ROOT / "config" / "site" / "features")
    (site / "defaults.toml").symlink_to(REPO_ROOT / "config" / "site" / "defaults.toml")
    (site / "presets" / "selections" / "all_active.toml").write_text(SELECTION)
    (site / "presets" / "screeners" / "vrp.toml").write_text(PRESET)
    return tmp_path


@pytest.fixture
def writer_client(explore: tuple[ReadStore, dict[str, str]], root: Path) -> TestClient:
    writer = FileConfigWriter(root)
    store = replace(explore[0], configs=writer, user=UserContext("local"))
    return TestClient(create_app(ApiSettings("memory://", str(root)), store, writer))
