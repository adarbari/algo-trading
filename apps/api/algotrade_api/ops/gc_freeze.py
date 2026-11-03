"""Keep the cyclic garbage collector off the warmed caches: after a warm pass the cached frames
and read objects are moved to the permanent generation (``gc.freeze``), so a full collection
scans only what requests allocate since. Without it a gen-2 pass over a multi-GB heap holds the
GIL for seconds (2026-11-02 `make load` stress: ``visit_decref`` / ``deduce_unreachable`` took the
cores, the event loop waited on the GIL, ``/health`` p99 5 s, requests timed out). Cached data is
acyclic, so freezing it leaks nothing a collection would have freed."""

import gc
import logging

log = logging.getLogger(__name__)

YOUNG_THRESHOLD = 50_000  # allocations before a gen-0 pass (default 700): fewer, larger passes


def freeze_warm_heap() -> int:
    """Move every object tracked now to the permanent generation; the number frozen."""
    gc.freeze()
    frozen = gc.get_freeze_count()
    log.info("gc: %d objects frozen after the warm pass", frozen)
    return frozen


def tune_collector() -> None:
    """Raise the gen-0 threshold once at start (``gc.set_threshold``); gen 1 and 2 keep theirs."""
    _, gen1, gen2 = gc.get_threshold()
    gc.set_threshold(YOUNG_THRESHOLD, gen1, gen2)
