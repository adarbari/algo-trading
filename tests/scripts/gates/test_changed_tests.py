"""`scripts/changed_tests.py`: changed files map to their mirrored tests and their areas."""

import importlib.util
import subprocess
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
    guide = "tests/architecture/guide"
    views = changed_tests.VIEWS_FITNESS
    assert covering("apps/web/src/pages/ideas/ui/IdeasPage.tsx") == [guide, web, views]
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


def test_what_the_guide_coverage_test_reads_maps_to_it() -> None:
    # the Guide coverage test (ADR 0051) reads the web code, the schema and the Guide sources
    guide = changed_tests.GUIDE_FITNESS
    assert guide in covering("apps/api/schema.graphql")
    assert guide in changed_tests.covering_tests(
        ["config/site/guide/glossary/edges/edges.toml"], {guide}.__contains__
    )


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
    found = changed_tests.covering_tests(["config/site/features/technical/bands.toml"], present)
    assert set(changed_tests.CATALOGUE_TESTS) <= set(found)


def test_a_web_source_change_maps_to_the_page_latency_views_test() -> None:
    # a new web view or operation fails CI until `make api-latency-views` lists it
    views = changed_tests.VIEWS_FITNESS
    assert views in covering("apps/web/src/pages/calendar/index.ts")
    assert views in covering("apps/api/schema.graphql")
    assert views not in covering("apps/web/design-system/index.ts")


def _fake_git(monkeypatch: pytest.MonkeyPatch, fetch_fails: bool = False) -> list[list[str]]:
    """Record the git commands run; `git remote` answers `origin`."""
    ran: list[list[str]] = []
    monkeypatch.setattr(changed_tests, "_git", lambda *a: ["origin"] if a == ("remote",) else [])

    def run(cmd: list[str], **_: object) -> None:
        ran.append(cmd)
        if fetch_fails:
            raise subprocess.CalledProcessError(128, cmd)

    monkeypatch.setattr(changed_tests.subprocess, "run", run)
    return ran


def test_a_remote_base_is_fetched_before_the_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    # a stale origin/main counted merged work as changed: V2 and V5 ran 10+ min of step 1
    ran = _fake_git(monkeypatch)
    changed_tests.refresh("origin/main")
    assert ran == [["git", "fetch", "--quiet", "origin", "main"]]


def test_a_local_base_is_not_fetched(monkeypatch: pytest.MonkeyPatch) -> None:
    ran = _fake_git(monkeypatch)
    changed_tests.refresh("3558f7f60")
    changed_tests.refresh("feature/x")  # no remote named `feature`
    assert ran == []


def test_a_failed_fetch_keeps_the_ref(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_git(monkeypatch, fetch_fails=True)
    changed_tests.refresh("origin/main")
    assert "could not fetch origin/main" in capsys.readouterr().err


def test_main_fetches_then_diffs_from_the_merge_base(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(changed_tests, "refresh", lambda base: calls.append(f"fetch {base}"))
    monkeypatch.setattr(
        changed_tests, "changed_files", lambda base: calls.append(f"diff {base}") or []
    )
    changed_tests.main(["changed_tests.py"])
    changed_tests.main(["changed_tests.py", "--no-fetch", "origin/main"])
    assert calls == ["fetch origin/main", "diff origin/main", "diff origin/main"]


def test_changed_files_diff_from_the_merge_base(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, ...]] = []

    def git(*args: str) -> list[str]:
        seen.append(args)
        return ["abc123"] if args[0] == "merge-base" else []

    monkeypatch.setattr(changed_tests, "_git", git)
    changed_tests.changed_files("origin/main")
    assert seen[:2] == [("merge-base", "origin/main", "HEAD"), ("diff", "--name-only", "abc123")]


def test_a_guide_entry_maps_to_the_guide_readers_not_the_whole_graph() -> None:
    # a glossary entry ran tests/apps/api/graphql and tests/unit/services/read whole (V2, V5)
    readers = set(changed_tests.SITE_CONFIG_READERS["config/site/guide/"])
    got = changed_tests.covering_tests(
        ["config/site/guide/glossary/results.toml"],
        (readers | {"tests/apps/api/graphql"}).__contains__,
    )
    assert set(got) == readers


def test_step_one_leaves_out_what_step_two_runs_in_full() -> None:
    paths = [
        "tests/architecture",
        "tests/architecture/guide",
        "tests/unit/config/site/guide",
        "tests/unit/configs/test_x.py",
        "tests/unit/services/read/guide",
    ]
    assert changed_tests.without_full_runs(paths) == [
        "tests/unit/configs/test_x.py",
        "tests/unit/services/read/guide",
    ]


def test_main_prints_no_full_run_paths(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(changed_tests, "refresh", lambda base: None)
    monkeypatch.setattr(changed_tests, "changed_files", lambda base: ["architecture/layout.toml"])
    changed_tests.main(["changed_tests.py"])
    assert capsys.readouterr().out.strip() == ""
