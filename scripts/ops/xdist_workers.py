#!/usr/bin/env python3
"""The pytest-xdist worker count for the shared machine: ``auto``, or ``2`` under load.

Owner learning 2026-10-18: ``make changed`` and the test targets run ``-n auto`` (one worker per
CPU); with several sessions on the Mac the 1-minute load average sat above 12 and every run
slowed the others. Above ``LOAD_LIMIT`` this prints ``2``, else ``auto``. It caps workers
only: no gate, test or threshold changes. ``ALGOTRADE_LOAD_LIMIT`` overrides the limit.
``--explain`` prints one line for ``make doctor``.
"""

from __future__ import annotations

import os
import sys

LOAD_LIMIT = 12.0
CAPPED = "2"
FREE = "auto"


def workers(load1: float, limit: float = LOAD_LIMIT) -> str:
    """``CAPPED`` when the 1-minute load average is above ``limit``, else ``FREE``."""
    return CAPPED if load1 > limit else FREE


def main(argv: list[str]) -> int:
    try:
        load1 = os.getloadavg()[0]
    except OSError:  # no load average on this platform: do not cap
        load1 = 0.0
    limit = float(os.environ.get("ALGOTRADE_LOAD_LIMIT", LOAD_LIMIT))
    chosen = workers(load1, limit)
    if "--explain" in argv:
        print(f"1-minute load {load1:.1f} (limit {limit:g}): xdist workers {chosen}")
    else:
        print(chosen)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
