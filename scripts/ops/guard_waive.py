#!/usr/bin/env python3
"""Claude Code PreToolUse hook (Bash): only the owner waives a failed ingestion step.

Owner decision 2026-10-10 (incident: a session ran ``algotrade-ingest nightly --date
2026-10-09 --waive chains`` and marked the session complete with 761 underlyings' option chains
missing). Reads the hook JSON on stdin; exits 2 with a message when a command runs
``algotrade-ingest`` (any path, ``uv run``, ``python -m algotrade_ingestion``, inside ``env`` /
``nohup`` / ``sh -c`` wrappers) with ``--waive``. A waiver is run from the owner's own terminal.
"""

from __future__ import annotations

import json
import shlex
import sys

MESSAGE = (
    "BLOCKED: `--waive` is the owner's decision only (owner rule 2026-10-10). A waiver marks a "
    "failed ingestion step accepted and releases every later session; a session or agent never "
    "passes it. Report the failed step and its cause to the owner, who waives from their own "
    "terminal (CLAUDE.md, Ingestion workflows)."
)
_SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")"}
_WRAPPERS = {"env", "nohup", "uv", "run", "time", "exec", "command", "sudo", "nice", "-m"}
_SHELLS = {"sh", "bash", "zsh"}


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


def _basename(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _is_ingest(token: str) -> bool:
    name = _basename(token)
    return name == "algotrade-ingest" or name.startswith("algotrade_ingestion")


def _is_wrapper(token: str) -> bool:
    name = _basename(token)
    return (
        name in _WRAPPERS
        or name.startswith(("python", "-"))
        or (
            "=" in token
            and not token.startswith("-")
            and "/" not in token.split("=", maxsplit=1)[0]
        )
    )


def waives(command: str, depth: int = 0) -> bool:
    """True when some command in ``command`` runs the ingestion CLI with ``--waive``."""
    if depth > 4:
        return False
    try:
        segments = _segments(command)
    except ValueError:
        return False
    for tokens in segments:
        head = 0
        while head < len(tokens) and _is_wrapper(tokens[head]):
            head += 1
        if head >= len(tokens):
            continue
        if _basename(tokens[head]) in _SHELLS:
            for i, tok in enumerate(tokens[head + 1 :], start=head + 1):
                is_c = tok.startswith("-") and "c" in tok[1:] and not tok.startswith("--")
                if is_c and i + 1 < len(tokens) and waives(tokens[i + 1], depth + 1):
                    return True
            continue
        if _is_ingest(tokens[head]) and any(
            t == "--waive" or t.startswith("--waive=") for t in tokens[head + 1 :]
        ):
            return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not waives(command):
        return 0
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
