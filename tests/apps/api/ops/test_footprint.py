"""The footprint reader: ``footprint`` output in MB, the listener's pid, the cached own read."""

import pytest

from algotrade_api.ops import footprint
from algotrade_api.ops.footprint import OwnFootprint, listener_pids, parse_footprint_mb

OUT = "zsh [34186]: 64-bit    Footprint: 36 GB (16384 bytes per page)\n"


def test_it_reads_the_footprint_line_in_any_unit() -> None:
    assert parse_footprint_mb(OUT) == 36 * 1024
    assert parse_footprint_mb("x    Footprint: 1440 KB (16384)") == 1440 / 1024
    assert parse_footprint_mb("Footprint: 2.5 GB") == 2.5 * 1024
    assert parse_footprint_mb("no such process") is None


def test_an_unreadable_process_is_unknown_not_zero() -> None:
    assert footprint.process_footprint_mb(1, lambda cmd: (1, "")) is None
    assert footprint.process_footprint_mb(1, lambda cmd: (0, OUT)) == 36 * 1024


def test_every_listener_pid_is_returned_for_a_reload_parent_and_child() -> None:
    assert listener_pids(8000, lambda cmd: (0, "4242\n4243\n")) == [4242, 4243]
    assert listener_pids(8000, lambda cmd: (1, "")) == []
    assert listener_pids(8000, lambda cmd: (127, "no lsof")) == []


def test_a_probe_that_raises_reads_as_unknown() -> None:
    def boom(cmd: list[str]) -> tuple[int, str]:
        raise ValueError("garbled")

    assert OwnFootprint(boom)() is None


def test_a_probe_that_reads_nothing_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    own = OwnFootprint(lambda cmd: (127, "no footprint"), lambda: 1e9)
    with caplog.at_level("WARNING"):
        assert own() is None
        own._at = float("-inf")  # the cache window passed
        assert own() is None
    assert caplog.text.count("cannot read this process") == 1


def test_the_own_footprint_is_read_once_per_cache_window() -> None:
    calls: list[list[str]] = []
    now = [0.0]

    def run(cmd: list[str]) -> tuple[int, str]:
        calls.append(cmd)
        return 0, OUT

    own = OwnFootprint(run, lambda: now[0])
    assert own() == own() == 36 * 1024 and len(calls) == 1
    now[0] += footprint.OWN_CACHE_S
    own()
    assert len(calls) == 2
