"""Run a command under the machine-wide `make check` lock: one full check at a time, at full speed.

Full checks from several worktrees used to run side by side (three to five at once in the week
to 2026-10-07), each capped at two workers and each taking 30 to 40 minutes. The lock queues
them instead: a check waits for the one ahead (it says which worktree holds it, since when),
then runs with every core. The lock file (`~/.cache/algotrade/check.lock`, `CHECK_LOCK=`)
holds the owner's pid, worktree and start time while it is held. Usage:
`check_lock.py [--lock PATH] -- <command...>`; the command's exit code is returned.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

DEFAULT_LOCK = Path(os.environ.get("CHECK_LOCK") or Path.home() / ".cache/algotrade/check.lock")


def holder(path: Path) -> str:
    """Who holds the lock, from its file: `pid cwd started` (or 'another make check')."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    return text or "another make check"


def run_locked(command: list[str], lock: Path = DEFAULT_LOCK, out: TextIO = sys.stderr) -> int:
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+", encoding="utf-8") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(f"make check: waiting for the lock held by {holder(lock)}", file=out, flush=True)
            fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        fh.truncate()
        started = datetime.now(tz=UTC).strftime("%H:%MZ")
        fh.write(f"pid {os.getpid()} in {Path.cwd()} since {started}\n")
        fh.flush()
        try:
            return subprocess.run(command, check=False).returncode
        finally:
            fh.seek(0)
            fh.truncate()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command after --")
    return run_locked(command, args.lock)


if __name__ == "__main__":
    sys.exit(main())
