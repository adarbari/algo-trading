"""`scripts/session_friction.py`: the friction report from a synthetic transcript folder."""

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "session_friction.py"
_spec = importlib.util.spec_from_file_location("session_friction", SCRIPT)
assert _spec and _spec.loader
friction = importlib.util.module_from_spec(_spec)
sys.modules["session_friction"] = friction
_spec.loader.exec_module(friction)

SINCE = date(2026, 10, 1)
BLOCKED = "<tool_use_error>Blocked: sleep 30 followed by: tail -5 /tmp/check.log</tool_use_error>"
PYTEST_FAIL = "FAILED tests/unit/x.py::test_a - assert 1 == 2\nExit code 1"
UNREAD = "<tool_use_error>File has not been read yet.</tool_use_error>"
OLD_USAGE = {"claude-fable-5-1": {"costUSD": 1.0}}
USAGE = {"claude-fable-5-1": {"costUSD": 30.0}, "claude-sonnet-5-5": {"costUSD": 10.0}}


def _use(tool: str, uid: str, **inp: object) -> dict[str, object]:
    return {"type": "tool_use", "id": uid, "name": tool, "input": inp}


def _result(uid: str, text: str, *, error: bool = False) -> dict[str, object]:
    block: dict[str, object] = {"type": "tool_result", "tool_use_id": uid, "content": text}
    if error:
        block["is_error"] = True
    return block


def _rec(kind: str, content: object, ts: str = "2026-10-06T10:00:00.000Z") -> dict[str, object]:
    message: dict[str, object] = {"role": kind, "content": content}
    if kind == "assistant":
        message["model"] = "claude-fable-5-1"
    return {"type": kind, "timestamp": ts, "message": message}


def _write(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def projects(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    main: list[dict[str, object]] = [
        _rec("user", "no, don't do that; use the Read tool instead"),
        _rec("user", "older correction: never mind", ts="2026-09-20T10:00:00.000Z"),
        _rec("assistant", [_use("Bash", "t1", command="make check WORKERS=2")]),
        _rec("user", [_result("t1", "FAILED tests/unit/x.py::test_a\nExit code 2")]),
        _rec("assistant", [_use("Bash", "t2", command="sleep 30; tail -5 /tmp/check.log")]),
        _rec("user", [_result("t2", BLOCKED, error=True)]),
        _rec("assistant", [_use("Bash", "t3", command="make check WORKERS=2")]),
        _rec("user", [_result("t3", "all green")]),
        {"type": "pr-link", "timestamp": "2026-10-06T11:00:00.000Z", "prNumber": 7},
        {"type": "custom-title", "timestamp": "2026-10-06T11:00:00Z", "customTitle": "Fix x"},
        {"type": "assistant", "timestamp": "2026-10-06T11:00:00Z", "modelUsage": OLD_USAGE},
        {"type": "assistant", "timestamp": "2026-10-06T11:00:01Z", "modelUsage": USAGE},
        {"type": "system", "timestamp": "2026-10-06T11:01:00Z", "toolDenialKind": "user-rejected"},
    ]
    _write(root / "abcdef12-0000.jsonl", main)
    agent = [
        _rec("user", "In a worktree, never uv sync; run the tests"),
        _rec("assistant", [_use("Bash", "a1", command="pytest tests/unit/x.py -q")]),
        _rec("user", [_result("a1", PYTEST_FAIL)]),
        _rec("assistant", [_use("Bash", "a2", command="pytest tests/unit/x.py -q")]),
        _rec("user", [_result("a2", PYTEST_FAIL)]),
        _rec("assistant", [_use("Edit", "a3", file_path="/x.py")]),
        _rec("user", [_result("a3", UNREAD, error=True)]),
    ]
    _write(root / "abcdef12-0000" / "subagents" / "agent-a1.jsonl", agent)
    (root / "memory").mkdir()
    return root


def test_scan_counts_gates_signals_and_corrections(tmp_path: Path) -> None:
    report = friction.scan(projects(tmp_path), SINCE)

    assert report.files == 2
    assert report.gate_runs["make check"] == 2 and report.gate_fails["make check"] == 1
    assert report.gate_runs["pytest"] == 2 and report.gate_fails["pytest"] == 2
    keys = {(s.kind, s.key) for s in report.ranked()}
    assert ("blocked tool call", "Blocked: sleep N followed by: tail -N <path>") in keys
    assert ("retried failing command", "pytest tests/unit/x.py -q") in keys
    assert ("permission denial", "user-rejected") in keys
    assert ("Edit error", "File has not been read yet.") in keys
    gate = report.signals[("gate failure", "make check")]
    assert gate.example == "FAILED tests/unit/x.py::test_a"
    # The owner's correction, never the brief given to an agent, never one before `since`.
    assert report.corrections == [("abcdef12", "no, don't do that; use the Read tool instead")]
    assert report.sessions["abcdef12"].prs == {7} and not report.sessions["abcdef12"].agent
    assert report.sessions["agent-a1"].agent


def test_ranking_is_count_times_sessions() -> None:
    report = friction.Report(since=SINCE)
    for _ in range(3):
        report.note("gate failure", "pytest", "s1")
    report.note("blocked tool call", "sleep", "s1")
    report.note("blocked tool call", "sleep", "s2")
    ranked = report.ranked()
    assert [s.key for s in ranked] == ["sleep", "pytest"]
    assert ranked[0].score == 4 and ranked[1].score == 3


def test_render_and_write(tmp_path: Path) -> None:
    report = friction.scan(projects(tmp_path), SINCE)
    text = friction.render(report, top=5)
    assert "1 sessions, 1 subagents, 1 PRs linked" in text
    assert "Full `make check` runs: 2 (2.0 per PR" in text
    assert "| `make check` | 2 | 1 |" in text
    assert "- `abcdef12`: no, don't do that" in text
    md, js = friction.write(report, tmp_path / "out", top=5)
    assert md.read_text(encoding="utf-8") == text
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["gate_fails"]["pytest"] == 2
    assert payload["sessions"]["abcdef12"]["prs"] == [7]
    assert payload["signals"][0]["score"] >= payload["signals"][-1]["score"]


def test_main_prints_the_summary_and_names_the_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    argv = ["--projects", str(projects(tmp_path)), "--out", str(out), "--since", "2026-10-01"]
    assert friction.main(argv) == 0
    printed = capsys.readouterr().out
    assert "## Top 15 signals" in printed and "## Owner corrections" not in printed
    assert "1 owner corrections" in printed and str(out) in printed
    assert list(out.glob("*.md")) and list(out.glob("*.json"))


def test_main_without_transcripts_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert friction.main(["--projects", str(tmp_path / "none")]) == 1
    assert "no transcripts" in capsys.readouterr().err


def test_project_dir_is_the_main_checkout_slug(tmp_path: Path) -> None:
    repo = tmp_path / "my-repo"
    repo.mkdir()
    assert friction.project_dir(repo).name == str(repo.resolve()).replace("/", "-")
    assert friction.project_dir(repo).parent == Path.home() / ".claude" / "projects"


def test_spend_takes_the_last_usage_snapshot_and_flags_expensive_work_item_sessions(
    tmp_path: Path,
) -> None:
    report = friction.scan(projects(tmp_path), SINCE)
    session = report.sessions["abcdef12"]
    assert session.title == "Fix x"
    assert session.cost == {"fable": 30.0, "sonnet": 10.0} and session.total_cost == 40.0
    text = friction.render(report, top=5)
    assert "| fable | $30.00 | 75% |" in text and "| all | $40.00 | |" in text
    assert "- 2026-10-06 Fix x: $40.00 (fable $30, sonnet $10), PRs 7" in text
    assert (
        friction._tier("claude-opus-5-5") == "opus"
        and friction._tier("<synthetic>") == "<synthetic>"
    )


def test_a_sonnet_run_work_item_is_not_flagged(tmp_path: Path) -> None:
    report = friction.Report(since=SINCE)
    report.sessions["s"] = friction.Session(
        agent=False, prs={1}, start="2026-10-06", title="T", cost={"sonnet": 9.0, "opus": 1.0}
    )
    assert "- none" in "\n".join(friction.spend_lines(report))
