"""Plan and run the web checks for the `apps/web` files changed on this branch (`make changed`).

First the static gates CI fails on most: Prettier and Stylelint over the changed files, the
design-system check, and ESLint over the changed scripts (about 45 s: it loads the project).
Any changed `.ts` / `.tsx` adds `npm run typecheck` (`tsc -b`, the only type gate; incremental,
its build info kept in `node_modules/.tmp`); the changed code files that still exist go to one
`vitest related` run (the tests that import them, one start-up instead of one per folder); a
changed story or CSS module adds that component's screenshots (Docker only, so printed, not run,
off Linux); a changed file under `src/` or `design-system/` adds the production build and the
bundle budgets, the web CI failure seen most. The Playwright e2e specs are CI's alone (owner
decision 2026-11-02: minutes each on the shared Mac, rarely the first red check).
This narrows the first check; CI still gates every change.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import changed_tests

WEB = "apps/web/"
# What vitest collects tests from (vite.config.ts `test.include`) and can import.
TESTED_ROOTS = ("src", "design-system", "scripts", "vite-plugins", "build", "lint-rules")
# A changed stylesheet reaches the tests of the components that import it.
TESTED = (".ts", ".tsx", ".js", ".css")
# A changed story or CSS module changes that component's screenshots.
STYLED = (".stories.tsx", ".module.css")
# Generated: every test imports it, so `related` would run the whole suite (CI does that).
UNRELATED = ("src/shared/api/generated/",)
Step = tuple[str, list[str]]  # (what it covers, argv run from apps/web)
LINTED = (".ts", ".tsx", ".js", ".mjs")
# The build the CI web-perf job runs (its Supabase placeholders), then the bundle budgets.
BUNDLE_STEPS: list[Step] = [
    (
        "bundle build",
        [
            "env",
            "VITE_SUPABASE_URL=http://127.0.0.1:54321",
            "VITE_SUPABASE_ANON_KEY=e2e-anon-key",
            "npx",
            "vite",
            "build",
        ],
    ),
    ("bundle budgets", ["npm", "run", "perf:bundle"]),
]


def plan(
    files: list[str], on_linux: bool = sys.platform == "linux", root: Path | None = None
) -> list[Step]:
    """The web checks covering `files` (repo-relative paths), in run order.

    With `root` (the `apps/web` folder), a folder that no longer exists (a deleted widget) has
    no tests to run and is left out.
    """
    related: list[str] = []
    visual: set[str] = set()
    typed = False
    bundled = False
    present: list[str] = []
    for name in files:
        if not name.startswith(WEB):
            continue
        rel = PurePosixPath(name.removeprefix(WEB))
        parts = rel.parts
        exists = root is None or (root / rel).is_file()
        if exists:
            present.append(str(rel))
        typed = typed or rel.suffix in (".ts", ".tsx")
        bundled = bundled or parts[0] in ("src", "design-system")
        if (
            exists
            and parts[0] in TESTED_ROOTS
            and rel.suffix in TESTED
            and not str(rel).startswith(UNRELATED)
        ):
            related.append(str(rel))
        if parts[0] == "design-system" and len(parts) > 3 and rel.name.endswith(STYLED):
            visual.add(parts[2])
    steps = _static_steps(present) + _steps(typed, sorted(related), visual, on_linux)
    return steps + (BUNDLE_STEPS if bundled else [])


def _static_steps(present: list[str]) -> list[Step]:
    """The seconds-long gates CI's web-static job runs, over the changed files that still exist:
    Prettier and Stylelint on those files only, then the design-system check (about 1 s whole).
    ESLint runs over the changed scripts only (about 45 s cold for two files, against 66-215 s
    for the whole project): "no raw HTML outside the design system" (ADR 0025 rule 3) was a top
    CI failure that only ESLint sees."""
    if not present:
        return []
    steps: list[Step] = [
        ("format", ["npx", "prettier", "--check", "--ignore-unknown", *sorted(present)])
    ]
    css = sorted(f for f in present if f.startswith("design-system/") and f.endswith(".css"))
    if css:
        steps.append(("stylelint", ["npx", "stylelint", *css]))
    steps.append(("design system", ["npm", "run", "ds:check"]))
    linted = sorted(f for f in present if f.endswith(LINTED))
    if linted:
        steps.append(
            ("eslint", ["npx", "eslint", "--max-warnings=0", "--no-warn-ignored", *linted])
        )
    return steps


def _steps(typed: bool, related: list[str], visual: set[str], on_linux: bool) -> list[Step]:
    """Order the gathered checks: types, unit, screenshots (no e2e: CI runs the specs)."""
    steps: list[Step] = []
    if typed:
        steps.append(("types", ["npm", "run", "typecheck"]))
    if related:
        steps.append(("unit (related)", ["npx", "vitest", "related", "--run", *related]))
    for component in sorted(visual):
        argv = ["npm", "run", "visual", "--", "--grep", component]
        if not on_linux:
            argv = ["npm", "run", "visual:docker", "--", "--grep", component]
            steps.append((f"screenshots {component} (Docker, run by hand)", argv))
        else:
            steps.append((f"screenshots {component}", argv))
    return steps


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else "origin/main"
    steps = plan(changed_tests.changed_files(base), root=changed_tests.REPO / "apps" / "web")
    if not steps:
        print("no web checks for the changed files")
        return 0
    for what, cmd in steps:
        print(f"web: {what}: {' '.join(cmd)}")
    for what, cmd in steps:
        if "by hand" in what:
            continue
        if subprocess.run(cmd, cwd=changed_tests.REPO / "apps" / "web", check=False).returncode:
            print(f"web check failed: {what}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
