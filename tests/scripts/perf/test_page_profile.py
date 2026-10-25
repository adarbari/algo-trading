"""`scripts/perf/page_profile.py` and the page / memory-guard / failure-flag parts of
`scripts/perf/api_latency.py`: pure logic only (a fake pstats table, no server, no store)."""

import asyncio
import contextlib
import cProfile
import importlib.util
import json
import os
import pstats
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import graphql
import pytest

PERF = Path(__file__).resolve().parents[3] / "scripts" / "perf"
sys.path.insert(0, str(PERF))  # api_latency imports web_page_ops and page_profile by name


def _load(name: str, file: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, PERF / file)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pp = _load("page_profile", "page_profile.py")
lat = _load("perf_api_latency_pp", "api_latency.py")

SWAP = "vm.swapusage: total = 16384.00M  used = 15800.00M  free = 584.00M  (encrypted)"


# ---- swap guard ---------------------------------------------------------------------------


def test_parse_swap_free_reads_megabytes_and_gigabytes() -> None:
    assert pp.parse_swap_free_mb(SWAP) == 584.0
    assert pp.parse_swap_free_mb("total = 2.00G  used = 0.50G  free = 1.50G") == 1536.0
    assert pp.parse_swap_free_mb("nonsense") is None


def test_swap_guard_aborts_below_the_floor_and_passes_above() -> None:
    pp.swap_guard(500, reader=lambda: 584.0)
    with pytest.raises(pp.SwapLowError) as err:
        pp.swap_guard(500, reader=lambda: 499.0)
    assert "499" in str(err.value)


def test_swap_guard_does_not_block_when_swap_cannot_be_read() -> None:
    pp.swap_guard(500, reader=lambda: None)


# ---- page / operation selection -----------------------------------------------------------

OPS = {"A": {"query": "q A"}, "B": {"query": "q B"}, "C": {"query": "q C"}}
BY_PAGE = {"/x": ["A", "B"], "/y": ["B", "C"]}


def test_select_operations_by_page_keeps_page_order_and_dedupes() -> None:
    got = pp.select_operations(OPS, BY_PAGE, ["/y", "/x"], [], {})
    assert list(got) == ["B", "C", "A"]


def test_select_operations_by_name_and_union_with_pages() -> None:
    assert list(pp.select_operations(OPS, BY_PAGE, [], ["C"], {})) == ["C"]
    assert list(pp.select_operations(OPS, BY_PAGE, ["/x"], ["C"], {})) == ["A", "B", "C"]


def test_select_operations_falls_back_to_the_static_map_for_an_uncaptured_route() -> None:
    assert list(pp.select_operations(OPS, BY_PAGE, ["/z"], [], {"/z": ["C"]})) == ["C"]


def test_select_operations_rejects_unknown_route_operation_or_undocumented_op() -> None:
    with pytest.raises(pp.SelectionError, match="/nope"):
        pp.select_operations(OPS, BY_PAGE, ["/nope"], [], {})
    with pytest.raises(pp.SelectionError, match="Zed"):
        pp.select_operations(OPS, BY_PAGE, [], ["Zed"], {})
    with pytest.raises(pp.SelectionError, match="Q"):
        pp.select_operations(OPS, BY_PAGE, ["/z"], [], {"/z": ["Q"]})


# ---- bucket attribution on a fake pstats --------------------------------------------------


def _fn(file: str, name: str) -> tuple[str, int, str]:
    return (file, 1, name)


def _stats(table: dict) -> dict:
    """{key: (cc, nc, tt, ct, callers)} like pstats.Stats.stats."""
    return {k: (v[0], v[0], v[1], v[2], v[3]) for k, v in table.items()}


ROOT = _fn("/repo/src/algotrade/services/read/x.py", "load")
RUN = _fn("/repo/src/algotrade/storage/runs.py", "from_json")
LOADS = _fn("/py/json/__init__.py", "loads")
STAT = ("~", 0, "<built-in method posix.stat>")
READ = _fn("/site-packages/pyarrow/parquet/core.py", "read_table")
PA_LEAF = _fn("/site-packages/pyarrow/_parquet.pyx", "decode")
PD = _fn("/site-packages/pandas/core/frame.py", "merge")
HELPER = _fn("/repo/src/algotrade/misc_helper.py", "helper")


def _fake() -> dict:
    # tottime 1.0 root, 2.0 from_json, 3.0 json.loads (under from_json), 0.5 stat (under
    # from_json AND read_table), 4.0 read_table, 1.5 decode (under read_table), 2.5 pandas
    return _stats(
        {
            ROOT: (1, 1.0, 14.5, {}),
            RUN: (1, 2.0, 5.5, {ROOT: (1, 1, 2.0, 5.5)}),
            LOADS: (1, 3.0, 3.0, {RUN: (1, 1, 3.0, 3.0)}),
            STAT: (4, 0.5, 0.5, {RUN: (2, 2, 0.25, 0.25), READ: (2, 2, 0.25, 0.25)}),
            READ: (1, 4.0, 6.0, {ROOT: (1, 1, 4.0, 6.0)}),
            PA_LEAF: (1, 1.5, 1.5, {READ: (1, 1, 1.5, 1.5)}),
            PD: (1, 2.5, 2.5, {ROOT: (1, 1, 2.5, 2.5)}),
        }
    )


def test_attribute_conserves_total_time_and_never_double_counts() -> None:
    buckets = pp.attribute(_fake())
    assert sum(buckets.values()) == pytest.approx(1.0 + 2.0 + 3.0 + 0.5 + 4.0 + 1.5 + 2.5)


def test_attribute_assigns_named_entry_points_and_their_callees() -> None:
    b = pp.attribute(_fake())
    assert b["filesystem walks"] == pytest.approx(0.5)  # stat keeps its own bucket
    assert b["run-record decode"] == pytest.approx(2.0 + 3.0)  # from_json + json.loads under it
    assert b["Parquet / Arrow"] == pytest.approx(4.0 + 1.5)  # read_table + its leaf
    assert b["pandas / numpy"] == pytest.approx(2.5)
    assert b["other"] == pytest.approx(1.0)  # the unmatched root


def test_attribute_a_callee_of_unmatched_code_only_is_other() -> None:
    stats = _stats({ROOT: (1, 1.0, 3.0, {}), HELPER: (1, 2.0, 2.0, {ROOT: (1, 1, 2.0, 2.0)})})
    assert pp.attribute(stats) == {"other": pytest.approx(3.0)}


def test_attribute_survives_recursive_callers() -> None:
    a, b = _fn("/repo/src/algotrade/a.py", "a"), _fn("/repo/src/algotrade/b.py", "b")
    stats = _stats(
        {a: (2, 1.0, 2.0, {b: (1, 1, 1.0, 1.0)}), b: (1, 1.0, 2.0, {a: (1, 1, 1.0, 1.0)})}
    )
    assert sum(pp.attribute(stats).values()) == pytest.approx(2.0)


def test_call_counts_stats_and_opened_files() -> None:
    opened = ("~", 0, "<built-in function open>")
    stats = _fake()
    stats[opened] = (3, 3, 0.1, 0.1, {})
    counts = pp.call_counts(stats)
    assert counts == {"stat calls": 4, "files opened": 3}


def test_top_functions_are_algotrade_and_pyarrow_by_cumulative_time() -> None:
    top = pp.top_functions(_fake(), 3)
    assert [t["cumulative_s"] for t in top] == [14.5, 6.0, 5.5]
    assert all("pandas" not in t["function"] for t in top)


# ---- the generated page file --------------------------------------------------------------


def test_upsert_section_replaces_one_page_and_keeps_the_others() -> None:
    doc = pp.upsert_section("", "/a", "## `/a`\n\nfirst\n")
    doc = pp.upsert_section(doc, "/b", "## `/b`\n\nbee\n")
    doc = pp.upsert_section(doc, "/a", "## `/a`\n\nsecond\n")
    assert doc.count("## `/a`") == 1 and "second" in doc and "first" not in doc
    assert "bee" in doc and doc.startswith("# Page profiles")


_ROW = {
    "op": "Op",
    "wall_s": 1.5,
    "bytes": 1234,
    "rows": 7,
    "error": None,
    "buckets": {"other": 1.0},
    "counts": {"stat calls": 9, "files opened": 2},
    "top": [],
}


def test_render_page_lists_buckets_flags_and_top_functions() -> None:
    row = {
        "op": "Op",
        "wall_s": 1.5,
        "bytes": 1234,
        "rows": 7,
        "error": None,
        "buckets": {"other": 1.0, "filesystem walks": 0.5},
        "counts": {"stat calls": 9, "files opened": 2},
        "top": [{"function": "algotrade/x.py:1(load)", "cumulative_s": 1.2, "calls": 3}],
    }
    md = pp.render_page("/p", [row, {**row, "op": "Bad", "error": "boom"}])
    assert "## `/p`" in md and "### Op" in md and "filesystem walks" in md
    assert "FAILED: boom" in md and "stat calls" in md and "algotrade/x.py:1(load)" in md


# ---- failure flagging in api_latency ------------------------------------------------------


def test_answer_problem_flags_graphql_errors_and_http_errors_not_empty_pages() -> None:
    ok = b'{"data": {"session": {"date": "2026-10-20"}}}'
    assert lat.answer_problem(200, ok) is None
    assert lat.answer_problem(503, b"") == "HTTP 503"
    assert lat.answer_problem(200, b'{"data": null, "errors": [{"message": "boom"}]}') == "boom"
    assert lat.answer_problem(200, b'{"data": {"x": null, "y": []}}') is None  # not a failure
    assert lat.answer_problem(200, b"<html>") == "not JSON"
    assert lat.answer_problem(200, b"[1, 2]") == "not JSON"  # JSON, but not an object
    assert lat.answer_problem(200, b'{"errors": ["plain"]}') == "plain"


def test_empty_note_marks_empty_pages_for_a_look_without_failing_them() -> None:
    assert "EMPTY (check)" in (lat.empty_note(200, b'{"data": {"x": null, "y": []}}') or "")
    assert "EMPTY (check)" in (lat.empty_note(200, b'{"data": null}') or "")
    assert lat.empty_note(200, b'{"data": {"d": "x"}}') is None
    assert lat.empty_note(500, b"") is None
    assert lat.empty_note(200, b"not json") is None


def test_cold_suspect_flags_a_cold_answer_much_smaller_than_the_uncached_one() -> None:
    assert lat.cold_suspect(47, 4_800_000) is not None
    assert lat.cold_suspect(4_700_000, 4_800_000) is None
    assert lat.cold_suspect(0, 0) is None


def test_cold_row_prints_bytes_and_the_first_error() -> None:
    line = lat.cold_line("IdeasPage", 47.0, 120, 0, "boom")
    assert "47 ms" in line and "120 B" in line and "FAILED: boom" in line
    assert "FAILED" not in lat.cold_line("X", 1.0, 5, 1, None)


# ---- the real-store refusal still applies to --profile and --page runs ---------------------


def test_profile_and_page_runs_need_a_clone_url() -> None:
    with pytest.raises(lat.RefusalError):
        lat.check_target(None, [], False, need_url=True)
    assert lat.run_needs_url(lat.parse_args(["--profile", "--page", "/x"])) is True
    assert lat.run_needs_url(lat.parse_args(["--uncached"])) is True
    assert lat.run_needs_url(lat.parse_args(["--page", "/x"])) is True  # a subset run starts an API
    assert lat.run_needs_url(lat.parse_args(["--ops", "A"])) is True
    assert lat.run_needs_url(lat.parse_args([])) is False


def test_profile_with_the_real_store_is_refused_before_anything_starts() -> None:
    real = lat.REPO / "var" / "data"  # lexical overlap: it need not exist
    assert lat.main(["--profile", "--page", "/x", "--data-url", f"file://{real}"]) == 2
    assert lat.main(["--page", "/x", "--data-url", f"file://{real}"]) == 2


def test_profile_accepts_one_page_only() -> None:
    assert lat.profile_selection_error(
        lat.parse_args(["--profile", "--page", "/a", "--page", "/b"])
    )
    assert lat.profile_selection_error(lat.parse_args(["--profile"]))
    assert not lat.profile_selection_error(lat.parse_args(["--profile", "--page", "/a"]))
    assert not lat.profile_selection_error(lat.parse_args(["--profile", "--ops", "A", "B"]))


def test_profile_refuses_the_real_store_even_when_confirmed() -> None:
    real = lat.REPO / "var" / "data"
    argv = ["--profile", "--page", "/x", "--i-know-this-is-the-real-store"]
    assert lat.main([*argv, "--data-url", f"file://{real}"]) == 2
    assert lat.main(argv) == 2  # and never without a URL


def test_run_profile_never_sets_a_missing_data_url() -> None:
    with pytest.raises(ValueError, match="data URL"):
        pp.run_profile(
            {},
            "/x",
            patch="",
            data_url="",
            config_dir=Path(),
            out=Path("x"),
            problem=lambda *_: None,
            rows_of=lambda _: 0,
        )


def test_swap_guard_stops_on_low_disk_under_the_clone() -> None:
    def low(_: Path) -> float:
        return 3.0

    def high(_: Path) -> float:
        return 40.0

    with pytest.raises(pp.SwapLowError, match="disk"):
        pp.swap_guard(500, reader=lambda: 9000.0, disk_path=Path("/c"), disk_free_gb=low)
    pp.swap_guard(500, reader=lambda: 9000.0, disk_path=Path("/c"), disk_free_gb=high)
    pp.swap_guard(500, reader=lambda: 9000.0, disk_path=None, disk_free_gb=low)


def test_saw_nothing_flags_a_profile_without_stat_calls_or_algotrade_code() -> None:
    thread_only = _stats({_fn("/py/asyncio/base_events.py", "run_forever"): (1, 1.0, 1.0, {})})
    assert pp.saw_nothing(thread_only) is True
    assert pp.saw_nothing(_fake()) is False
    md = pp.render_page("/p", [{**_ROW, "saw_nothing": True}])
    assert "PROFILE SAW NOTHING (thread issue)" in md


def test_the_read_pool_calls_run_inline_on_the_calling_thread() -> None:
    async def go() -> tuple[int, int]:
        a = await pp._inline_sync(threading.get_ident, limiter=object())
        b = await pp._inline_thread(threading.get_ident)
        return a, b

    assert asyncio.run(go()) == (threading.get_ident(), threading.get_ident())


# ---- --profile-limit: snapshots, stability, partial section, cut ----------------------------


def _snap(t: float, other: float, fs: float, stat: int = 0, opened: int = 0) -> dict:
    return {
        "t": t,
        "buckets": {"other": other, "filesystem walks": fs},
        "counts": {"stat calls": stat, "files opened": opened},
    }


def test_snapshot_of_a_fake_profile_has_buckets_and_counters() -> None:
    snap = pp.snapshot_of(_fake(), 12.0)
    assert snap["t"] == 12.0 and snap["counts"]["stat calls"] == 4
    assert sum(snap["buckets"].values()) == pytest.approx(14.5)


def test_stability_needs_three_snapshots_and_moves_under_five_points() -> None:
    steady = [_snap(60, 50, 50), _snap(120, 52, 48), _snap(180, 53, 47), _snap(240, 54, 46)]
    assert pp.stability(steady) == "STABILITY: shares stable"
    moving = [_snap(60, 90, 10), _snap(120, 70, 30), _snap(180, 50, 50)]
    assert "still moving" in pp.stability(moving)
    assert "too few" in pp.stability(steady[:2])
    # only the last three count: an early swing does not matter
    assert pp.stability([_snap(1, 99, 1), *steady]) == "STABILITY: shares stable"


def test_trend_table_has_shares_counters_and_rates() -> None:
    lines = pp.trend_table([_snap(10, 50, 50, stat=1000, opened=20)])
    row = lines[-1]
    assert "| 10 |" in row and "50%" in row and "1,000" in row and "100" in row  # 100 stat/s


def test_partial_section_is_labelled_and_carries_trend_stability_and_the_note() -> None:
    snaps = [_snap(60, 50, 50, 10, 1), _snap(120, 51, 49, 20, 2), _snap(180, 52, 48, 30, 3)]
    row = {**_ROW, "partial": {"reason": "limit", "elapsed": 180.0, "snapshots": snaps}}
    md = pp.render_page("/p", [row])
    assert "PARTIAL: profiled for 180 s, the call had not finished" in md
    assert "STABILITY: shares stable" in md and "| elapsed s |" in md
    assert "absolute seconds are lower bounds" in md


def test_run_profiled_cuts_at_the_limit_and_keeps_snapshots_and_the_profile() -> None:
    def spin() -> None:
        end = time.perf_counter() + 5
        while time.perf_counter() < end:
            sum(range(1000))

    res = pp.run_profiled(spin, limit_s=0.35, snapshot_s=0.1)
    assert res.cut == "limit" and 0.3 < res.elapsed < 2
    assert len(res.snapshots) >= 3 and res.stats  # ticks, plus the final snapshot
    assert [s["t"] for s in res.snapshots] == sorted(s["t"] for s in res.snapshots)


def test_run_profiled_returns_the_value_when_the_call_finishes() -> None:
    res = pp.run_profiled(lambda: 7, limit_s=5, snapshot_s=1)
    assert res.value == 7 and res.cut is None


def test_a_sigterm_during_the_call_is_a_cut_not_a_crash() -> None:
    old = signal.signal(signal.SIGTERM, pp._on_signal)
    try:
        res = pp.run_profiled(lambda: os.kill(os.getpid(), signal.SIGTERM) or 1, limit_s=None)
    finally:
        signal.signal(signal.SIGTERM, old)
    assert res.cut == "SIGTERM"


def test_partial_row_writes_the_section_even_when_cut(tmp_path: Path) -> None:
    res = pp.Profiled(stats=_fake(), snapshots=[_snap(1, 1, 1)], cut="SIGTERM", elapsed=3.0)
    row = pp.partial_row("Op", res)
    out = tmp_path / "p.md"
    pp._flush(out, "/p", [row])
    text = out.read_text()
    assert "PARTIAL: profiled for 3 s" in text and "SIGTERM" in text


def test_limit_and_snapshot_must_be_positive_and_guards_are_unchanged() -> None:
    bad = lat.parse_args(["--profile", "--page", "/a", "--profile-limit", "0"])
    assert lat.profile_selection_error(bad)
    assert lat.profile_selection_error(
        lat.parse_args(["--profile", "--page", "/a", "--profile-snapshot", "-1"])
    )
    ok = lat.parse_args(["--profile", "--page", "/a", "--profile-limit", "600"])
    assert not lat.profile_selection_error(ok) and ok.profile_limit == 600
    assert lat.parse_args(["--profile", "--page", "/a"]).profile_limit is None
    real = lat.REPO / "var" / "data"
    assert (
        lat.main(
            ["--profile", "--page", "/x", "--profile-limit", "5", "--data-url", f"file://{real}"]
        )
        == 2
    )
    with pytest.raises(pp.SwapLowError):
        pp.swap_guard(500, reader=lambda: 1.0)


def test_a_cut_unwinds_a_blocking_call_inside_an_asyncio_task() -> None:
    """The ASGI call is a task that blocks the loop thread (inline resolvers): the Cut raised in
    the handler must come out of run_until_complete, and the drain must leave no task pending."""
    loop = asyncio.new_event_loop()

    async def blocked() -> None:
        end = time.perf_counter() + 5
        while time.perf_counter() < end:
            sum(range(1000))

    res = pp.run_profiled(
        lambda: loop.run_until_complete(blocked()),
        limit_s=0.2,
        snapshot_s=0.1,
        on_cut=lambda: pp._drain(loop),
    )
    assert res.cut == "limit" and res.elapsed < 2
    assert not [t for t in asyncio.all_tasks(loop) if not t.done()]
    loop.close()


# ---- review fixes: snapshots keep the stack, atomic flush, Cut inside an exception group ------


def _leaf() -> int:
    return sum(range(2000))


# cProfile keeps ONE context stack for the whole process (sys.monitoring is interpreter-wide in
# 3.12), so a call any other thread makes while ``_leaf`` is in flight (an xdist worker's execnet
# thread, coverage) can take the parent's place and lose or misattribute a call: CI saw an exact
# count of 23091 for 23092. The snapshot test therefore profiles in a fresh one-thread process.
_SNAPSHOT_PROBE = """
import json, sys, time
sys.path.insert(0, sys.argv[1])
import page_profile as pp

def _leaf():
    return sum(range(2000))

def _mid():
    end = time.perf_counter() + 0.4
    while time.perf_counter() < end:
        _leaf()

def _outer():
    _mid()

res = pp.run_profiled(_outer, limit_s=None, snapshot_s=0.05)
rows = {k[2]: v for k, v in res.stats.items() if k[2] in ("_leaf", "_mid", "_outer")}
print(json.dumps({
    "snapshots": len(res.snapshots), "elapsed": res.elapsed,
    "rows": {n: {"calls": v[1], "cum": v[3], "callers": {c[2]: r[1] for c, r in v[4].items()}}
             for n, v in rows.items()},
}))
"""


def test_a_mid_run_snapshot_leaves_callers_and_cumulative_time_intact() -> None:
    out = subprocess.run(
        [sys.executable, "-c", _SNAPSHOT_PROBE, str(PERF)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout
    got = json.loads(out)
    assert got["snapshots"] >= 3  # ticks happened while _mid was on the stack
    leaf, mid, outer = (got["rows"][n] for n in ("_leaf", "_mid", "_outer"))
    assert "_mid" in leaf["callers"]  # the leaf calls after a snapshot keep a caller
    assert "_outer" in mid["callers"]
    floor = 0.9 * got["elapsed"]
    assert outer["cum"] > floor and mid["cum"] > floor  # outer frames kept gaining
    # and every leaf call reaches a caller: the table is a connected graph
    assert sum(leaf["callers"].values()) == leaf["calls"]


def test_stats_now_matches_pstats_after_the_profile_stops() -> None:
    prof = cProfile.Profile()
    prof.enable()
    _outer_short()
    prof.disable()
    mine, theirs = pp.stats_now(prof), pstats.Stats(prof).stats
    assert mine.keys() == theirs.keys()
    for key in mine:
        assert mine[key][:2] == theirs[key][:2] and set(mine[key][4]) == set(theirs[key][4])


def _outer_short() -> None:
    for _ in range(50):
        _leaf()


def test_flush_is_atomic_and_a_signal_during_it_never_truncates_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic: the stop signal is injected inside the temp-file write (a hook, no timing).
    Mid-way the old page is intact; the signal is held back, the new content lands, and only
    then the Cut is delivered."""
    out = tmp_path / "page-profiles.md"
    pp._flush(out, "/a", [{**_ROW}])
    old = out.read_text()
    mid: list[str] = []
    real_fchmod = os.fchmod

    def hook(fd: int, mode: int) -> None:
        os.kill(os.getpid(), signal.SIGTERM)  # the handler runs here, in the main thread
        mid.append(out.read_text())  # the page is still the old one, untruncated
        real_fchmod(fd, mode)

    monkeypatch.setattr(pp.os, "fchmod", hook)
    prev = signal.signal(signal.SIGTERM, pp._on_signal)
    try:
        with pytest.raises(pp.Cut) as cut:  # delivered once the flush is done
            pp._flush(out, "/b", [{**_ROW}])
    finally:
        signal.signal(signal.SIGTERM, prev)
    assert mid == [old] and cut.value.reason == "SIGTERM"
    text = out.read_text()
    assert "## `/a`" in text and "## `/b`" in text
    assert [p.name for p in tmp_path.iterdir()] == ["page-profiles.md"]  # no temp file left


def test_a_failed_write_keeps_the_old_file_and_removes_the_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "p.md"
    pp._flush(out, "/a", [{**_ROW}])
    before = out.read_text()

    def boom(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):
        pp._flush(out, "/b", [{**_ROW}])
    assert out.read_text() == before and [p.name for p in tmp_path.iterdir()] == ["p.md"]


def test_a_cut_wrapped_in_exception_groups_is_still_a_cut() -> None:
    def nested() -> None:
        raise BaseExceptionGroup(
            "tg", [ValueError("x"), BaseExceptionGroup("in", [pp.Cut("limit")])]
        )

    res = pp.run_profiled(nested, limit_s=None)
    assert res.cut == "limit"
    assert pp.find_cut(ValueError("plain")) is None

    def other() -> None:
        raise BaseExceptionGroup("tg", [ValueError("x")])

    with pytest.raises(BaseExceptionGroup):
        pp.run_profiled(other, limit_s=None)


# ---- the capped EdgesPage run produced no section: a cut inside an executor task -------------


def _slow_graphql(loop: asyncio.AbstractEventLoop):  # type: ignore[no-untyped-def]
    """A real graphql-core execution whose async resolver is a long CPU loop (the shape of the
    edge resolvers): the Cut lands inside the executor's task, not in the awaiting caller."""
    schema = graphql.build_schema("type Query { slow: String }")

    async def slow(*_: object) -> str:
        end = time.perf_counter() + 5
        while time.perf_counter() < end:
            _leaf()
        return "x"

    return lambda: loop.run_until_complete(
        graphql.graphql(schema, "{ slow }", root_value={"slow": slow})
    )


def test_a_cut_inside_a_graphql_executor_task_still_yields_the_partial_result() -> None:
    loop = asyncio.new_event_loop()
    seen: list[pp.Profiled] = []
    res = pp.run_profiled(
        _slow_graphql(loop),
        limit_s=0.3,
        snapshot_s=0.1,
        on_cut=lambda: pp._drain(loop),
        on_partial=seen.append,
    )
    assert res.cut == "limit" and res.stats and len(res.snapshots) >= 3
    assert len(seen) == 1 and seen[0].cut == "limit"  # written from the handler, once
    loop.close()


def test_the_partial_is_written_even_if_the_cut_never_reaches_the_caller() -> None:
    seen: list[pp.Profiled] = []

    def swallowed() -> None:  # the Cut is caught and dropped by "the app": a task swallowed it
        try:
            end = time.perf_counter() + 5
            while time.perf_counter() < end:
                _leaf()
        except pp.Cut:
            pass
        raise RuntimeError("stray")

    with pytest.raises(RuntimeError):
        pp.run_profiled(swallowed, limit_s=0.2, snapshot_s=0.1, on_partial=seen.append)
    assert len(seen) == 1 and seen[0].cut == "limit"


def test_a_failing_on_cut_or_drain_after_a_cut_is_not_fatal() -> None:
    def boom() -> None:
        raise pp.Cut("limit")

    res = pp.run_profiled(lambda: (_ for _ in ()).throw(pp.Cut("limit")), limit_s=None, on_cut=boom)
    assert res.cut == "limit"

    loop = asyncio.new_event_loop()

    async def reraises_on_cancel() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise pp.Cut("limit") from None

    task = loop.create_task(reraises_on_cancel())
    loop.run_until_complete(asyncio.sleep(0))
    pp._drain(loop)  # must not raise
    assert task.done()
    loop.close()


def test_a_sigterm_mid_operation_writes_the_partial_before_unwinding() -> None:
    seen: list[pp.Profiled] = []
    old = signal.signal(signal.SIGTERM, pp._on_signal)
    try:
        res = pp.run_profiled(
            lambda: os.kill(os.getpid(), signal.SIGTERM) or time.sleep(1),
            limit_s=None,
            on_partial=seen.append,
        )
    finally:
        signal.signal(signal.SIGTERM, old)
    assert res.cut == "SIGTERM" and [s.cut for s in seen] == ["SIGTERM"]
    assert not pp.CURRENT  # the running operation is cleared after the call


def test_an_operation_running_is_never_classified_as_between_operations() -> None:
    assert pp.running_operation() is None
    seen: list[str | None] = []
    pp.run_profiled(lambda: seen.append(pp.running_operation()), limit_s=None, name="Op")
    assert seen == ["Op"] and pp.running_operation() is None


# ---- follow-up: stop signals survive clean-up, emit once, bounded drain, swallowed Cut -------


def test_a_stop_signal_cut_during_clean_up_is_not_swallowed_but_a_limit_cut_is() -> None:
    def stop() -> None:
        raise pp.Cut("SIGTERM")

    with pytest.raises(pp.Cut, match="SIGTERM"):
        pp.run_profiled(lambda: (_ for _ in ()).throw(pp.Cut("limit")), limit_s=None, on_cut=stop)
    assert pp.survivable(pp.Cut("limit")) and not pp.survivable(pp.Cut("SIGHUP"))
    assert pp.survivable(ValueError("x"))
    assert not pp.survivable(BaseExceptionGroup("g", [pp.Cut("SIGINT")]))


def test_emit_runs_once_even_if_a_signal_arrives_while_it_computes() -> None:
    calls: list[int] = []

    def on_partial(_res: pp.Profiled) -> None:
        calls.append(1)
        os.kill(os.getpid(), signal.SIGTERM)  # a second stop, mid-handler: held back, not a re-run

    def spin() -> None:
        end = time.perf_counter() + 5
        while time.perf_counter() < end:
            _leaf()

    old = signal.signal(signal.SIGTERM, pp._on_signal)
    try:
        res = pp.run_profiled(spin, limit_s=0.2, snapshot_s=0.1, on_partial=on_partial)
    finally:
        signal.signal(signal.SIGTERM, old)
    assert calls == [1] and res.cut in ("limit", "SIGTERM")


def test_a_resolver_that_swallows_the_cut_still_gets_its_section_and_the_run_ends() -> None:
    """The mechanism of the capped EdgesPage run: the Cut lands in a resolver that catches
    BaseException and carries on. The section is written from the handler and the run ends."""
    loop = asyncio.new_event_loop()
    schema = graphql.build_schema("type Query { slow: String }")
    seen: list[pp.Profiled] = []

    async def slow(*_: object) -> str:
        end = time.perf_counter() + 0.6
        while time.perf_counter() < end:
            with contextlib.suppress(BaseException):  # the swallowing resolver
                _leaf()
        return "x"

    res = pp.run_profiled(
        lambda: loop.run_until_complete(
            graphql.graphql(schema, "{ slow }", root_value={"slow": slow})
        ),
        limit_s=0.2,
        snapshot_s=0.1,
        on_cut=lambda: pp._drain(loop),
        on_partial=seen.append,
    )
    assert len(seen) == 1 and seen[0].cut == "limit" and res.cut == "limit"
    loop.close()


def test_drain_is_bounded_when_a_sibling_task_is_in_long_cpu_work() -> None:
    loop = asyncio.new_event_loop()

    async def cpu_on_cancel() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            end = time.perf_counter() + 20
            while time.perf_counter() < end:
                _leaf()

    task = loop.create_task(cpu_on_cancel())
    loop.run_until_complete(asyncio.sleep(0))
    t0 = time.perf_counter()
    pp._drain(loop, timeout_s=0.3)
    assert time.perf_counter() - t0 < 3 and task is not None
    loop.close()


def test_drain_does_not_report_the_original_cut_again(
    capsys: pytest.CaptureFixture[str],
) -> None:
    loop = asyncio.new_event_loop()

    async def reraises() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise pp.Cut("limit") from None

    task = loop.create_task(reraises())
    loop.run_until_complete(asyncio.sleep(0))
    pp._drain(loop)
    assert "draining the cut call failed" not in capsys.readouterr().err and task.done()
    loop.close()


def test_the_page_file_is_world_readable_not_0600(tmp_path: Path) -> None:
    out = tmp_path / "p.md"
    pp._flush(out, "/a", [{**_ROW}])
    assert out.stat().st_mode & 0o777 == 0o644
