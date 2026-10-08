"""What changed on this branch: the test paths that cover it (`make changed`) or the areas
it touches (`--areas`, for `make check`).

Tests mirror their source (CLAUDE.md "Directory layout"), so a changed module maps to its
mirrored test file, or to the mirrored folder when the file has no test of its own. Changed
test files map to themselves; a changed architecture registry maps to the fitness tests.
This narrows the first check. `--areas` prints the areas the change touches, `python`, `web`
and / or `docs`, by the same rule as CI's "Changed areas" job (.github/workflows/ci.yml), so
`make check` runs the gates for those areas; a branch with no change (main) is every area.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Source prefix -> mirrored test prefix (CLAUDE.md "Tests mirror their source").
MIRRORS = (
    ("src/algotrade/", "tests/unit/"),
    ("libs/sources/algotrade_sources/", "tests/libs/sources/"),
    ("apps/ingestion/algotrade_ingestion/", "tests/apps/ingestion/"),
    ("apps/backtest/algotrade_backtest/", "tests/apps/backtest/"),
    ("apps/api/algotrade_api/", "tests/apps/api/"),
)


def _git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def changed_files(base: str) -> list[str]:
    """Files changed since the merge base with `base`, plus uncommitted and untracked ones."""
    merge_base = _git("merge-base", base, "HEAD")[0]
    committed = _git("diff", "--name-only", merge_base)
    untracked = _git("ls-files", "--others", "--exclude-standard")
    return sorted(set(committed) | set(untracked))


def _on_disk(path: str) -> bool:
    return (REPO / path).exists()


def covering_tests(files: list[str], present: Callable[[str], bool] = _on_disk) -> list[str]:
    """The test files or folders covering `files` (only paths that exist)."""
    paths: set[str] = set()
    for name in files:
        if name.startswith("architecture/"):
            paths.add("tests/architecture")
        if not name.endswith(".py"):
            continue
        if name.startswith("tests/"):
            if Path(name).name.startswith("test_") and present(name):
                paths.add(name)
            continue
        for source, tests in MIRRORS:
            if name.startswith(source):
                rel = Path(tests + name.removeprefix(source))
                own = rel.parent / f"test_{rel.name}"
                if rel.name != "__init__.py" and present(str(own)):
                    paths.add(str(own))
                elif present(str(rel.parent)):
                    paths.add(str(rel.parent))
                break
    return sorted(paths)


BOTH_AREAS = (".github/workflows/ci.yml", "apps/api/openapi.json", "apps/api/schema.graphql")
DOCS_PREFIXES = ("docs/", ".claude/")


def changed_areas(files: list[str]) -> list[str]:
    """The areas `files` touch: `python`, `web`, `docs` (CI's rule); nothing changed = all code."""
    areas: set[str] = set()
    for name in files:
        if name in BOTH_AREAS:
            areas |= {"python", "web"}
        elif name.startswith("apps/web/"):
            areas.add("web")
        elif name.startswith(DOCS_PREFIXES) or name.endswith(".md") or name == "LICENSE":
            areas.add("docs")
        else:
            areas.add("python")
    return sorted(areas) if files else ["python", "web"]


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    base = args[0] if args else "origin/main"
    if "--areas" in argv:
        try:
            files = changed_files(base)
        except subprocess.CalledProcessError:  # no such base ref (a shallow CI checkout)
            print(f"changed_tests: no {base} to diff against; every area", file=sys.stderr)
            files = []
        print(" ".join(changed_areas(files)))
    else:
        print("\n".join(covering_tests(changed_files(base))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
