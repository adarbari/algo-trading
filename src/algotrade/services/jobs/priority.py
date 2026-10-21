"""Background priority of a process that shares the Mac with the API (ADR 0077 decision 21):
the one place that lowers CPU niceness and, on darwin, disk priority."""

import contextlib
import ctypes
import logging
import os
import sys

log = logging.getLogger(__name__)

# <sys/resource.h> (darwin). UTILITY, not THROTTLE: the ingest holds the store's commit lock
# while it writes and the API's own writes wait on that lock, so its I/O must stay prompt.
IOPOL_TYPE_DISK, IOPOL_SCOPE_PROCESS, IOPOL_UTILITY = 0, 0, 2


def lower_priority(nice: int) -> None:
    """Take on background CPU (niceness ``nice`` in total, not added to the current one) and
    (darwin) utility disk priority for the rest of this process, and so for the workers it
    spawns (both are inherited); never raises: a platform without the calls just runs at
    normal priority, and a refused disk policy is logged."""
    with contextlib.suppress(OSError):
        if nice > 0:
            os.nice(max(0, nice - os.nice(0)))
    if sys.platform == "darwin":
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.setiopolicy_np(IOPOL_TYPE_DISK, IOPOL_SCOPE_PROCESS, IOPOL_UTILITY) != 0:
                log.warning("disk priority not lowered (errno %d)", ctypes.get_errno())
        except (OSError, AttributeError):
            log.warning("disk priority not lowered (no libc call)")
