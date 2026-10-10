"""`scripts/perf/api_latency.py`: the operation inventory from a capture, the row count, the
per-page totals and the rendered table (no server)."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "perf" / "api_latency.py"
_spec = importlib.util.spec_from_file_location("perf_api_latency", SCRIPT)
assert _spec and _spec.loader
lat = importlib.util.module_from_spec(_spec)
sys.modules["perf_api_latency"] = lat
_spec.loader.exec_module(lat)

PAGES = {
    "/a": [
        {"kind": "graphql", "op": "X", "variables": {"k": 1}, "query": "query X { x }"},
        {"kind": "graphql", "op": "X", "variables": {"k": 2}, "query": "query X { x }"},
        {"kind": "graphql", "op": "Y", "variables": {}, "query": "query Y { y }"},
    ],
    "/b": [{"kind": "graphql", "op": "Y", "variables": {}, "query": "query Y { y }"}],
}


def _metrics(cold: float) -> dict:
    return {
        "status": 200,
        "cold_ms": cold,
        "warm_p50_ms": 1.0,
        "warm_p95_ms": 2.0,
        "nocache_p50_ms": cold / 2,
        "bytes": 10,
        "rows": 1,
    }


def test_inventory_keeps_first_variables_and_distinct_ops_per_page() -> None:
    ops, by_page = lat.inventory(PAGES)
    assert ops["X"]["variables"] == {"k": 1}
    assert by_page == {"/a": ["X", "Y"], "/b": ["Y"]}


def test_largest_list_finds_the_longest_nested_list() -> None:
    assert lat.largest_list({"a": [1, 2], "b": {"c": [[1, 2, 3], []]}}) == 3
    assert lat.largest_list({"a": 1}) == 0


def test_page_totals_sum_and_critical_path() -> None:
    ops = {"X": _metrics(100.0), "Y": _metrics(300.0)}
    totals = lat.page_totals({"/a": ["X", "Y"]}, ops)["/a"]
    assert totals["sum_cold_ms"] == 400.0
    assert totals["critical_cold_ms"] == 300.0
    assert totals["slowest"] == "Y"
    assert totals["sum_nocache_p50_ms"] == pytest.approx(200.0)


def test_render_sorts_by_cold_ms_descending() -> None:
    ops = {"Fast": _metrics(1.0), "Slow": _metrics(9.0)}
    report = {
        "generated": "now",
        "operations": ops,
        "pages": lat.page_totals({"/a": ["Fast", "Slow"]}, ops),
    }
    text = lat.render(report)
    assert text.index("| Slow |") < text.index("| Fast |")
