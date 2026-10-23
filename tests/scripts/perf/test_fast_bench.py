"""`scripts/perf/fast_bench.py`: the bar file is valid, the recorded history parses, the rule
judges critical paths, exceptions and the shell, and the tool refuses the real store (no server)."""

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "perf"))
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
    "exception": [{"operation": "Slow", "reason": "r", "date": "2026-10-22"}],
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
    names = [e["operation"] for e in bar["exception"]]
    assert len(names) == len(set(names))
    assert "InstrumentEvents" not in names  # withdrawn after the option F re-measure
    for e in bar["exception"]:
        assert e["operation"] and e["reason"].strip()
        date.fromisoformat(e["date"])


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
    ops = fb.time_ops(
        {"A#1": {"name": "A", "query": "q", "variables": {}}}, "file:///c", 2, 4.0, partial
    )
    dumped = json.loads(partial.read_text())
    assert dumped["samples"] == {"A#1": [12.0, 12.0]} and dumped["names"] == {"A#1": "A"}
    assert ops["A#1"]["avg"] == 12.0 and not ops["A#1"]["noisy"] and not ops["A#1"]["failed"]
