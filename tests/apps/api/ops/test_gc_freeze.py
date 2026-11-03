"""Frozen warm-heap objects are not visited by a full collection."""

import gc

from algotrade_api.ops.gc_freeze import YOUNG_THRESHOLD, freeze_warm_heap, tune_collector


def test_freezing_moves_tracked_objects_out_of_the_collected_generations() -> None:
    keep = [{"row": [i]} for i in range(1000)]
    try:
        frozen = freeze_warm_heap()
        assert frozen >= 1000
        # a frozen object freed by reference counting leaves the permanent generation, so the
        # count may fall below the number returned (527740 vs 527742 on CI); it never exceeds it
        assert 1000 <= gc.get_freeze_count() <= frozen
        assert all(o is not keep[0] for o in gc.get_objects())  # a full pass does not see it
    finally:
        gc.unfreeze()
    assert keep


def test_tune_collector_raises_only_the_young_threshold() -> None:
    before = gc.get_threshold()
    try:
        tune_collector()
        assert gc.get_threshold() == (YOUNG_THRESHOLD, before[1], before[2])
    finally:
        gc.set_threshold(*before)
