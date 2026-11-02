"""Plan and run the web checks for the `apps/web` files changed on this branch (`make changed`).

First the static gates CI fails on most: Prettier and Stylelint over the changed files, the
design-system check, and ESLint over the changed scripts (about 45 s: it loads the project).
A changed slice or design-system folder maps to its vitest folder; a changed page or route to
the e2e spec named after it (unknown: `smoke`); a changed
story or CSS module to that component's screenshots (Docker only, so printed, not run, off
Linux); any changed `.ts` / `.tsx` adds `npm run typecheck` (`tsc -b`, the only type gate); a
changed file under `src/` or `design-system/` adds the production build and the bundle budgets.
This narrows the first check; `make check` still gates every change.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import changed_tests

WEB = "apps/web/"
SPECS = (
    "admin-ingestion",
    "calendar",
    "explore",
    "guide-help",
    "guide",
    "ideas",
    "login",
    "regime",
    "screener-builder",
    "screener-results",
    "smoke",
)
# Page folder (or route file stem) -> e2e spec, where the names differ.
SPEC_ALIASES = {
    "trader-calendar": "calendar",
    "trader-explore": "explore",
    "trader-ideas": "ideas",
    "trader-regime": "regime",
    "trader-screeners": "screener-results",
    "screeners": "screener-results",
    "ingestion": "admin-ingestion",
}
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


def spec_for(name: str) -> str:
    """The e2e spec named after a page folder or route file stem (`smoke` when unknown)."""
    stem = PurePosixPath(name).stem.removesuffix(".test").removesuffix("-route")
    stem = SPEC_ALIASES.get(stem, stem)
    return stem if stem in SPECS else "smoke"


def plan(
    files: list[str], on_linux: bool = sys.platform == "linux", root: Path | None = None
) -> list[Step]:
    """The web checks covering `files` (repo-relative paths), in run order.

    With `root` (the `apps/web` folder), a folder that no longer exists (a deleted widget) has
    no tests to run and is left out.
    """
    vitest: set[str] = set()
    specs: set[str] = set()
    visual: set[str] = set()
    typed = False
    bundled = False
    present: list[str] = []
    for name in files:
        if not name.startswith(WEB):
            continue
        rel = PurePosixPath(name.removeprefix(WEB))
        parts = rel.parts
        if root is None or (root / rel).is_file():
            present.append(str(rel))
        typed = typed or rel.suffix in (".ts", ".tsx")
        bundled = bundled or parts[0] in ("src", "design-system")
        if parts[0] == "src" and len(parts) > 3:
            vitest.add("/".join(parts[:3]))
            if parts[1] == "pages":
                specs.add(spec_for(parts[2]))
            elif parts[1:3] == ("app", "routes"):
                specs.add(spec_for(parts[-1]))
        elif parts[0] == "design-system" and len(parts) > 3:
            vitest.add("/".join(parts[:3]))
            if rel.name.endswith((".stories.tsx", ".module.css")):
                visual.add(parts[2])
    if root is not None:
        vitest = {folder for folder in vitest if (root / folder).is_dir()}
    steps = _static_steps(present) + _steps(typed, vitest, specs, visual, on_linux)
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


def _steps(
    typed: bool, vitest: set[str], specs: set[str], visual: set[str], on_linux: bool
) -> list[Step]:
    """Order the gathered checks: types, unit, e2e, screenshots."""
    steps: list[Step] = []
    if typed:
        steps.append(("types", ["npm", "run", "typecheck"]))
    for folder in sorted(vitest):
        steps.append((f"unit {folder}", ["npx", "vitest", "run", folder]))
    for spec in sorted(specs):
        steps.append((f"e2e {spec}", ["npx", "playwright", "test", f"e2e/{spec}.spec.ts"]))
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
