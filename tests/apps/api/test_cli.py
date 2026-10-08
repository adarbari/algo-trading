"""``algotrade-api``: the open-files limit it serves with; ``stamp-web``: the build stamped, and
the running API's state said."""

import json
import resource
from pathlib import Path

import pytest

from algotrade_api import cli
from algotrade_api.ops.build import STAMP
from algotrade_api.ops.schedule import OPEN_FILES


def test_stamp_web_stamps_the_build_and_warns_when_the_api_is_behind(tmp_path: Path) -> None:
    stale = {"build": {"mismatches": ["restart the API: launchctl kickstart -k x"]}}
    lines = cli.stamp_web(tmp_path, 8000, lambda url: json.dumps(stale).encode())
    assert (tmp_path / STAMP).is_file() and lines[0].startswith(f"stamped {tmp_path}")
    assert lines[1:] == [
        "WARNING: the API at http://127.0.0.1:8000 is out of step:",
        "  - restart the API: launchctl kickstart -k x",
    ]
    in_step = cli.stamp_web(tmp_path, 8000, lambda url: b'{"build": {"mismatches": []}}')
    assert "serves this build" in in_step[-1]


def test_stamp_web_without_an_api_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def refused(url: str) -> bytes:
        raise ConnectionRefusedError

    assert cli.stamp_web(tmp_path, 8123, refused)[-1] == "no API answering at http://127.0.0.1:8123"


def _limits(monkeypatch: pytest.MonkeyPatch, soft: int, hard: int) -> list[tuple[int, int]]:
    """Stub the process's open-files limits at ``(soft, hard)``; the limits set, recorded."""
    set_to: list[tuple[int, int]] = []
    monkeypatch.setattr(cli.resource, "getrlimit", lambda kind: (soft, hard))
    monkeypatch.setattr(cli.resource, "setrlimit", lambda kind, limits: set_to.append(limits))
    return set_to


def test_serving_lifts_launchds_256_open_files_soft_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # the agent installed before its plist set NumberOfFiles still starts at 256 (2026-10-08)
    set_to = _limits(monkeypatch, 256, resource.RLIM_INFINITY)
    assert cli.raise_open_files() == OPEN_FILES
    assert set_to == [(OPEN_FILES, resource.RLIM_INFINITY)]


def test_the_open_files_limit_stays_within_the_hard_limit_and_is_never_lowered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_to = _limits(monkeypatch, 256, 1024)
    assert cli.raise_open_files() == 1024 and set_to == [(1024, 1024)]
    set_to = _limits(monkeypatch, 65536, resource.RLIM_INFINITY)
    assert cli.raise_open_files() == 65536 and set_to == []


def test_serving_raises_the_limit_before_uvicorn_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "raise_open_files", lambda: order.append("limit") or OPEN_FILES)
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: order.append("serve"))
    cli.main([])
    assert order == ["limit", "serve"]
