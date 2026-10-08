"""``algotrade-api stamp-web``: the build stamped, and the running API's state said."""

import json
from pathlib import Path

import pytest

from algotrade_api import cli
from algotrade_api.ops.build import STAMP


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
