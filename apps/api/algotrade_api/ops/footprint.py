"""The memory footprint of a process on this Mac, read-only: macOS ``footprint -p <pid>`` (the
number Activity Monitor calls Memory, compressed pages included, not the RSS that hid the 36 GB
warm, docs/perf/api-memory.md). Used by ``make doctor`` (the process listening on the API's
port) and by the cache warmer's per-step log line (its own process, cached a few seconds).
``None`` wherever the tool is absent or its output unreadable (not macOS, no such process):
callers treat that as unknown, never as small."""

import logging
import os
import re
import subprocess
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

type Run = Callable[[list[str]], tuple[int, str]]

_UNITS_MB = {"B": 1 / 1024**2, "KB": 1 / 1024, "MB": 1.0, "GB": 1024.0, "TB": 1024.0**2}
_FOOTPRINT = re.compile(r"Footprint:\s*([\d.]+)\s*(B|KB|MB|GB|TB)\b")
OWN_CACHE_S = 5.0  # the warmer asks between steps (seconds apart): one call per few seconds


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return p.returncode, p.stdout


def parse_footprint_mb(text: str) -> float | None:
    """The footprint line of ``footprint`` output in MB (``Footprint: 1440 KB``), else None."""
    match = _FOOTPRINT.search(text)
    return float(match.group(1)) * _UNITS_MB[match.group(2)] if match else None


def process_footprint_mb(pid: int, run: Run = _run) -> float | None:
    """The footprint of process ``pid`` in MB; None when it cannot be read."""
    rc, out = run(["footprint", "-p", str(pid), "--noCategories"])
    return parse_footprint_mb(out) if rc == 0 else None


def listener_pids(port: int, run: Run = _run) -> list[int]:
    """The pids listening on TCP ``port`` on any address (``lsof``); several under ``--reload``
    (the parent holds the socket, a child serves)."""
    rc, out = run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    return [int(t) for t in out.split() if t.isdigit()] if rc == 0 else []


class OwnFootprint:
    """This process's footprint in MB, re-read at most every ``OWN_CACHE_S``."""

    def __init__(self, run: Run = _run, clock: Callable[[], float] = time.monotonic):
        self._run, self._clock = run, clock
        self._at = float("-inf")
        self._mb: float | None = None
        self._warned = False

    def __call__(self) -> float | None:
        now = self._clock()
        if now - self._at >= OWN_CACHE_S:
            self._mb = process_footprint_mb(os.getpid(), self._run)
            if self._mb is None and not self._warned:  # a broken probe must not hide the guard
                log.warning(
                    "cannot read this process's footprint: warm steps are logged without it"
                )
                self._warned = True
            self._at = now
        return self._mb
