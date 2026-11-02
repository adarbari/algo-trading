"""`scripts/changed_web.py`: changed web files map to vitest folders, e2e specs, screenshots."""

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
        "npx eslint --max-warnings=0 src/entities/feature/columns.tsx",
        "npm run typecheck",
        "npx vitest run src/entities/feature",
        "env VITE_SUPABASE_URL=http://127.0.0.1:54321 VITE_SUPABASE_ANON_KEY=e2e-anon-key"
        " npx vite build",
        "npm run perf:bundle",
    ]


def test_a_page_maps_to_the_spec_named_after_it() -> None:
    got = cmds("apps/web/src/pages/trader-ideas/IdeasPage.tsx")
    assert "npx playwright test e2e/ideas.spec.ts" in got
    assert "npx vitest run src/pages/trader-ideas" in got


def test_a_route_maps_to_its_spec_and_an_unknown_one_to_smoke() -> None:
    assert "npx playwright test e2e/regime.spec.ts" in cmds(
        "apps/web/src/app/routes/trader/regime-route.tsx"
    )
    assert "npx playwright test e2e/smoke.spec.ts" in cmds(
        "apps/web/src/pages/placeholder/Page.tsx"
    )
    assert "npx playwright test e2e/smoke.spec.ts" in cmds("apps/web/src/app/routes/root.ts")


def test_a_story_or_css_module_maps_to_the_component_screenshots() -> None:
    got = cmds("apps/web/design-system/components/Banner/Banner.module.css")
    assert "npm run visual -- --grep Banner" in got
    assert "npx vitest run design-system/components/Banner" in got
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


def test_a_deleted_folder_has_no_tests_to_run(tmp_path: Path) -> None:
    (tmp_path / "src/widgets/kept").mkdir(parents=True)
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
    assert "npx vitest run src/widgets/kept" in got
    assert "npx vitest run src/widgets/gone" not in got


def test_app_and_design_system_code_adds_the_bundle_budgets_but_a_config_file_does_not() -> None:
    assert "npm run perf:bundle" in cmds("apps/web/design-system/components/Banner/Banner.tsx")
    assert "npm run perf:bundle" not in cmds("apps/web/package.json")
    assert not any(c.startswith("npx eslint") for c in cmds("apps/web/package.json"))
