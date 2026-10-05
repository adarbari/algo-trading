"""`make status`: where things stand, in about 15 lines. Read-only: open PRs with CI state (gh),
running ingest jobs and `var/logs/*.status` tails, the last nightly run and the store's latest
session (through the explore services, never a path), dev servers on 8000 / 5173 / 5174.
Every probe goes through `Probes`; a probe that cannot answer says why on its line.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PORTS = {8000: "api", 5173: "web dev", 5174: "storybook/preview"}
JOB_MARKERS = ("algotrade-ingest", "var/logs/")
MAX_PRS = 5


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=REPO, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return p.returncode, p.stdout.strip()


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _store_facts() -> tuple[str, str]:
    """(latest session, last nightly) read through the library; never a path of our own."""
    # Lazy: the library may be missing (no venv), and status must still report the rest.
    from algotrade.config.env import config_dir, data_url  # noqa: PLC0415
    from algotrade.config.user import UserContext  # noqa: PLC0415
    from algotrade.services.explore.store import latest_session, open_store  # noqa: PLC0415
    from algotrade.services.read.context import open_stores  # noqa: PLC0415
    from algotrade.services.read.ops.runs import load_nightly_runs  # noqa: PLC0415

    store = open_store(data_url(), config_dir(), UserContext("local"))
    latest = latest_session(store.reader)
    runs = load_nightly_runs(open_stores(store.reader, store.configs, store.user), 1)
    last = f"{runs[0].session} {runs[0].status}" if runs else "none recorded"
    return str(latest) if latest else "empty", last


@dataclass
class Probes:
    which: Callable[[str], str | None] = shutil.which
    run: Callable[[list[str]], tuple[int, str]] = _run
    port_open: Callable[[int], bool] = _port_open
    store_facts: Callable[[], tuple[str, str]] = _store_facts
    logs: Path = field(default_factory=lambda: REPO / "var" / "logs")


def prs(p: Probes) -> list[str]:
    if not p.which("gh"):
        return ["PRs: gh not installed (brew install gh)"]
    rc, out = p.run(["gh", "pr", "list", "--json", "number,title,isDraft,statusCheckRollup"])
    if rc != 0:
        return ["PRs: gh failed (run: gh auth login)"]
    items = json.loads(out or "[]")
    if not items:
        return ["PRs: none open"]
    lines = [f"PRs: {len(items)} open"]
    for pr in items[:MAX_PRS]:
        checks = [
            c.get("conclusion") or c.get("status") or "?" for c in pr.get("statusCheckRollup") or []
        ]
        if any(c in ("FAILURE", "CANCELLED", "TIMED_OUT") for c in checks):
            ci = "CI failing"
        elif any(c in ("IN_PROGRESS", "QUEUED", "PENDING", "?") for c in checks):
            ci = "CI running"
        else:
            ci = "CI green" if checks else "no checks"
        draft = " draft" if pr.get("isDraft") else ""
        lines.append(f"  #{pr['number']} {str(pr['title'])[:60]} [{ci}{draft}]")
    return lines


def jobs(p: Probes) -> list[str]:
    rc, out = p.run(["ps", "-eo", "pid,etime,args"])
    running = []
    for line in out.splitlines() if rc == 0 else []:
        if any(m in line for m in JOB_MARKERS) and "status.py" not in line and "ps -eo" not in line:
            pid, etime, *args = line.split()
            running.append(f"  {pid} up {etime}: {' '.join(args)[:70]}")
    lines = [f"Ingest jobs: {len(running)} running", *running]
    for f in sorted(p.logs.glob("*.status")) if p.logs.exists() else []:
        tail = f.read_text().strip().splitlines()[-1:] or ["(empty)"]
        lines.append(f"  {f.name}: {tail[0][:80]}")
    return lines


def store(p: Probes) -> list[str]:
    try:
        latest, last = p.store_facts()
    except Exception as exc:  # a missing store or venv must not crash a status report
        return [f"Store: unreadable ({type(exc).__name__}: {str(exc)[:60]})"]
    return [f"Store: latest session {latest}; last nightly {last}"]


def servers(p: Probes) -> list[str]:
    up = [f"{port} {name}" for port, name in PORTS.items() if p.port_open(port)]
    return ["Dev servers: " + (", ".join(up) if up else "none listening")]


def report(p: Probes) -> str:
    return "\n".join([*prs(p), *jobs(p), *store(p), *servers(p)])


def main() -> int:
    sys.stdout.write(report(Probes()) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
