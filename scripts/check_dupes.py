#!/usr/bin/env python3
"""Duplicate-code ratchet (ADR 0019): copy-pasted blocks in src/, libs/, apps/ may only go down.

Runs pylint's ``duplicate-code`` check (R0801) alone over the tracked Python files in ``src/``,
``libs/`` and ``apps/`` (tests and the GraphQL mirror types excluded: ``MIRRORS``; imports,
docstrings, comments and signatures ignored) and compares the number of duplicate blocks with
``architecture/dupes_baseline.txt``:

- more blocks than the baseline fails: reuse the owner (architecture/*_ownership.toml) instead;
- fewer blocks fails too until the baseline is lowered (``make dupes-update``), so a removed
  duplicate can never silently come back.

Usage: python scripts/check_dupes.py [--update]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

BASELINE = Path("architecture/dupes_baseline.txt")
# 6 lines: pylint compares normalised lines, so ruff-formatted copies of the same logic rarely
# match over longer windows; 6 catches real copy-paste (e.g. run-record tails) without noise.
MIN_LINES = 6
PYLINT_ARGS = (
    "--disable=all",
    "--enable=duplicate-code",
    f"--min-similarity-lines={MIN_LINES}",
    "--ignore-imports=y",
    "--ignore-docstrings=y",
    "--ignore-comments=y",
    "--ignore-signatures=y",
    "--score=n",
)
BLOCK = re.compile(r"R0801: Similar lines in \d+ files")
# The GraphQL object types repeat their read dataclass's fields on purpose (ADR 0037
# "Consequences": the duplication is contained by one .of() per type, the SDL snapshot and
# READ 7, tests/architecture/api/test_read_model.py::test_types_mirror_read_model, which fails
# when a type drifts from its dataclass). Copy-paste of logic there is caught by READ 3.
MIRRORS = "apps/api/algotrade_api/graphql/types/"


def tracked_sources() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "src/*.py", "libs/*.py", "apps/*.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [f for f in out.split() if not f.startswith(MIRRORS)]


def count_blocks(pylint_output: str) -> int:
    return len(BLOCK.findall(pylint_output))


def run_pylint(files: list[str]) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "pylint", *PYLINT_ARGS, *files],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode & 1 or proc.returncode & 32:  # fatal error / usage error
        raise SystemExit(f"pylint failed:\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def verdict(found: int, baseline: int) -> tuple[int, str]:
    if found > baseline:
        return 1, (
            f"duplicate-code: {found} duplicate blocks, baseline {baseline}. Extract the shared "
            "logic into its owner (architecture/*_ownership.toml) instead of copying it."
        )
    if found < baseline:
        return 1, (
            f"duplicate-code: {found} duplicate blocks, baseline {baseline}. Nice: lower "
            f"{BASELINE} to {found} (`make dupes-update`) so it cannot come back."
        )
    return 0, f"duplicate-code: OK ({found} known duplicate blocks)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="lower the baseline to today")
    args = parser.parse_args(argv)
    output = run_pylint(tracked_sources())
    found, baseline = count_blocks(output), int(BASELINE.read_text().split()[0])
    code, message = verdict(found, baseline)
    if found > baseline or (code and not args.update):
        print(output.strip())
        print(message)
        return code
    if args.update and found < baseline:
        BASELINE.write_text(f"{found}\n")
        print(f"{BASELINE} lowered to {found}")
        return 0
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
