"""`scripts/changed_web.py`: changed web files map to vitest folders, e2e specs, screenshots."""

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("changed_web", SCRIPTS / "changed_web.py")
assert _spec and _spec.loader
changed_web = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changed_web)


def cmds(*files: str, linux: bool = True) -> list[str]:
    return [" ".join(c) for _, c in changed_web.plan(list(files), linux)]


def test_a_slice_file_maps_to_its_folder_and_the_type_gate() -> None:
    assert cmds("apps/web/src/entities/feature/columns.tsx") == [
        "npm run typecheck",
        "npx vitest run src/entities/feature",
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


def test_other_files_map_to_nothing() -> None:
    assert cmds("src/algotrade/x.py", "apps/web/package.json", "apps/web/COMPONENTS.md") == []
