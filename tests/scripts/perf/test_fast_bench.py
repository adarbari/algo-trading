"""`scripts/perf/fast_bench.py`: the bar file is valid, the recorded history parses, the rule
judges critical paths, exceptions and the shell, and the tool refuses the real store (no server)."""

import dataclasses
import importlib.util
import json
import re
import shutil
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from algotrade.storage.configs.files import FileConfigStore
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "perf"))
import web_page_ops as wpo  # noqa: E402 (needs scripts/perf on the path)

_spec = importlib.util.spec_from_file_location(
    "perf_fast_bench", ROOT / "scripts" / "perf" / "fast_bench.py"
)
assert _spec and _spec.loader
fb = importlib.util.module_from_spec(_spec)
sys.modules["perf_fast_bench"] = fb
_spec.loader.exec_module(fb)

BAR = {
    "critical_path_limit_s": 1.0,
    "shell_total_limit_s": 1.0,
    "shell_operations": ["Viewer", "GuideEntries"],
    "exception": [
        {"operation": "Slow", "reason": "r", "date": "2026-10-22", "expiry": "2999-01-01"},
        {"operation": "Old", "reason": "r", "date": "2019-10-22", "expiry": "2020-01-01"},
    ],
}


CLEAN = {**BAR, "exception": []}


def _view(crit: float, op: str) -> dict:
    return {"crit_s": crit, "sum_s": crit, "slowest_op": op}


def test_bar_file_is_valid_and_every_exception_has_reason_and_date() -> None:
    bar = fb.load_bar()
    assert bar["critical_path_limit_s"] == 1.0
    assert bar["shell_total_limit_s"] == 1.0
    assert {"Viewer", "SessionDate", "Regime", "StatusStrip", "EdgeDesk", "GuideEntries"} == set(
        bar["shell_operations"]
    )
    exceptions = bar.get("exception", [])
    names = [e["operation"] for e in exceptions]
    assert len(names) == len(set(names))
    assert "InstrumentEvents" not in names  # withdrawn after the option F re-measure
    today = datetime.now(UTC).date()
    for e in exceptions:
        assert e["operation"] and e["reason"].strip() and e["approval"].strip()
        assert date.fromisoformat(e["date"]) <= date.fromisoformat(e["expiry"])
        assert date.fromisoformat(e["date"]) <= today  # never dated in the future


def test_an_expired_exception_no_longer_excuses_a_view() -> None:
    assert set(fb.exceptions_by_op(BAR, date(2019, 12, 31))) == {"Slow", "Old"}
    assert set(fb.exceptions_by_op(BAR)) == {"Slow"}
    res = fb.evaluate({"/a": _view(1.5, "Old")}, 0.2, BAR)
    assert res["rows"][0]["verdict"] == "OVER" and res["failures"]


def test_history_lines_parse_and_carry_the_required_keys() -> None:
    history = fb.read_history()
    assert len(history) >= 8  # rounds 1-8 are seeded
    for h in history:
        assert all(k in h for k in fb.HISTORY_KEYS)
        assert all(k in h["totals"] for k in fb.TOTAL_KEYS)
        assert h["views"]
        for v in h["views"].values():
            assert all(k in v for k in fb.VIEW_KEYS)
    assert [h["sha"] for h in history][-1] == "fb7708269"  # round 8 is the last seeded run
    assert any("machine 2x slower" in h["machine"] for h in history)
    assert all(isinstance(h.get("noisy"), bool) for h in history)
    fb.render_history(history)  # renders


def test_tool_refuses_the_real_store_and_a_missing_url(capsys: pytest.CaptureFixture[str]) -> None:
    assert fb.main([]) == 2
    assert fb.main(["--data-url", f"file://{ROOT / 'var' / 'data'}"]) == 2
    assert "refused" in capsys.readouterr().err


def test_evaluate_fails_over_views_unless_a_named_exception() -> None:
    views = {"/a": _view(0.4, "X"), "/b": _view(1.6, "Slow"), "/c": _view(1.2, "Other")}
    res = fb.evaluate(views, 0.5, BAR)
    verdicts = {r["view"]: r["verdict"] for r in res["rows"]}
    assert verdicts == {"/a": "ok", "/b": "EXCEPTION", "/c": "OVER"}
    assert len(res["failures"]) == 1 and "/c" in res["failures"][0]
    assert res["totals"]["views_over_1s"] == 2


def test_evaluate_fails_when_the_shell_is_over_its_limit() -> None:
    res = fb.evaluate({"/a": _view(0.2, "X")}, 1.2, BAR)
    assert res["failures"] == ["shell: 1.20 s combined over 1.0 s"]


def test_shell_total_counts_each_operation_once_at_its_slowest_variant() -> None:
    assert (
        fb.shell_total(
            {"Viewer": [0.1], "GuideEntries": [0.2, 0.5], "Other": [9]}, ["Viewer", "GuideEntries"]
        )
        == 0.6
    )


def test_ratio_mode_divides_by_the_shell_slowdown_never_below_one() -> None:
    last = [{"totals": {"shell_total_s": 0.5}}]
    assert fb.scale_from_history(1.0, last) == 2.0
    assert fb.scale_from_history(0.3, last) == 1.0
    assert fb.scale_from_history(1.0, []) == 1.0
    res = fb.evaluate({"/a": _view(1.8, "X")}, 1.0, BAR, scale=2.0)
    assert res["rows"][0]["verdict"] == "ok" and not res["failures"]


def test_history_record_round_trips_through_the_file(tmp_path: Path) -> None:
    path = tmp_path / "h.jsonl"
    rec = fb.history_record(
        {"/a": _view(0.4, "X")},
        {"views_over_1s": 0, "seconds_above_bar": 0, "shell_total_s": 0.3},
        "abc",
        1.0,
        2.0,
        "n",
    )
    fb.append_history(rec, path)
    fb.append_history(rec, path)
    assert [json.loads(x) for x in path.read_text().splitlines()] == fb.read_history(path)
    assert all(k in fb.read_history(path)[0] for k in fb.HISTORY_KEYS)


def test_only_filter_keeps_named_operations_and_their_views() -> None:
    distinct = {"A#1": {"name": "A"}, "B#1": {"name": "B"}, "C#1": {"name": "C"}}
    view_ops = {"/x": ["A#1", "B#1"], "/y": ["C#1"]}
    assert fb.restrict(distinct, view_ops, set()) == (distinct, view_ops)
    keep, views = fb.restrict(distinct, view_ops, {"B"})
    assert list(keep) == ["B#1"] and views == {"/x": ["B#1"]}
    assert fb.only_names("A,B", "C") == {"A", "B"}
    assert fb.only_names(None, "C,D") == {"C", "D"} and fb.only_names(None, None) == set()


def test_noisy_flag_is_stored_in_the_history_record() -> None:
    totals = {"views_over_1s": 0, "seconds_above_bar": 0, "shell_total_s": 0.3}
    rec = fb.history_record({"/a": _view(0.4, "X")}, totals, "abc", 1.0, 2.0, "n", True)
    assert rec["noisy"] is True


def test_guard_defaults_are_the_page_profile_floors() -> None:
    assert fb.DISK_FLOOR_GB == [fb.al.pp.MIN_FREE_DISK_GB]
    assert fb.al.SWAP_FLOOR_MB[0] == fb.al.pp.MIN_FREE_SWAP_MB


def test_time_ops_dumps_the_samples_after_every_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeClient:
        def get(self, url: str) -> None:
            return None

    class FakeApi:
        url = "http://x"
        last_error = ""

        def __init__(self, *a: object, **k: object) -> None:
            self.client = FakeClient()

        def call(self, body: dict) -> tuple[float, int, int, int]:
            return 12.0, 200, 10, 1

        def close(self) -> None:
            return None

    monkeypatch.setattr(fb.al, "Api", FakeApi)
    monkeypatch.setattr(fb.al, "uncached_config", lambda src, dst: dst)
    monkeypatch.setattr(fb.al, "guard", lambda: None)
    monkeypatch.setattr(fb, "wait_quiet", lambda limit, load_max: 1.0)
    partial = tmp_path / "samples-partial.json"
    ops, _ = fb.time_ops(
        {"A#1": {"name": "A", "query": "q", "variables": {}}}, "file:///c", 2, 4.0, partial
    )
    dumped = json.loads(partial.read_text())
    assert dumped["samples"] == {"A#1": [12.0, 12.0]} and dumped["names"] == {"A#1": "A"}
    assert ops["A#1"]["avg"] == 12.0 and not ops["A#1"]["noisy"] and not ops["A#1"]["failed"]


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _run_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, call_s: float, reps: int, budget: float
) -> tuple[dict, dict]:
    """time_ops over 2 operations on a fake clock where every timing takes ``call_s``."""
    clock = _Clock()

    class FakeApi:
        url = "http://x"
        last_error = ""

        def __init__(self, *a: object, **k: object) -> None:
            self.client = type("C", (), {"get": staticmethod(lambda url: None)})()

        def call(self, body: dict) -> tuple[float, int, int, int]:
            clock.now += call_s
            return call_s * 1000, 200, 10, 1

        def close(self) -> None:
            return None

    monkeypatch.setattr(fb.al, "Api", FakeApi)
    monkeypatch.setattr(fb.al, "uncached_config", lambda src, dst: dst)
    monkeypatch.setattr(fb.al, "guard", lambda: None)
    monkeypatch.setattr(fb, "wait_quiet", lambda limit, load_max: 1.0)
    ops = {f"{n}#1": {"name": n, "query": "q", "variables": {}} for n in "AB"}
    return fb.time_ops(ops, "file:///c", reps, 4.0, None, budget, clock)


def test_a_fast_run_does_all_its_reps_and_is_confident(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ops, meta = _run_budget(monkeypatch, tmp_path, 1.0, 5, 270)
    assert meta["passes"] == 5 and not meta["low_confidence"] and ops["A#1"]["n"] == 5
    assert meta["stop_reason"] == "reps"


def test_a_loaded_run_stops_early_when_the_next_pass_would_overrun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ops, meta = _run_budget(monkeypatch, tmp_path, 10.0, 5, 70)  # a pass = 20 s
    assert meta["stop_reason"] == "budget"
    assert meta["passes"] == 3 and not meta["low_confidence"]  # 60 s done, the 4th would end at 80
    assert ops["A#1"]["n"] == 3 and ops["A#1"]["avg"] == 10000.0


def test_two_passes_are_always_done_but_flagged_low_confidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ops, meta = _run_budget(monkeypatch, tmp_path, 100.0, 5, 30)
    assert meta["passes"] == fb.MIN_PASSES == 2 and meta["low_confidence"]
    assert ops["B#1"]["n"] == 2


def test_keep_going_never_exceeds_reps_and_predicts_with_the_mean() -> None:
    assert not fb.keep_going(5, 5, 1.0, 270)
    assert fb.keep_going(1, 5, 999.0, 270)  # the minimum
    assert fb.keep_going(3, 5, 150.0, 270) and not fb.keep_going(3, 5, 210.0, 270)


CAPTURE = ROOT / "benchmarks" / "api_latency_views.captured.json"
NOT_CATALOGUE = {"regime@v3", "regime_indicators@v1"}  # table / group names, not features


def _captured_requests() -> list[dict]:
    views = json.loads(CAPTURE.read_text())["views"]
    return [r for v in views.values() for r in (v.get("captured") or {}).get("requests", [])]


def test_the_committed_capture_parses_and_every_operation_in_it_still_exists() -> None:
    """Fitness: a renamed or removed web operation fails here, not in the nightly gate.

    Fix: refresh the capture (docs/perf/page-latency-bar.md, "Refresh the capture")."""
    requests = _captured_requests()
    assert requests and all(r["query"] and isinstance(r["variables"], dict) for r in requests)
    pages = json.loads((ROOT / "benchmarks" / "api_latency_pages.json").read_text())["pages"]
    known = {c["op"] for calls in pages.values() for c in calls if c["kind"] == "graphql"}
    known |= wpo.all_query_ops(ROOT / "apps" / "web" / "src")
    assert {r["op"] for r in requests} <= known, sorted({r["op"] for r in requests} - known)


def test_the_committed_capture_names_only_features_the_catalogue_has() -> None:
    """Fitness: a feature renamed or removed (analyst_*@v1 -> @v2) fails here, not as a 200 with
    an error in the gate."""
    catalogue = set(
        re.findall(r"^## `([^`]+@v\d+)`", (ROOT / "docs/data/features.md").read_text(), re.M)
    )
    named = {
        t
        for r in _captured_requests()
        for t in re.findall(r"[a-z][a-z0-9_]*@v\d+", json.dumps(r["variables"]))
    }
    assert any(n.startswith("analyst_") for n in named)
    assert not named - catalogue - NOT_CATALOGUE, sorted(named - catalogue - NOT_CATALOGUE)


def test_the_gate_measures_the_capture_by_default_and_warns_on_the_static_list(
    tmp_path: Path,
) -> None:
    assert fb.resolve_views_file(None) == (fb.CAPTURED_FILE, "")
    assert fb.resolve_views_file("x.json") == (Path("x.json"), "")
    path, warning = fb.resolve_views_file(None, tmp_path / "missing.json")
    assert path == fb.vw.VIEWS_FILE and "no captured variables" in warning


def test_wrapper_timings_are_parsed_and_stored_in_the_history_record() -> None:
    assert fb.parse_timings("wait_s=3,snapshot_s=240,bad,x=y") == {"wait_s": 3, "snapshot_s": 240}
    totals = {"views_over_1s": 0, "seconds_above_bar": 0, "shell_total_s": 0.3}
    rec = fb.history_record(
        {"/a": _view(0.4, "X")}, totals, "a", 1.0, 2.0, "n", False, {"wait_s": 3}
    )
    assert rec["timings"] == {"wait_s": 3}
    assert "timings" not in fb.history_record({"/a": _view(0.4, "X")}, totals, "a", 1.0, 2.0, "n")


def _ops(**kw: float) -> dict[str, list[float]]:
    return {k: [v] for k, v in kw.items()}


def _failures(**over: object) -> list[str]:
    args: dict = {
        "views": {"/a": {"failed": [], "empty": []}},
        "view_ops": {"/a": ["X#1"]},
        "skipped": {},
        "by_name": _ops(Viewer=0.1, GuideEntries=0.1),
        "bar": CLEAN,
        "subset": False,
        "today": date(2026, 10, 23),
    }
    args.update(over)
    return fb.integrity_failures(**args)


def test_a_clean_run_has_no_integrity_failure() -> None:
    assert _failures() == []


def test_a_view_that_did_not_parse_or_an_unresolved_operation_fails_the_gate() -> None:
    out = _failures(skipped={"/b": "bad", "/c :: Gone": "operation Gone has no document"})
    assert len(out) == 1 and "/b" in out[0] and "Gone" in out[0]


def test_listed_unmeasured_views_pass_until_the_list_expires() -> None:
    bar = {**CLEAN, "unmeasured_views": ["/b"], "unmeasured_expiry": "2026-11-01"}
    assert _failures(bar=bar, skipped={"/b": "no document"}) == []
    assert _failures(bar=bar, skipped={"/b": "x"}, today=date(2026, 11, 2))


def test_empty_views_missing_shell_failed_and_empty_answers_all_fail() -> None:
    assert "no operations" in _failures(view_ops={"/a": []})[0]
    assert "shell operations not measured" in _failures(by_name=_ops(Viewer=0.1))[0]
    assert _failures(by_name=_ops(Viewer=0.1), subset=True) == []
    failed = {"/a": {"failed": ["Boom"], "empty": []}}
    assert "failed" in _failures(views=failed)[0] and "Boom" in _failures(views=failed)[0]
    empty = {"/a": {"failed": [], "empty": ["Hollow", "MyScreens"]}}
    bar = {**CLEAN, "empty_ok": ["MyScreens"], "empty_ok_expiry": "2999-01-01"}
    out = _failures(views=empty, bar=bar)
    assert len(out) == 1 and "Hollow" in out[0] and "MyScreens" not in out[0]


def test_a_missing_shell_operation_is_not_counted_as_zero() -> None:
    assert fb.missing_shell(_ops(Viewer=0.1), ["Viewer", "Regime"]) == ["Regime"]
    with pytest.raises(KeyError):
        fb.shell_total(_ops(Viewer=0.1), ["Viewer", "Regime"])


def test_history_mode_states_the_passes_and_rounds_1_and_2_are_a_different_method() -> None:
    totals = {"views_over_1s": 0, "seconds_above_bar": 0, "shell_total_s": 0.3}
    rec = fb.history_record({"/a": _view(0.4, "X")}, totals, "a", 1.0, 2.0, "n", False, None, 3)
    assert "3 passes" in rec["mode"] and rec["method"] == fb.METHOD
    history = fb.read_history()
    assert [h["method"] for h in history[:2]] == ["cache-mode", "cache-mode"]
    assert all(h["method"] == fb.METHOD for h in history[2:])
    text = fb.render_history(history)
    assert text.count("not comparable") == 2


def test_the_history_file_is_a_parameter_and_the_tracked_file_is_not_touched(
    tmp_path: Path,
) -> None:
    rec = fb.history_record(
        {"/a": _view(0.4, "X")},
        {"views_over_1s": 0, "seconds_above_bar": 0, "shell_total_s": 0.3},
        "a",
        1.0,
        2.0,
        "n",
    )
    before = fb.HISTORY_FILE.read_bytes()
    fb.append_history(rec, tmp_path / "h.jsonl")
    assert fb.read_history(str(tmp_path / "h.jsonl"))[0]["sha"] == "a"
    assert fb.HISTORY_FILE.read_bytes() == before
    assert fb.parse_args(["--history-file", "x"]).history_file == "x"


def test_an_expired_exception_or_unmeasured_list_is_reported_loudly_at_run_time() -> None:
    assert (
        "exception for Slow expired on 2999-01-01" in _failures(bar=BAR, today=date(3000, 1, 1))[0]
    )
    bar = {**BAR, "exception": [{"operation": "Old", "expiry": "2020-01-01"}]}
    assert "exception for Old expired on 2020-01-01" in _failures(bar=bar)[0]


def test_the_committed_capture_resolves_every_operation_and_skips_nothing() -> None:
    """Fitness: the gate must not fail its integrity check on day one, nor skip an operation
    silently: op_set resolves everything, the parametrised guide routes included."""
    distinct, view_ops, skipped = fb.op_set(fb.vw.load_views(fb.CAPTURED_FILE))
    assert skipped == {} and all(view_ops.values())
    names = {d["name"] for d in distinct.values()}
    assert {"EdgeCompare", "EdgePaper", "GuideEdge", "GuideField", "GuideSituation"} <= names
    assert {"GuideScreener", "GuideScreenerCategory", "FeatureCatalogueDetail"} <= names
    assert "/guide/fields/:name" in view_ops and "/guide/situations/:slug" in view_ops


def _fake_post(data: dict[str, dict]):
    def post(query: str, variables: dict) -> dict:
        for name, payload in data.items():
            if f"query {name}" in query:
                return payload
        raise KeyError(query)

    return post


GUIDE_FIXTURE = {
    "FeatureCatalogue": {
        "catalogue": [{"name": "a", "guide": None}, {"name": "b", "guide": {"theme": "t"}}]
    },
    "GuideIndex": {"guideIndex": {"situations": [{"slug": "sit-1"}]}},
    "EdgesPage": {"edges": [{"screeners": []}, {"screeners": ["scr-1", "scr-2"]}]},
    "GuideScreenerIndex": {"guideScreenerIndex": {"categories": [{"id": "cat-1"}]}},
    "HarnessRuns": {"harnessRuns": [{"runId": "run-9"}]},
}


def _op_dicts(*names: str) -> dict[str, dict]:
    return {f"{n}#1": {"name": n, "query": "q", "variables": {"old": 1}} for n in names}


def test_resolvers_pick_a_real_id_for_every_template_from_the_clone() -> None:
    ops = _op_dicts(
        "GuideField",
        "GuideHelpField",
        "GuideSituation",
        "GuideScreener",
        "GuideScreenerEdges",
        "GuideScreenerCategory",
        "HarnessRun",
    )
    assert fb.resolve_variables(_fake_post(GUIDE_FIXTURE), ops) == []
    got = {d["name"]: d["variables"] for d in ops.values()}
    assert got["GuideField"]["name"] == "b" and got["GuideHelpField"]["name"] == "b"  # has a guide
    assert got["GuideSituation"]["slug"] == "sit-1" and got["GuideScreener"]["id"] == "scr-1"
    assert got["GuideScreenerEdges"]["id"] == "scr-1"
    assert got["GuideScreenerCategory"]["id"] == "cat-1"
    assert got["HarnessRun"] == {"old": 1, "runId": "run-9"}  # a stale captured id is replaced


def test_a_template_with_no_resolvable_id_fails_the_gate_not_skipped() -> None:
    empty = {**GUIDE_FIXTURE, "GuideIndex": {"guideIndex": {"situations": [], "families": []}}}
    ops = _op_dicts("GuideSituation", "GuideField")
    assert fb.resolve_variables(_fake_post(empty), ops) == ["GuideSituation"]
    out = _failures(unresolved=["GuideSituation"])
    assert "no real id" in out[0] and "GuideSituation" in out[0]


def test_first_render_defaults_equal_what_the_webs_edge_trades_sends() -> None:
    src = (ROOT / "apps/web/src/widgets/edge-trades/ui/EdgeTrades.tsx").read_text()
    period = re.search(r"useState<TradePeriod>\('(\w+)'\)", src)
    page = re.search(r"const \[page, setPage\] = useState\((\d+)\)", src)
    column = re.search(r"columnId: '(\w+)',\s*direction: '(\w+)'", src)
    assert period and page and column
    columns = (ROOT / "apps/web/src/widgets/edge-trades/model/columns.tsx").read_text()
    sort = re.search(rf"\b{column.group(1)}: '(\w+)'", columns)
    assert sort
    assert {
        "period": period.group(1),
        "page": int(page.group(1)),
        "sort": sort.group(1),
        "descending": column.group(2) == "desc",
    } == fb.FIRST_RENDER


def test_hand_written_web_documents_are_found_with_their_constants_filled() -> None:
    docs = fb.pdocs.hand_written_documents()
    assert "edge(id: $id)" in docs["EdgeCompare"] and "${" not in docs["EdgeCompare"]
    assert "winRate baseRate liftPts trades" in docs["EdgeCompare"]
    assert "edgePaper" in docs["EdgePaper"]


def test_an_operation_failing_in_an_early_pass_is_failed_even_if_the_last_pass_is_fine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = iter([500, 200, 200])

    class FlakyApi:
        url = "http://x"
        last_error = ""

        def __init__(self, *a: object, **k: object) -> None:
            self.client = type("C", (), {"get": staticmethod(lambda url: None)})()

        def call(self, body: dict) -> tuple[float, int, int, int]:
            return 5.0, next(statuses), 1, 1

        def close(self) -> None:
            return None

    monkeypatch.setattr(fb.al, "Api", FlakyApi)
    monkeypatch.setattr(fb.al, "uncached_config", lambda src, dst: dst)
    monkeypatch.setattr(fb.al, "guard", lambda: None)
    monkeypatch.setattr(fb, "wait_quiet", lambda limit, load_max: 1.0)
    ops, _ = fb.time_ops({"A#1": {"name": "A", "query": "q", "variables": {}}}, "file:///c", 3, 4.0)
    assert ops["A#1"]["failed"] is True


def test_a_non_json_or_error_answer_leaves_the_operation_unresolved_not_a_crash() -> None:
    def post(query: str, variables: dict) -> dict:
        raise ValueError("Expecting value")  # r.json() of an HTML error page

    ops = _op_dicts("GuideSituation", "HarnessRun")
    assert fb.resolve_variables(post, ops) == ["GuideSituation", "HarnessRun"]
    assert "GuideSituation" in _failures(unresolved=["GuideSituation"])[0]


@pytest.mark.allow_localhost
def test_every_resolver_picks_an_id_the_real_api_answers_with_content(
    api_golden: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fitness: run every resolver against the real API app (in process) and replay each
    resolved operation: none may answer empty (an entry that is legitimately empty would fail the
    gate every night). HarnessRun is excepted: the fixture store has no harness runs."""
    client = TestClient(
        create_app(ApiSettings("memory://", "config"), api_golden[0], authenticator=as_user())
    )

    def raw(query: str, variables: dict):
        return client.post("/graphql", json={"query": query, "variables": variables})

    def post(query: str, variables: dict) -> dict:
        return raw(query, variables).json()["data"]

    docs = fb.pdocs.web_documents()
    names = sorted(set(fb.VARIABLE_RESOLVERS) - {"HarnessRun"})
    ops = {f"{n}#1": {"name": n, "query": docs[n], "variables": {}} for n in names}
    assert fb.resolve_variables(post, ops) == []
    for d in ops.values():
        r = raw(d["query"], d["variables"])
        assert r.status_code == 200 and fb.al.answer_problem(r.status_code, r.content) is None
        assert fb.al.empty_note(r.status_code, r.content) is None, (d["name"], d["variables"])


@pytest.mark.allow_localhost
def test_edge_compare_is_asked_about_the_viewers_own_edge_and_answers_with_content(
    api_golden: tuple, tmp_path: Path
) -> None:
    """The 2026-10-23 hand run failed integrity on EdgeCompare (answered null): the page asks it
    only for an edge the viewer owns, a site edge answers `compare: null` by design, and the bench
    asked about the capture's site edge. The bench now gives its viewer a copy and asks about it."""
    site = "absolute_momentum_crash_filter"
    cfg = tmp_path / "config"
    shutil.copytree(Path(__file__).resolve().parents[3] / "config", cfg)
    docs = fb.pdocs.web_documents() | fb.pdocs.hand_written_documents()
    query = docs["EdgeCompare"]
    ops = {"EdgeCompare#1": {"name": "EdgeCompare", "query": query, "variables": {"id": site}}}
    fb.point_at_own_edge(ops, cfg)
    assert ops["EdgeCompare#1"]["variables"] == {"id": fb.BENCH_COPY}
    store = dataclasses.replace(api_golden[0], configs=FileConfigStore(cfg, local=False))
    client = TestClient(
        create_app(ApiSettings("memory://", str(cfg)), store, authenticator=as_user(fb.BENCH_USER))
    )
    r = client.post("/graphql", json={"query": docs["EdgeCompare"], "variables": {"id": site}})
    assert fb.al.empty_note(r.status_code, r.content) is not None  # the site edge: null, as shown
    d = ops["EdgeCompare#1"]
    r = client.post("/graphql", json={"query": d["query"], "variables": d["variables"]})
    assert fb.al.answer_problem(r.status_code, r.content) is None
    assert fb.al.empty_note(r.status_code, r.content) is None


def test_time_ops_marks_edge_compare_as_an_own_copy_not_run_and_no_other_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeApi:
        url = "http://x"
        last_error = ""

        def __init__(self, *a: object, **k: object) -> None:
            self.client = type("C", (), {"get": staticmethod(lambda url: None)})()

        def call(self, body: dict) -> tuple[float, int, int, int]:
            return 5.0, 200, 10, 1

        def close(self) -> None:
            return None

    monkeypatch.setattr(fb.al, "Api", FakeApi)
    monkeypatch.setattr(fb.al, "uncached_config", lambda src, dst: dst)
    monkeypatch.setattr(fb.al, "guard", lambda: None)
    monkeypatch.setattr(fb, "wait_quiet", lambda limit, load_max: 1.0)
    ops = {
        "EdgeCompare#1": {"name": "EdgeCompare", "query": "q", "variables": {"id": "e"}},
        "EdgePaper#1": {"name": "EdgePaper", "query": "q", "variables": {"id": "e"}},
    }
    done, _ = fb.time_ops(ops, "file:///c", 1, 4.0)
    assert done["EdgeCompare#1"]["fidelity"] == "own copy, not run"
    assert "fidelity" not in done["EdgePaper#1"]


def test_a_request_stream_leaves_every_request_and_the_progress_after_a_kill(
    tmp_path: Path,
) -> None:
    rs = fb.RequestStream(tmp_path)
    rs.begin("IdeasPage", 2, 1)
    rs.end("IdeasPage", "IdeasPage#1", 2, 1790.0, 1234, 200, 5.7)
    rs.begin("RegimeSignals", 2, 1)  # killed here: no close, no flush call
    lines = [json.loads(x) for x in (tmp_path / "ops-stream.jsonl").read_text().splitlines()]
    assert lines[0]["op"] == "IdeasPage" and lines[0]["ms"] == 1790.0 and lines[0]["load1"] == 5.7
    assert lines[0]["bytes"] == 1234 and lines[0]["status"] == 200 and lines[0]["pass"] == 2
    progress = json.loads((tmp_path / "bench-progress.json").read_text())
    assert progress["op"] == "RegimeSignals" and progress["passes_done"] == 1
    assert progress["requests"] == 1
    rs.close()
