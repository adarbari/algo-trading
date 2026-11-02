"""`scripts/changed_web.py`: changed web files map to the static gates, related tests, budgets."""

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("changed_web", SCRIPTS / "changed_web.py")
assert _spec and _spec.loader
changed_web = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changed_web)


def cmds(*files: str, linux: bool = True) -> list[str]:
    return [" ".join(c) for _, c in changed_web.plan(list(files), linux)]


def test_a_slice_file_maps_to_its_folder_and_the_type_gate() -> None:
    assert cmds("apps/web/src/entities/feature/columns.tsx") == [
        "npx prettier --check --ignore-unknown src/entities/feature/columns.tsx",
        "npm run ds:check",
        "npx eslint --max-warnings=0 --no-warn-ignored src/entities/feature/columns.tsx",
        "npm run typecheck",
        "npx vitest related --run src/entities/feature/columns.tsx",
        "env VITE_SUPABASE_URL=http://127.0.0.1:54321 VITE_SUPABASE_ANON_KEY=e2e-anon-key"
        " npx vite build",
        "npm run perf:bundle",
    ]


def test_the_changed_code_files_go_to_one_related_vitest_run() -> None:
    got = cmds(
        "apps/web/src/pages/trader-ideas/IdeasPage.tsx",
        "apps/web/src/widgets/watchlist-editor/ui/Editor.tsx",
        "apps/web/scripts/check-bundle-budgets.ts",
    )
    unit = [c for c in got if "vitest" in c]
    assert unit == [
        "npx vitest related --run scripts/check-bundle-budgets.ts"
        " src/pages/trader-ideas/IdeasPage.tsx src/widgets/watchlist-editor/ui/Editor.tsx"
    ]


def test_the_generated_client_is_not_a_related_root() -> None:
    # every test imports the client: `related` on it would be the whole suite, which CI runs
    got = cmds("apps/web/src/shared/api/generated/graphql/gql.ts")
    assert not any("vitest" in c for c in got)
    assert "npm run typecheck" in got


def test_no_e2e_spec_runs_locally_but_the_bundle_budgets_do() -> None:
    # owner decision 2026-11-02: CI runs the Playwright specs; the bundle stays local
    got = cmds(
        "apps/web/src/pages/trader-ideas/IdeasPage.tsx",
        "apps/web/src/app/routes/trader/regime-route.tsx",
        "apps/web/e2e/ideas.spec.ts",
    )
    assert not any("playwright" in c for c in got)
    assert got[-2:] == [
        "env VITE_SUPABASE_URL=http://127.0.0.1:54321 VITE_SUPABASE_ANON_KEY=e2e-anon-key"
        " npx vite build",
        "npm run perf:bundle",
    ]


def test_a_story_or_css_module_maps_to_the_component_screenshots() -> None:
    got = cmds("apps/web/design-system/components/Banner/Banner.module.css")
    assert "npm run visual -- --grep Banner" in got
    assert "npx vitest related --run design-system/components/Banner/Banner.module.css" in got
    off = cmds("apps/web/design-system/components/Banner/Banner.stories.tsx", linux=False)
    assert "npm run visual:docker -- --grep Banner" in off


def test_files_outside_the_web_app_map_to_nothing() -> None:
    assert cmds("src/algotrade/x.py", "docs/ci.md") == []


def test_other_web_files_get_only_the_static_gates() -> None:
    assert cmds("apps/web/package.json") == [
        "npx prettier --check --ignore-unknown package.json",
        "npm run ds:check",
    ]


def test_a_design_system_stylesheet_is_stylelinted_alone() -> None:
    got = cmds(
        "apps/web/design-system/components/Banner/Banner.module.css",
        "apps/web/src/pages/guide/GuidePage.tsx",
    )
    assert "npx stylelint design-system/components/Banner/Banner.module.css" in got
    assert got.index("npm run ds:check") < got.index("npm run typecheck")


def test_a_deleted_file_is_not_format_checked(tmp_path: Path) -> None:
    (tmp_path / "src/widgets/kept/ui").mkdir(parents=True)
    (tmp_path / "src/widgets/kept/ui/Kept.tsx").write_text("")
    steps = changed_web.plan(
        ["apps/web/src/widgets/gone/ui/Gone.tsx", "apps/web/src/widgets/kept/ui/Kept.tsx"],
        True,
        tmp_path,
    )
    fmt = " ".join(next(c for what, c in steps if what == "format"))
    assert "Kept.tsx" in fmt and "Gone.tsx" not in fmt


def test_a_deleted_file_has_no_related_tests(tmp_path: Path) -> None:
    (tmp_path / "src/widgets/kept/ui").mkdir(parents=True)
    (tmp_path / "src/widgets/kept/ui/Kept.tsx").write_text("")
    got = [
        " ".join(c)
        for _, c in changed_web.plan(
            [
                "apps/web/src/widgets/gone/ui/Gone.tsx",
                "apps/web/src/widgets/kept/ui/Kept.tsx",
            ],
            True,
            tmp_path,
        )
    ]
    assert "npx vitest related --run src/widgets/kept/ui/Kept.tsx" in got


def test_type_checking_stays_incremental_between_runs() -> None:
    # `tsc -b` reuses its build info only if it survives the run: node_modules/.tmp does
    web = SCRIPTS.parent / "apps" / "web"
    for name in ("tsconfig.app.json", "tsconfig.node.json"):
        text = (web / name).read_text()
        assert '"tsBuildInfoFile": "./node_modules/.tmp/' in text, name


def test_app_and_design_system_code_adds_the_bundle_budgets_but_a_config_file_does_not() -> None:
    assert "npm run perf:bundle" in cmds("apps/web/design-system/components/Banner/Banner.tsx")
    assert "npm run perf:bundle" not in cmds("apps/web/package.json")
    assert not any(c.startswith("npx eslint") for c in cmds("apps/web/package.json"))


def test_eslint_does_not_fail_on_a_changed_file_the_config_ignores() -> None:
    # the generated GraphQL client is in eslint.config.js `ignores`: handed to eslint as an
    # argument it warns "File ignored", and --max-warnings=0 turned that into a failed push
    got = cmds("apps/web/src/shared/api/generated/graphql/gql.ts")
    assert any(c.startswith("npx eslint") and "--no-warn-ignored" in c for c in got)
