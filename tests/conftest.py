import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

from algotrade.data import StoreReader
from algotrade.services.explore.store import ReadStore
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.sources.framework.base import FixtureSource
from algotrade_ingestion.sources.framework.registry import fixture_source
from algotrade_ingestion.tasks.maintenance.golden import load_golden
from algotrade_ingestion.tasks.reference import reference_diff
from tests.helpers.api_store import api_store
from tests.helpers.ingest_fakes import task_ctx

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "datasets" / "golden"

# HYPOTHESIS_PROFILE=nightly runs far more examples on the scheduled workflow.
settings.register_profile("dev", max_examples=30, deadline=None)
settings.register_profile("ci", max_examples=100, deadline=None, print_blob=True)
settings.register_profile(
    "nightly", max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(autouse=True)
def strict_reference_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """A universe build that would write two ``events/reference_change`` rows under one key
    fails the test instead of being deduplicated (production keeps one and counts it)."""
    monkeypatch.setattr(reference_diff, "STRICT", True)


@pytest.fixture(scope="session")
def golden_source() -> FixtureSource:
    """The committed golden CSVs, as the source registry builds them."""
    return fixture_source("synthetic", GOLDEN_DIR)


@pytest.fixture(scope="session")
def golden_reader(golden_source: FixtureSource) -> StoreReader:
    """The golden datasets loaded through the real ingestion job into an in-memory store."""
    backend = MemoryBackend()
    load_golden(task_ctx(StoreWriter(backend)), golden_source)
    return StoreReader(backend)


@pytest.fixture(scope="session")
def explore(golden_source: FixtureSource) -> tuple[ReadStore, dict[str, str]]:
    """The golden store plus one session of everything a page shows (API / explore tests)
    -> (the store, the run ids the tests look up)."""
    return api_store(golden_source)


@pytest.fixture(scope="session")
def golden_url(tmp_path_factory: pytest.TempPathFactory, golden_source: FixtureSource) -> str:
    """A local (Parquet) fixture store with the golden datasets, for CLI tests."""
    root = tmp_path_factory.mktemp("golden-store")
    load_golden(task_ctx(StoreWriter(LocalBackend(root))), golden_source)
    return f"file://{root}"


@pytest.fixture(autouse=True)
def _no_live_vendor_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never reach live vendors, even if a developer's .env holds real keys."""
    monkeypatch.setenv("ALGOTRADE_MASSIVE_API_KEY", "")
    monkeypatch.setenv("ALGOTRADE_SEC_CONTACT", "")
