import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.readers import StoreReader
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.golden import load_golden
from algotrade_ingestion.sources.synthetic.files import GoldenFiles

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "datasets" / "golden"

# HYPOTHESIS_PROFILE=nightly runs far more examples on the scheduled workflow.
settings.register_profile("dev", max_examples=30, deadline=None)
settings.register_profile("ci", max_examples=100, deadline=None, print_blob=True)
settings.register_profile(
    "nightly", max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(scope="session")
def golden_files() -> GoldenFiles:
    return GoldenFiles(GOLDEN_DIR)


@pytest.fixture(scope="session")
def golden_reader(golden_files: GoldenFiles) -> StoreReader:
    """The golden datasets loaded through the real ingestion job into an in-memory store."""
    backend = MemoryBackend()
    load_golden(StoreWriter(backend), golden_files)
    return StoreReader(backend)


@pytest.fixture(scope="session")
def golden_url(tmp_path_factory: pytest.TempPathFactory, golden_files: GoldenFiles) -> str:
    """A local (Parquet) fixture store with the golden datasets, for CLI tests."""
    root = tmp_path_factory.mktemp("golden-store")
    load_golden(StoreWriter(LocalBackend(root)), golden_files)
    return f"file://{root}"


@pytest.fixture(autouse=True)
def _no_live_vendor_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never reach live vendors, even if a developer's .env holds real keys."""
    monkeypatch.setenv("ALGOTRADE_MASSIVE_API_KEY", "")
    monkeypatch.setenv("ALGOTRADE_SEC_CONTACT", "")
