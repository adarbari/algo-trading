"""`scripts/perf/page_profile.py` and the page / memory-guard / failure-flag parts of
`scripts/perf/api_latency.py`: pure logic only (a fake pstats table, no server, no store)."""

import importlib.util
import sys
from pathlib import Path

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


def test_answer_problem_flags_graphql_errors_empty_data_and_http_errors() -> None:
    ok = b'{"data": {"session": {"date": "2026-10-20"}}}'
    assert lat.answer_problem(200, ok) is None
    assert lat.answer_problem(503, b"") == "HTTP 503"
    assert lat.answer_problem(200, b'{"data": null, "errors": [{"message": "boom"}]}') == "boom"
    assert "empty" in (lat.answer_problem(200, b'{"data": {"x": null, "y": []}}') or "")
    assert "empty" in (lat.answer_problem(200, b'{"data": null}') or "")


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
    assert lat.run_needs_url(lat.parse_args(["--page", "/x"])) is False


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
