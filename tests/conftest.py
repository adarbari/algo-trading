import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

from algotrade.data.store import DatasetStore

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
def golden_store() -> DatasetStore:
    return DatasetStore(GOLDEN_DIR)
