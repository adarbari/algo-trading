"""`scripts/status.py`: the report from fake probes (gh, ps, ports, the store)."""

import importlib.util
import json
import sys
from pathlib import Path

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
        "store_facts": lambda: ("2026-10-02", "2026-10-02 SUCCESS"),
        "logs": tmp_path,
    }
    return status.Probes(**{**base, **kw})


def test_report_is_short_and_covers_every_area(tmp_path: Path) -> None:
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
        "latest session 2026-10-02; last nightly 2026-10-02 SUCCESS",
        "8000 api",
    ):
        assert want in text, want
    assert "launchd" not in text


def test_degrades_without_gh_or_store(tmp_path: Path) -> None:
    def boom() -> tuple[str, str]:
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
