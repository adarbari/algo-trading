"""`scripts/changed_tests.py`: changed files map to their mirrored tests."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "changed_tests.py"
_spec = importlib.util.spec_from_file_location("changed_tests", SCRIPT)
assert _spec and _spec.loader
changed_tests = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changed_tests)

EXISTING = {
    "tests/unit/data/test_prices.py",
    "tests/unit/data",
    "tests/apps/ingestion/tasks/market",
    "tests/libs/sources/vendors/ibkr/test_gateway.py",
    "tests/apps/api/test_main.py",
}


def covering(*files: str) -> list[str]:
    paths: list[str] = changed_tests.covering_tests(list(files), EXISTING.__contains__)
    return paths


def test_a_module_maps_to_its_own_mirrored_test() -> None:
    assert covering("src/algotrade/data/prices.py") == ["tests/unit/data/test_prices.py"]
    assert covering("libs/sources/algotrade_sources/vendors/ibkr/gateway.py") == [
        "tests/libs/sources/vendors/ibkr/test_gateway.py"
    ]


def test_a_module_without_its_own_test_maps_to_the_mirrored_folder() -> None:
    assert covering("src/algotrade/data/volatility.py") == ["tests/unit/data"]
    assert covering("apps/ingestion/algotrade_ingestion/tasks/market/ibkr_iv.py") == [
        "tests/apps/ingestion/tasks/market"
    ]


def test_changed_tests_and_registries_map_to_themselves_and_fitness_tests() -> None:
    assert covering("tests/apps/api/test_main.py", "architecture/layout.toml") == [
        "tests/apps/api/test_main.py",
        "tests/architecture",
    ]


def test_files_with_nothing_to_cover_them_are_skipped() -> None:
    assert covering("README.md", "src/algotrade/nowhere/x.py", "tests/conftest.py") == []
