"""`scripts/perf/api_latency.py`: the operation inventory from a capture, the row count, the
per-page totals and the rendered table (no server)."""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

import algotrade.services.read.context as cx
import algotrade_api.graphql.response_cache as rc
from algotrade_api.graphql import warm

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


# ---- --uncached: guards, launch patches, calls per page, the Pages section ----------------------

CAPTURE = {
    "/a": [
        {"kind": "graphql", "op": "X", "variables": {}, "query": "q"},
        {"kind": "graphql", "op": "X", "variables": {}, "query": "q"},
        {"kind": "graphql", "op": "Y", "variables": {}, "query": "q"},
    ],
    "/b": [{"kind": "graphql", "op": "Y", "variables": {}, "query": "q"}],
}


def _full(cold: float, un: float) -> dict:
    return {**_metrics(cold), "uncached_p50_ms": un, "load_p50_ms": un * 2, "bytes": 100}


def test_request_counts_count_repeats_per_operation() -> None:
    assert lat.request_counts(CAPTURE) == {"/a": {"X": 2, "Y": 1}, "/b": {"Y": 1}}


def test_calls_per_page_sums_repeats_and_keeps_the_critical_path_distinct() -> None:
    ops = {"X": _full(100.0, 10.0), "Y": _full(300.0, 30.0)}
    page = lat.calls_per_page(lat.request_counts(CAPTURE), ops)["/a"]
    assert (page["requests"], page["distinct"], page["bytes"]) == (3, 2, 300)
    assert page["sum_uncached_p50_ms"] == 50.0  # 2 x 10 + 30
    assert page["critical_uncached_p50_ms"] == 30.0
    assert page["sum_cold_ms"] == 500.0
    assert page["critical_cold_ms"] == 300.0
    assert page["ops"]["X"]["count"] == 2
    assert page["ops"]["X"]["share_uncached_p50_ms"] == pytest.approx(0.4)
    assert page["ops"]["X"]["bytes"] == 200


def test_launch_patches_by_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    for cls, names in (
        (rc.ResponseCache, ("get", "get_stale")),
        (cx.ResultCache, ("get", "get_or_compute")),
        (warm.CacheWarmer, ("run", "warm_home", "replay_operations")),
    ):
        for n in names:
            monkeypatch.setattr(cls, n, getattr(cls, n))  # restored after the test
    monkeypatch.setattr(sys, "argv", ["-c", "0", "0"])
    exec(lat.PATCH, {})
    assert cx.ResultCache().get_or_compute("k", lambda: 1) == 1
    assert cx.ResultCache.get is not None and rc.ResponseCache.get.__name__ != "<lambda>"
    monkeypatch.setattr(sys, "argv", ["-c", "0", "1"])
    exec(lat.PATCH, {})
    assert rc.ResponseCache.get.__name__ == "<lambda>"
    assert cx.ResultCache.get.__name__ != "<lambda>"  # the loader cache still answers
    monkeypatch.setattr(sys, "argv", ["-c", "0", "2"])
    exec(lat.PATCH, {})
    cache = cx.ResultCache()
    calls = []
    assert cache.get_or_compute("k", lambda: calls.append(1) or 5) == 5
    assert cache.get_or_compute("k", lambda: calls.append(1) or 5) == 5
    assert len(calls) == 2  # never answered from the cache
    assert cache.get("k") is None
    assert asyncio.run(warm.CacheWarmer.run(object())) is None  # the warmer is idle
    assert warm.CacheWarmer.warm_home(object()) is None


def test_patch_asserts_its_targets_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["-c", "0", "2"])
    monkeypatch.delattr(warm.CacheWarmer, "replay_operations")
    with pytest.raises(AssertionError, match="targets moved"):
        exec(lat.PATCH, {})


def test_check_target_refuses_the_real_store(tmp_path: Path) -> None:
    real = tmp_path / "var" / "data"
    stores = [real.resolve()]
    with pytest.raises(lat.RefusalError):
        lat.check_target(f"file://{real}", stores, confirmed=False, need_url=True)
    with pytest.raises(lat.RefusalError):  # inside it, and a parent of it
        lat.check_target(f"file://{real}/bars", stores, confirmed=False, need_url=True)
    with pytest.raises(lat.RefusalError):
        lat.check_target(f"file://{tmp_path}", stores, confirmed=False, need_url=True)
    assert lat.check_target(f"file://{real}", stores, confirmed=True, need_url=True)
    clone = f"file://{tmp_path / 'clone'}"
    assert lat.check_target(clone, stores, confirmed=False, need_url=True) == (
        f"file://{(tmp_path / 'clone').resolve()}"
    )


def test_check_target_sees_another_spelling_and_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "Var" / "data"
    real.mkdir(parents=True)
    link = tmp_path / "alias"
    link.symlink_to(real)
    with pytest.raises(lat.RefusalError):  # a symlink to it (case-insensitive volumes alike)
        lat.check_target(f"file://{link}", [real.resolve()], confirmed=False, need_url=True)
    monkeypatch.setattr(lat, "REPO", tmp_path)  # a relative URL resolves against the repo
    with pytest.raises(lat.RefusalError):
        lat.check_target("file://./Var/data", [real.resolve()], confirmed=False, need_url=True)
    assert lat.check_target("file://./clone", [real.resolve()], False, True) == (
        f"file://{(tmp_path / 'clone').resolve()}"
    )


def test_check_target_needs_a_url_for_uncached_but_not_for_the_baseline() -> None:
    with pytest.raises(lat.RefusalError):
        lat.check_target(None, [], confirmed=False, need_url=True)
    assert lat.check_target(None, [], confirmed=False, need_url=False) is None
    assert lat.check_target(None, [], confirmed=True, need_url=True) is None
    with pytest.raises(lat.RefusalError):
        lat.check_target("s3://bucket", [], confirmed=False, need_url=False)


def test_real_stores_include_env_repo_and_main_checkout(tmp_path: Path) -> None:
    env = {"ALGOTRADE_DATA_URL": f"file://{tmp_path / 'e'}"}
    found = lat.real_stores(env, tmp_path / "wt", tmp_path / "main")
    assert (tmp_path / "e").resolve() in found
    assert (tmp_path / "wt" / "var" / "data").resolve() in found
    assert (tmp_path / "main" / "var" / "data").resolve() in found


def test_uncached_config_turns_release_reads_off(tmp_path: Path) -> None:
    site = tmp_path / "cfg" / "site"
    site.mkdir(parents=True)
    (site / "nightly.toml").write_text("[serving]\nrelease_reads = true  # kill switch\n")
    out = lat.uncached_config(tmp_path / "cfg", tmp_path / "out")
    (tmp_path / "cfg" / "users").mkdir()
    (tmp_path / "cfg" / "users" / "u.toml").write_text("x")
    out = lat.uncached_config(tmp_path / "cfg", tmp_path / "out2")
    assert (out / "users" / "u.toml").exists()  # the whole root is copied
    assert "release_reads = false" in (out / "site" / "nightly.toml").read_text()
    assert "release_reads = true" in (site / "nightly.toml").read_text()  # the source is untouched


def test_free_port_stays_in_the_worktree_block_and_never_falls_back() -> None:
    port = lat.free_port({"ALGOTRADE_PORT_BASE": "14120"})
    assert 14128 <= port <= 14139
    with pytest.raises(RuntimeError):
        lat.free_port({})


def test_response_error_flags_http_and_graphql_errors() -> None:
    assert lat.response_error(200, b'{"data": {"a": 1}}') is None
    assert lat.response_error(503, b"") == "HTTP 503"
    assert lat.response_error(200, b'{"errors": [{"message": "boom"}]}') == "boom"
    assert lat.response_error(200, b"<html>") == "not JSON"


def test_uncached_table_flags_failed_calls() -> None:
    m = {
        **_full(1.0, 2.0),
        "failed_calls": 3,
        "first_error": "boom",
        "uncached_p95_ms": 2.0,
        "load_p95_ms": 4.0,
        "rows": 0,
    }
    text = lat.render_uncached(
        {
            "generated": "g",
            "target": "t",
            "uncached_repeats": 5,
            "load_clients": 4,
            "remaining_memos": [],
            "operations": {"X": m},
            "pages": {},
        }
    )
    assert "FAILED x3: boom" in text


def test_page_report_compares_static_and_capture_and_lists_gaps() -> None:
    wpo = lat.wpo
    routes = [
        wpo.Route("/a", kind="page"),
        wpo.Route("/c", kind="page"),
        wpo.Route("/later", kind="placeholder"),
    ]
    static = {
        "/a": {"X": wpo.LOAD, "Z": wpo.LOAD, "W": wpo.HANDLER},
        "/c": {"X": wpo.LOAD},
        "/later": {},
    }
    ops = {"X": _full(100.0, 10.0), "Y": _full(300.0, 30.0)}
    rep = lat.page_report(
        routes, static, {"S": wpo.LOAD}, CAPTURE, ops, {"X", "Y", "Z", "W", "S", "Orphan"}
    )
    a = rep["pages"]["/a"]
    assert a["captured"] == {"X": 2, "Y": 1}
    assert any(d.startswith("Y: captured, not in the static map") for d in a["differences"])
    assert any(d.startswith("Z: static on-load, not captured") for d in a["differences"])
    assert a["static_interaction"] == ["W"]
    assert a["basis"] == "capture" and a["requests"] == 3
    assert rep["pages"]["/c"]["basis"] == "static on-load"
    assert rep["routes_without_capture"] == ["/c", "/later"]
    assert rep["capture_without_route"] == ["/b"]
    assert rep["operations_without_page"] == ["Orphan"]
    assert rep["pages_without_data"] == ["/later"]
    text = "\n".join(lat.render_pages(rep))
    assert "Operations without a page" in text and "Orphan" in text
