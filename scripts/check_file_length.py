#!/usr/bin/env python3
"""Fail if any source file exceeds the line limit.

Long files are a smell that one module has more than one responsibility. Split it.
Usage: python scripts/check_file_length.py [--max 1000] [paths...]
"""

import argparse
import subprocess
import sys
from pathlib import Path

MAX_LINES = 1000
CHECKED_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".cfg", ".sh"}


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return [Path(p) for p in out.splitlines()]


def oversized(paths: list[Path], limit: int) -> list[tuple[Path, int]]:
    offenders = []
    for path in paths:
        if path.suffix not in CHECKED_SUFFIXES or not path.is_file():
            continue
        count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        if count > limit:
            offenders.append((path, count))
    return offenders


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=MAX_LINES)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    offenders = oversized(args.paths or tracked_files(), args.max)
    for path, count in offenders:
        print(f"{path}: {count} lines (max {args.max}) - split it by responsibility")
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
