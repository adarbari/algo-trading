#!/usr/bin/env python3
"""Fail when ADR or web-rule numbers collide or drift.

Two sessions that each take "the next free number" collide only at merge time. This check moves
that to the push: (1) an ADR file new on this branch (`docs/adr/NNNN-*.md` not on origin/main)
must not reuse a number origin/main already has; (2) the rule numbers in the "Rules and how they
are enforced" table of docs/ui/architecture.md are 1..n in order, and every number a lint
message cites (`message(n, ...)` or `[ADR 0025 rule n]` in apps/web/lint-rules/*.js) is in the
table. Offline (fetch fails) the ADR check is skipped with a note.
Usage: python scripts/check_numbering.py
"""

import re
import subprocess
import sys
from pathlib import Path

ADR_DIR = "docs/adr"
ADR_FILE = re.compile(r"^docs/adr/(\d{4})-[^/]+\.md$")
RULES_DOC = "docs/ui/architecture.md"
LINT_DIR = "apps/web/lint-rules"
CITED = re.compile(r"\bmessage\(\s*(\d+)\s*,|\[ADR 0025 rule (\d+)\]")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def _adr_names(root: Path, ref: str) -> set[str] | None:
    out = _git(root, "ls-tree", "-r", "--name-only", ref, "--", ADR_DIR)
    if out.returncode != 0:
        return None
    return {p for p in out.stdout.splitlines() if ADR_FILE.match(p)}


def adr_collisions(root: Path, fetch: bool = True) -> tuple[list[str], str | None]:
    """Problems with this branch's new ADR numbers, and a note when the check was skipped."""
    if fetch and _git(root, "fetch", "-q", "origin", "main").returncode != 0:
        return [], "origin/main not reachable (offline): ADR number check skipped"
    main = _adr_names(root, "origin/main")
    mine = _adr_names(root, "HEAD")
    if main is None or mine is None:
        return [], "origin/main or HEAD has no docs/adr: ADR number check skipped"
    taken: dict[str, str] = {}
    for path in main:
        taken[ADR_FILE.match(path).group(1)] = path  # type: ignore[union-attr]
    problems = []
    for path in sorted(mine - main):
        number = ADR_FILE.match(path).group(1)  # type: ignore[union-attr]
        if number in taken:
            problems.append(
                f"{path}: ADR number {number} is already taken on origin/main by {taken[number]};"
                " take the next free number (rename the file and fix the links to it)"
            )
    return problems, None


def table_rules(text: str) -> list[int]:
    """The rule numbers of the 'Rules and how they are enforced' table, in order."""
    section = text.split("## Rules and how they are enforced", 1)[-1].split("\n## ", 1)[0]
    return [int(m.group(1)) for m in re.finditer(r"^\|\s*(\d+)\s*\|", section, re.MULTILINE)]


def rule_problems(root: Path) -> list[str]:
    doc = root / RULES_DOC
    if not doc.is_file():
        return []
    numbers = table_rules(doc.read_text(encoding="utf-8"))
    problems = []
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append(
            f"{RULES_DOC}: rule numbers are {numbers}, expected 1..{len(numbers)} in order"
        )
    for js in sorted((root / LINT_DIR).glob("*.js")):
        for m in CITED.finditer(js.read_text(encoding="utf-8")):
            n = int(m.group(1) or m.group(2))
            if n not in numbers:
                problems.append(
                    f"{js.relative_to(root)}: cites rule {n}, not in the {RULES_DOC} table"
                )
    return problems


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    problems, note = adr_collisions(root)
    if note:
        print(f"note: {note}")
    problems += rule_problems(root)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
