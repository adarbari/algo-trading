"""`scripts/perf/fast_bench.py`: the bar file is valid, the recorded history parses, the rule
judges critical paths, exceptions and the shell, and the tool refuses the real store (no server)."""

import importlib.util
import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

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
        assert date.fromisoformat(e["expiry"]) >= today, f"{e['operation']}: expired, remove it"


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


def test_a_loaded_run_stops_early_when_the_next_pass_would_overrun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ops, meta = _run_budget(monkeypatch, tmp_path, 10.0, 5, 70)  # a pass = 20 s
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
