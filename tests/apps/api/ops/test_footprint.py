"""The footprint reader: ``footprint`` output in MB, the listener's pid, the cached own read."""

from algotrade_api.ops import footprint
from algotrade_api.ops.footprint import OwnFootprint, listener_pid, parse_footprint_mb

OUT = "zsh [34186]: 64-bit    Footprint: 36 GB (16384 bytes per page)\n"


def test_it_reads_the_footprint_line_in_any_unit() -> None:
    assert parse_footprint_mb(OUT) == 36 * 1024
    assert parse_footprint_mb("x    Footprint: 1440 KB (16384)") == 1440 / 1024
    assert parse_footprint_mb("Footprint: 2.5 GB") == 2.5 * 1024
    assert parse_footprint_mb("no such process") is None


def test_an_unreadable_process_is_unknown_not_zero() -> None:
    assert footprint.process_footprint_mb(1, lambda cmd: (1, "")) is None
    assert footprint.process_footprint_mb(1, lambda cmd: (0, OUT)) == 36 * 1024


def test_the_listener_pid_is_the_first_lsof_line() -> None:
    assert listener_pid(8000, lambda cmd: (0, "4242\n4243\n")) == 4242
    assert listener_pid(8000, lambda cmd: (1, "")) is None
    assert listener_pid(8000, lambda cmd: (127, "no lsof")) is None


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
