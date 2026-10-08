"""`scripts/changed_tests.py`: changed files map to their mirrored tests and their areas."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "changed_tests.py"
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


def test_any_web_change_maps_to_the_web_fitness_tests() -> None:
    # #319: a .tsx string and an 11-module apps/web/e2e passed `make changed`, failed CI.
    web = "tests/architecture/test_layout_web.py"
    assert covering("apps/web/src/pages/ideas/ui/IdeasPage.tsx") == [web]
    assert covering("apps/web/e2e/screeners.spec.ts") == [web]
    assert covering("architecture/web_prose.toml") == ["tests/architecture"]


def test_changed_tests_and_registries_map_to_themselves_and_fitness_tests() -> None:
    assert covering("tests/apps/api/test_main.py", "architecture/layout.toml") == [
        "tests/apps/api/test_main.py",
        "tests/architecture",
    ]


def test_files_with_nothing_to_cover_them_are_skipped() -> None:
    assert covering("README.md", "src/algotrade/nowhere/x.py", "tests/conftest.py") == []


def test_changed_areas_follow_the_ci_rule() -> None:
    areas = changed_tests.changed_areas
    assert areas(["src/algotrade/data/prices.py", "Makefile"]) == ["python"]
    assert areas(["apps/web/src/pages/ideas.tsx"]) == ["web"]
    assert areas(["docs/ci.md", ".claude/skills/x/SKILL.md", "README.md", "LICENSE"]) == ["docs"]
    assert areas(["apps/api/openapi.json"]) == ["python", "web"]
    assert areas(["docs/ci.md", "apps/web/e2e/x.ts", "uv.lock"]) == ["docs", "python", "web"]


def test_nothing_changed_means_every_code_area() -> None:
    assert changed_tests.changed_areas([]) == ["python", "web"]


def test_areas_without_the_base_ref_are_every_code_area(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # CI checks out one commit: no origin/main to diff against, so the gate runs everything.
    assert changed_tests.main(["changed_tests.py", "--areas", "no/such/ref"]) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "python web" and "every area" in out.err


def test_a_site_config_change_maps_to_the_tests_that_read_the_site_config() -> None:
    present = set(changed_tests.SITE_CONFIG_TESTS).__contains__
    found = changed_tests.covering_tests(
        ["config/site/presets/screeners/momentum_12_1/v1.toml"], present
    )
    assert found == sorted(changed_tests.SITE_CONFIG_TESTS)
    assert changed_tests.covering_tests(["config/users/u1/x.toml"], present) == []


def test_a_feature_change_runs_the_web_catalogue_export_test() -> None:
    present = {*changed_tests.CATALOGUE_TESTS, "tests/unit/features"}.__contains__
    found = changed_tests.covering_tests(["src/algotrade/features/registry.py"], present)
    assert set(changed_tests.CATALOGUE_TESTS) <= set(found)
    found = changed_tests.covering_tests(["config/site/features/bands.toml"], present)
    assert set(changed_tests.CATALOGUE_TESTS) <= set(found)
