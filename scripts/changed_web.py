"""Plan and run the web checks for the `apps/web` files changed on this branch (`make changed`).

A changed slice or design-system folder maps to its vitest folder; a changed page or route to
the e2e spec named after it (unknown: `smoke`); a changed story or CSS module to that
component's screenshots (Docker only, so printed, not run, off Linux); any changed `.ts` /
`.tsx` adds `npm run typecheck` (`tsc -b`, the only type gate). This narrows the first check;
`make check` still gates every change.
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


def spec_for(name: str) -> str:
    """The e2e spec named after a page folder or route file stem (`smoke` when unknown)."""
    stem = PurePosixPath(name).stem.removesuffix(".test").removesuffix("-route")
    stem = SPEC_ALIASES.get(stem, stem)
    return stem if stem in SPECS else "smoke"


def plan(files: list[str], on_linux: bool = sys.platform == "linux") -> list[Step]:
    """The web checks covering `files` (repo-relative paths), in run order."""
    vitest: set[str] = set()
    specs: set[str] = set()
    visual: set[str] = set()
    typed = False
    for name in files:
        if not name.startswith(WEB):
            continue
        rel = PurePosixPath(name.removeprefix(WEB))
        parts = rel.parts
        typed = typed or rel.suffix in (".ts", ".tsx")
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
    return _steps(typed, vitest, specs, visual, on_linux)


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
    steps = plan(changed_tests.changed_files(base))
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
