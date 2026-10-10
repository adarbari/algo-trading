"""`scripts/ops/guard_waive.py`: the PreToolUse hook refuses `algotrade-ingest ... --waive`.
Fed sample hook JSON on stdin."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "guard_waive.py"


def _run(command: str) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, str(SCRIPT)], input=payload, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(
    "command",
    [
        "algotrade-ingest nightly --date 2026-10-09 --waive chains --reason x",
        ".venv/bin/algotrade-ingest nightly --date D --reason x --waive chains",
        "/Users/a/algo-trading/.venv/bin/algotrade-ingest nightly --waive=chains",
        "uv run algotrade-ingest nightly --date D --waive chains --reason x",
        "python -m algotrade_ingestion nightly --date D --waive chains --reason x",
        "env PYTHONPATH=x nohup algotrade-ingest nightly --date D --waive chains --reason x &",
        "sh -c 'algotrade-ingest nightly --date D --waive chains --reason x'",
        'bash -lc "cd x && nohup .venv/bin/algotrade-ingest nightly --waive chains"',
        "echo hi; algotrade-ingest nightly --date D --waive chains --reason x",
    ],
)
def test_waive_is_blocked(command: str) -> None:
    result = _run(command)
    assert result.returncode == 2
    assert "owner" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "algotrade-ingest nightly --date 2026-10-09",
        "algotrade-ingest nightly --force",
        "uv run algotrade-ingest report --date D",
        "git commit -m 'only the owner passes algotrade-ingest --waive'",
        "grep -rn -- --waive docs",
        "sh -c 'echo --waive'",
        "echo 'unterminated",
    ],
)
def test_other_commands_pass(command: str) -> None:
    result = _run(command)
    assert result.returncode == 0
    assert result.stderr == ""


def test_bad_json_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], input="not json", capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
