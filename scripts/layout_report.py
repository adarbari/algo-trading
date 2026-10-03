#!/usr/bin/env python3
"""Early warning for the directory layout (ADR 0020, ``architecture/layout.toml``).

Lists directories under src/, libs/, apps/ and tests/ (Python) and apps/web (TypeScript, ADR
0025) that hold ``warn_modules`` or more modules, so a split by kind is planned before the
``max_modules`` limit forces it. Never fails: the limit itself is enforced by
tests/architecture/test_layout*.py.
Usage: python scripts/layout_report.py
"""

import fnmatch
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = tomllib.loads((ROOT / "architecture" / "layout.toml").read_text())
NOT_COUNTED = {"__init__.py", "conftest.py"}
SKIPPED = {".venv", "node_modules", "__pycache__"}
WEB_SUFFIXES = {".ts", ".tsx", ".js"}
WEB_NOT_MODULES = ("index.ts", "*.test.*", "*.spec.*", "*.stories.*", "*.d.ts")


def module_counts() -> Counter[str]:
    counts: Counter[str] = Counter()
    for top in ("src", "libs", "apps", "tests"):
        for path in (ROOT / top).rglob("*.py"):
            if path.name not in NOT_COUNTED and not SKIPPED & set(path.parts):
                counts[path.parent.relative_to(ROOT).as_posix()] += 1
    web = LAYOUT["web"]
    for path in (ROOT / web["root"]).rglob("*"):
        rel = path.relative_to(ROOT)
        if set(web["skipped"]) & set(rel.parts) or path.suffix not in WEB_SUFFIXES:
            continue
        if not any(fnmatch.fnmatchcase(path.name, p) for p in WEB_NOT_MODULES):
            counts[rel.parent.as_posix()] += 1
    return counts


def main() -> int:
    warn, limit = LAYOUT["warn_modules"], LAYOUT["max_modules"]
    near = sorted((d, n) for d, n in module_counts().items() if n >= warn)
    if not near:
        print(f"layout: no directory at {warn}+ modules (limit {limit})")
        return 0
    print(f"layout: approaching the {limit}-module limit: plan the split by kind")
    for directory, n in near:
        print(f"  {n:>2}/{limit}  {directory}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
