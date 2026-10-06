"""The API's launchd agent (ADR 0044): written with absolute paths, never installed."""

import json
import plistlib
from pathlib import Path

import pytest

from algotrade_api import cli
from algotrade_api.ops.schedule import LABEL, api_plist


def test_the_agent_serves_on_loopback_and_is_kept_alive() -> None:
    agent = plistlib.loads(api_plist(Path("/repo"), 8000))
    assert agent["Label"] == LABEL
    assert agent["ProgramArguments"] == [
        "/repo/.venv/bin/algotrade-api", "--host", "127.0.0.1", "--port", "8000",
    ]  # fmt: skip
    assert agent["WorkingDirectory"] == "/repo"  # the CLI reads this checkout's .env
    assert agent["RunAtLoad"] is True and agent["KeepAlive"] is True
    assert agent["StandardOutPath"] == "/repo/var/logs/api.log"
    assert agent["StandardErrorPath"] == "/repo/var/logs/api.err.log"


def test_an_invalid_port_is_refused() -> None:
    with pytest.raises(ValueError, match="port"):
        api_plist(Path("/repo"), 0)


def test_schedule_writes_the_agent_and_prints_the_install_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setenv("ALGOTRADE_AUTH", "supabase")
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: pytest.fail("schedule must not serve"))
    cli.main(["schedule", "--port", "8001"])
    plan = json.loads(capsys.readouterr().out)
    written = tmp_path / "var" / f"{LABEL}.plist"
    assert plan["written"] == str(Path("var") / f"{LABEL}.plist") and written.exists()
    agent = plistlib.loads(written.read_bytes())
    assert agent["WorkingDirectory"] == str(tmp_path.resolve())
    assert agent["ProgramArguments"][-1] == "8001"
    assert plan["install"][-1].startswith("launchctl load ")
    assert "note" not in plan


def test_schedule_warns_when_authentication_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setenv("ALGOTRADE_AUTH", "off")
    cli.main(["schedule"])
    assert "ALGOTRADE_AUTH=supabase" in json.loads(capsys.readouterr().out)["note"]
