"""The free-space floor: the nightly refuses to start on a nearly full data volume."""

from pathlib import Path

import pytest

from algotrade.config.site.settings import NightlySettings
from algotrade.core.model.errors import AlgoTradeError
from algotrade_ingestion.ops.disk import require_free_disk


def free(gb: float):  # type: ignore[no-untyped-def]
    return lambda _path: int(gb * 1e9)


def test_a_volume_below_the_floor_is_refused_with_the_numbers_and_the_setting() -> None:
    with pytest.raises(AlgoTradeError, match=r"9\.4 GB free.*15 GB floor.*min_free_gb"):
        require_free_disk(Path("/data"), 15, free(9.4))


def test_a_volume_at_or_above_the_floor_passes() -> None:
    require_free_disk(Path("/data"), 15, free(15.0))
    require_free_disk(Path("/data"), 15, free(200))


def test_the_floor_and_the_thread_caps_are_configurable_with_safe_defaults() -> None:
    d = NightlySettings.from_document(None)
    assert (d.min_free_gb, d.arrow_cpu_threads, d.arrow_io_threads) == (15.0, 2, 4)
    doc = {"resources": {"min_free_gb": 30, "arrow_cpu_threads": 1, "arrow_io_threads": 2}}
    s = NightlySettings.from_document(doc)
    assert (s.min_free_gb, s.arrow_cpu_threads, s.arrow_io_threads) == (30.0, 1, 2)
