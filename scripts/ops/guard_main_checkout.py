#!/usr/bin/env python3
"""Claude Code PreToolUse hook (Bash): keep the main checkout on ``main``.

The launchd API, the nightly and ``scripts/ops/deploy.sh`` run from the main checkout, and
deploy refuses while it is off ``main`` (2026-10-10: a branch left there blocked auto-deploy for
8 h). Reads the hook JSON on stdin; exits 2 with a message when a command would create or switch
to a branch other than ``main`` in the main checkout (the repo whose git dir is its common git
dir). Linked worktrees, ``git checkout main`` and file checkouts (``--``) pass.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

MESSAGE = (
    "BLOCKED: this would create or switch a branch in the main checkout ({dir}). The main "
    "checkout stays on `main` (the API, nightly and auto-deploy run from it; deploy.sh refuses "
    "while it is off main). Make a worktree instead: scripts/worktree.sh <branch>, then "
    "`source worktree.env` (CLAUDE.md, Worktrees)."
)
_DIRS = ("--git-dir", "--git-common-dir")
_SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")"}


def is_main_checkout(directory: Path) -> bool:
    """True when ``directory`` is inside a repo that is not a linked worktree."""
    if not directory.is_dir():
        return False
    try:
        out = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--path-format=absolute", *_DIRS],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    lines = out.stdout.split()
    return out.returncode == 0 and len(lines) == 2 and lines[0] == lines[1]


def _segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segments: list[list[str]] = [[]]
    for token in lexer:
        if token in _SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


def _git_args(tokens: list[str]) -> tuple[Path | None, list[str]] | None:
    """(the ``-C`` directory, the arguments after ``git``) or None when not a git command."""
    i = 0
    while i < len(tokens) and (tokens[i] == "env" or "=" in tokens[i].split("/")[0]):
        i += 1
    if i >= len(tokens) or Path(tokens[i]).name != "git":
        return None
    i += 1
    cdir: Path | None = None
    while i < len(tokens) and tokens[i].startswith("-"):
        if tokens[i] == "-C" and i + 1 < len(tokens):
            cdir = (cdir or Path()) / tokens[i + 1]
            i += 2
        elif tokens[i] in {"-c", "--git-dir", "--work-tree", "--namespace"}:
            i += 2
        else:
            i += 1
    return cdir, tokens[i:]


def _switches_branch(args: list[str], directory: Path) -> bool:
    """Would this ``git checkout|switch`` create a branch or move HEAD off ``main``?"""
    if not args or args[0] not in {"checkout", "switch"}:
        return False
    rest = args[1:]
    creates = {"-b", "-B"} if args[0] == "checkout" else {"-c", "-C", "--create", "--force-create"}
    if any(a in creates or (a.startswith(("-b", "-B")) and args[0] == "checkout") for a in rest):
        return True
    positional = [a for a in rest if not a.startswith("-")]
    if "--" in rest or not positional:
        return False
    if positional == ["main"]:
        return False
    # a file checkout without `--` is not a branch change
    return not (args[0] == "checkout" and all((directory / a).exists() for a in positional))


def blocked_directory(command: str, cwd: Path) -> Path | None:
    """The main-checkout directory the command would switch a branch in, or None."""
    try:
        segments = _segments(command)
    except ValueError:
        return None
    current = cwd
    for tokens in segments:
        if tokens[0] == "cd":
            target = Path(tokens[1]).expanduser() if len(tokens) > 1 else Path.home()
            if len(tokens) == 1 or tokens[1] != "-":
                current = (current / target).resolve()
            continue
        parsed = _git_args(tokens)
        if parsed is None:
            continue
        cdir, args = parsed
        directory = (current / cdir).resolve() if cdir else current
        if _switches_branch(args, directory) and is_main_checkout(directory):
            return directory
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    cwd = Path(payload.get("cwd") or Path.cwd())
    found = blocked_directory(command, cwd)
    if found is None:
        return 0
    print(MESSAGE.format(dir=found), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
