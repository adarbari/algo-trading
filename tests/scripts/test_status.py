"""`scripts/status.py`: the report from fake probes (gh, ps, ports, the store)."""

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

from algotrade.storage.backends.release.interfaces import ReleaseReport

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "status.py"
_spec = importlib.util.spec_from_file_location("status", SCRIPT)
assert _spec and _spec.loader
status = importlib.util.module_from_spec(_spec)
sys.modules["status"] = status
_spec.loader.exec_module(status)

PRS = json.dumps(
    [
        {
            "number": 7,
            "title": "Add x",
            "isDraft": False,
            "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        },
        {
            "number": 8,
            "title": "Fix y",
            "isDraft": True,
            "statusCheckRollup": [{"conclusion": "FAILURE"}],
        },
        {
            "number": 9,
            "title": "Wip z",
            "isDraft": False,
            "statusCheckRollup": [{"status": "IN_PROGRESS"}],
        },
    ]
)
PS = "  1 00:01 /sbin/launchd\n 42 05:10 /bin/zsh /x/var/logs/ibkr-iv-backfill.sh\n"


def probes(tmp_path: Path, **kw: object) -> "status.Probes":
    def run(cmd: list[str]) -> tuple[int, str]:
        return (0, PRS) if cmd[0] == "gh" else (0, PS)

    base: dict[str, object] = {
        "which": lambda n: "/bin/" + n,
        "run": run,
        "port_open": lambda port: port == 8000,
        "store_facts": lambda: ("2026-10-02", "2026-10-02 SUCCESS", "2026-10-02 COMPLETE"),
        "logs": tmp_path,
        "api_build": lambda url: (),
        "serving": lambda: None,
    }
    return status.Probes(**{**base, **kw})


def test_report_is_short_and_covers_every_area(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ALGOTRADE_PORT_BASE", raising=False)
    (tmp_path / "job.status").write_text("chunk 1 exit=0\nchunk 2 exit=0\n")
    text = status.report(probes(tmp_path))
    assert len(text.splitlines()) <= 15
    for want in (
        "#7 Add x [CI green]",
        "#8 Fix y [CI failing draft]",
        "[CI running]",
        "Ingest jobs: 1 running",
        "42 up 05:10",
        "job.status: chunk 2 exit=0",
        "latest session 2026-10-02; last nightly 2026-10-02 SUCCESS; "
        "last post-session 2026-10-02 COMPLETE",
        "8000 api",
        "API build: in step",
    ):
        assert want in text, want
    assert "launchd" not in text


def test_degrades_without_gh_or_store(tmp_path: Path) -> None:
    def boom() -> tuple[str, str, str]:
        raise FileNotFoundError("no store")

    text = status.report(
        probes(
            tmp_path,
            which=lambda n: None,
            store_facts=boom,
            port_open=lambda p: False,
            run=lambda cmd: (0, ""),
        )
    )
    assert "gh not installed" in text
    assert "Store: unreadable (FileNotFoundError" in text
    assert "none listening" in text and "0 running" in text


def test_gh_failure_says_how_to_fix(tmp_path: Path) -> None:
    text = status.report(probes(tmp_path, run=lambda cmd: (1, "")))
    assert "gh auth login" in text


def test_servers_probe_this_worktrees_port_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALGOTRADE_PORT_BASE", "12340")
    assert list(status.ports()) == [12340, 12341, 12346]


def test_an_api_out_of_step_with_its_build_is_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 2026-10-07: an API started before make web-build served a web it could not answer.
    monkeypatch.delenv("ALGOTRADE_PORT_BASE", raising=False)
    stale = ("the web was built against GraphQL schema b, the API serves a; restart the API: x",)
    lines = status.api_build(probes(tmp_path, api_build=lambda url: stale))
    assert lines == ["API build: OUT OF STEP", f"  {stale[0]}"]
    assert status.api_build(probes(tmp_path, port_open=lambda port: False)) == []
    assert "does not answer" in status.api_build(probes(tmp_path, api_build=lambda url: None))[0]


def test_unrecorded_golden_cases_older_than_14_days_are_listed(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    cases.mkdir()
    for name, body in {
        "old": {"recorded": False, "curated": "2026-09-20"},
        "fresh": {"recorded": False, "curated": "2026-10-05"},
        "done": {"curated": "2026-01-01"},
        "undated": {"recorded": False},
    }.items():
        (cases / f"{name}.json").write_text(json.dumps(body))
    p = probes(tmp_path, golden_cases=cases, today=lambda: date(2026, 10, 11))
    lines = status.unrecorded_cases(p)
    assert lines[0].startswith("Golden cases unrecorded > 14 days: 2")
    assert [x.split(":")[0].strip() for x in lines[1:]] == ["old", "undated"]
    assert status.unrecorded_cases(probes(tmp_path, golden_cases=tmp_path / "none")) == []
    assert "Golden cases" in status.report(p)


def test_release_lines_are_silent_without_a_release_tree_and_report_one(tmp_path: Path) -> None:
    def run(cmd: list[str]) -> tuple[int, str]:
        return (0, "2") if "rev-list" in cmd else (0, "abcdef123456")

    p = status.Probes(run=run, repo=tmp_path)
    assert status.release(p) == []
    (tmp_path / "var" / "release" / "blue").mkdir(parents=True)
    (tmp_path / "var" / "release" / "current").symlink_to(tmp_path / "var" / "release" / "blue")
    (tmp_path / "var" / "deploy").mkdir()
    (tmp_path / "var" / "deploy" / "ingest_sync_blocked").write_text("t busy\n")
    text = "\n".join(status.release(p))
    assert "blue abcdef123 (2 behind)" in text and "current ->" in text
    assert "ingest checkout abcdef123 (2 behind" in text and "BLOCKED: t busy" in text


def test_serving_line_names_the_current_release_and_the_pins(tmp_path: Path) -> None:
    report = ReleaseReport("2026-10-02.9.f1", ("2026-10-02.9.f1",), {"release-2026-10-02.9.f1": 9})
    text = status.report(probes(tmp_path, serving=lambda: report))
    assert "Serving: current 2026-10-02.9.f1; 1 releases; pins 2026-10-02.9.f1@9" in text
    assert "Serving" not in status.report(probes(tmp_path))  # no release, no pin: no line


def test_serving_line_degrades_when_the_store_cannot_be_read(tmp_path: Path) -> None:
    def boom() -> None:
        raise FileNotFoundError("no store")

    assert "Serving: unreadable (FileNotFoundError)" in status.report(
        probes(tmp_path, serving=boom)
    )
