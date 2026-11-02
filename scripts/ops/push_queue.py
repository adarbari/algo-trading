#!/usr/bin/env python3
"""A machine-wide queue for the pre-push hook (`make pre-push`), the push most waited on first.

2026-11-02: with about 8 sessions pushing at once, the pre-push hook (#1036) ran five
``make changed`` at a time on the 10-core / 16 GB Mac (load 42, 12+ min each); two at a time is
what it carries. Owner decision 2026-11-02: one queue for every worktree, the push with the most
dependent open PRs first. The queue lives in the main checkout's ``var/locks/push-queue/``
(found through ``git rev-parse --git-common-dir``): a ticket file per waiter
(``{pid, branch, pr, priority, enqueued_at}``) and ``PUSH_QUEUE_SLOTS`` (default 2) slot
directories made with ``mkdir`` (atomic, like ``check_lock.sh``). A waiter takes a slot only
when one is free and it is first by (priority desc, enqueued_at asc) among live tickets; a ticket
or slot whose pid is dead, or older than ``STALE_SECONDS``, is dropped at every poll.

Priority = the open PRs that depend on this branch's PR: stacked on it (their head contains this
branch's head commit, or their base is this branch) or naming it in the body (``Stacked on #N``,
``Depends on #N``, ``waits on #N``, ``needs #N``). ``PUSH_PRIORITY`` overrides; any ``gh`` or git
failure gives 0 with the reason printed, so a push is never blocked on GitHub. The wrapper then
runs ``make pre-push WORKERS=${PUSH_QUEUE_WORKERS:-4}`` (the fast lane, ``scripts/pre_push.py``;
``make changed`` stays the full local check) and frees its slot when that ends or is
signalled. Run by the ``pre-push-fast`` pre-push hook in ``.pre-commit-config.yaml``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SLOTS = 2
WORKERS = "4"
HOOK_TARGET = "pre-push"
POLL_SECONDS = 5.0
STALE_SECONDS = 2 * 3600.0
GH_TIMEOUT = 15

_DEPENDS = r"(?:stacked\s+on|depends\s+on|waits\s+on|needs)\s+#{n}(?!\d)"


def count_dependants(
    pr_number: int | None,
    prs: list[dict[str, Any]],
    descendant_refs: set[str] | frozenset[str] = frozenset(),
    own_ref: str = "",
) -> int:
    """Open PRs (from ``prs``: number, headRefName, baseRefName, body) that depend on this one.

    A PR counts once, if its head is in ``descendant_refs`` (its branch contains our head
    commit), its base is our branch, or its body says it waits on ``#pr_number``.
    """
    pattern = re.compile(_DEPENDS.format(n=pr_number), re.IGNORECASE) if pr_number else None
    counted: set[int] = set()
    for pr in prs:
        number = pr.get("number")
        if number == pr_number or pr.get("headRefName") == own_ref:
            continue
        stacked = pr.get("headRefName") in descendant_refs or (
            bool(own_ref) and pr.get("baseRefName") == own_ref
        )
        named = bool(pattern and pattern.search(pr.get("body") or ""))
        if stacked or named:
            counted.add(number if isinstance(number, int) else id(pr))
    return len(counted)


def order_tickets(tickets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Highest priority first, then first come first served (ties: lowest pid)."""
    return sorted(tickets, key=lambda t: (-t["priority"], t["enqueued_at"], t["pid"]))


def is_stale(entry: dict[str, Any], now: float, alive: Any, limit: float = STALE_SECONDS) -> bool:
    """A ticket or slot is stale when its pid is dead or it is older than ``limit``."""
    return not alive(entry["pid"]) or now - entry["enqueued_at"] > limit


def may_run(me: int, tickets: list[dict[str, Any]], busy_slots: int, slots: int) -> bool:
    """A slot is free and ``me`` is first among the live tickets."""
    ordered = order_tickets(tickets)
    return busy_slots < slots and bool(ordered) and ordered[0]["pid"] == me


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def queue_dir(cwd: Path | None = None) -> Path:
    """``var/locks/push-queue`` of the main checkout, shared by every worktree."""
    out = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    ).stdout.strip()
    return Path(out).parent / "var" / "locks" / "push-queue"


def _run(args: list[str]) -> str:
    return subprocess.run(
        args, capture_output=True, text=True, check=True, timeout=GH_TIMEOUT
    ).stdout


def compute_priority() -> tuple[int, int | None, str]:
    """(priority, this branch's PR number or None, a reason line); 0 on any failure."""
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    override = os.environ.get("PUSH_PRIORITY")
    pr: int | None = None
    try:
        try:
            pr = json.loads(_run(["gh", "pr", "view", branch, "--json", "number"]))["number"]
        except subprocess.CalledProcessError:
            pr = None  # no PR yet: only stacked branches can count
        if override is not None:
            return int(override), pr, "PUSH_PRIORITY"
        prs = json.loads(
            _run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--state",
                    "open",
                    "--limit",
                    "100",
                    "--json",
                    "number,headRefName,baseRefName,body",
                ]
            )
        )
        descendants = {
            p["headRefName"]
            for p in prs
            if subprocess.run(
                ["git", "merge-base", "--is-ancestor", "HEAD", f"origin/{p['headRefName']}"],
                check=False,
                capture_output=True,
                timeout=GH_TIMEOUT,
            ).returncode
            == 0
        }
        return count_dependants(pr, prs, descendants, branch), pr, "open dependants"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        reason = f"priority 0, GitHub unavailable ({type(exc).__name__})"
        return (int(override) if override and override.lstrip("-").isdigit() else 0), pr, reason


def _read(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _live(directory: Path, pattern: str, now: float) -> list[dict[str, Any]]:
    """Entries matching ``pattern`` in ``directory``; stale ones are removed."""
    live = []
    for path in directory.glob(pattern):
        target = path / "ticket.json" if path.is_dir() else path
        entry = _read(target)
        if entry is None:
            continue  # being written
        if is_stale(entry, now, pid_alive):
            shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(
                missing_ok=True
            )
        else:
            live.append(entry)
    return live


def acquire(qdir: Path, ticket: dict[str, Any], slots: int, poll: float) -> Path:
    """Wait in the queue; return the slot directory taken."""
    qdir.mkdir(parents=True, exist_ok=True)
    mine = qdir / f"ticket.{ticket['pid']}.json"
    mine.write_text(json.dumps(ticket))
    try:
        while True:
            now = time.time()
            waiting = _live(qdir, "ticket.*.json", now)
            held = _live(qdir, "slot.*", now)
            ordered = order_tickets(waiting)
            pos = next((i + 1 for i, t in enumerate(ordered) if t["pid"] == ticket["pid"]), 1)
            if may_run(ticket["pid"], waiting, len(held), slots):
                for n in range(slots):
                    slot = qdir / f"slot.{n}"
                    try:
                        slot.mkdir()
                    except FileExistsError:
                        continue
                    (slot / "ticket.json").write_text(json.dumps(ticket))
                    return slot
            print(
                f"push queue: position {pos} of {len(ordered)}, priority {ticket['priority']}, "
                f"{len(held)}/{slots} slots busy",
                flush=True,
            )
            time.sleep(poll)
    finally:
        mine.unlink(missing_ok=True)


def main() -> int:
    slots = int(os.environ.get("PUSH_QUEUE_SLOTS", SLOTS))
    workers = os.environ.get("PUSH_QUEUE_WORKERS", WORKERS)
    try:
        priority, pr, reason = compute_priority()
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        priority, pr, branch, reason = 0, None, "?", f"priority 0 ({type(exc).__name__})"
    print(
        f"push queue: priority {priority} ({reason}), slots {slots}, workers {workers}", flush=True
    )
    ticket = {
        "pid": os.getpid(),
        "branch": branch,
        "pr": pr,
        "priority": priority,
        "enqueued_at": time.time(),
    }
    slot = acquire(queue_dir(), ticket, slots, POLL_SECONDS)

    def release(*_: object) -> None:
        shutil.rmtree(slot, ignore_errors=True)

    child = subprocess.Popen(
        ["make", HOOK_TARGET, f"WORKERS={workers}"],
        env={**os.environ, "WEB_WORKERS": os.environ.get("WEB_WORKERS", workers)},
    )

    def forward(signum: int, _frame: object) -> None:
        child.send_signal(signum)

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, forward)
    try:
        return child.wait()
    finally:
        release()


if __name__ == "__main__":
    sys.exit(main())
