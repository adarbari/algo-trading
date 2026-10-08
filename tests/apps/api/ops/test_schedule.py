"""The API's launchd agent (ADR 0044): written with absolute paths, never installed."""

import json
import plistlib
from pathlib import Path

import pytest

from algotrade_api import cli
from algotrade_api.ops.schedule import (
    DEPLOY_LABEL,
    LABEL,
    MAX_CONNECTIONS,
    OPEN_FILES,
    api_plist,
    deploy_plist,
)


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


def test_the_agent_lifts_launchds_256_open_files_default() -> None:
    """launchd starts an agent with a soft limit of 256 descriptors; every connection is one,
    so a burst of slow requests ran the API out (``accept()``: EMFILE, 2026-10-08)."""
    agent = plistlib.loads(api_plist(Path("/repo"), 8000))
    for limits in ("SoftResourceLimits", "HardResourceLimits"):
        assert agent[limits] == {"NumberOfFiles": OPEN_FILES}
    assert 256 < OPEN_FILES <= 10240  # macOS refuses a limit above OPEN_MAX (10240)


def test_the_connection_cap_leaves_descriptors_for_the_reads_in_flight() -> None:
    # uvicorn answers 503 past MAX_CONNECTIONS; the descriptors above it serve the store reads
    # (parquet files, index locks) of the requests in flight, and the process's own files
    assert MAX_CONNECTIONS * 4 <= OPEN_FILES


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


def _tools(tmp_path: Path, *names: str) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in names:
        (bin_dir / name).write_text("#!/bin/sh\n")
        (bin_dir / name).chmod(0o755)
    return str(bin_dir)


def test_the_deploy_agent_polls_origin_main_every_five_minutes(tmp_path: Path) -> None:
    path = _tools(tmp_path, "uv", "npm", "git")
    agent = plistlib.loads(deploy_plist(Path("/repo"), path))
    assert agent["Label"] == DEPLOY_LABEL == "com.algotrade.deploy"
    assert agent["ProgramArguments"] == ["/bin/bash", "/repo/scripts/ops/deploy.sh", "--auto"]
    assert agent["StartInterval"] == 300 and agent["RunAtLoad"] is True
    assert agent["WorkingDirectory"] == "/repo"
    assert agent["StandardOutPath"] == agent["StandardErrorPath"] == "/repo/var/logs/deploy.log"
    assert agent["EnvironmentVariables"] == {"PATH": path}
    assert "KeepAlive" not in agent


def test_the_deploy_agent_refuses_a_path_without_the_tools(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="npm"):
        deploy_plist(Path("/repo"), _tools(tmp_path, "uv", "git"))
    with pytest.raises(ValueError, match="interval"):
        deploy_plist(Path("/repo"), _tools(tmp_path, "uv", "npm", "git"), 0)


def test_schedule_agent_deploy_writes_its_own_plist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setenv("PATH", _tools(tmp_path, "uv", "npm", "git"))
    cli.main(["schedule", "--agent", "deploy"])
    plan = json.loads(capsys.readouterr().out)
    assert plan["written"] == str(Path("var") / f"{DEPLOY_LABEL}.plist")
    assert (tmp_path / plan["written"]).exists() and not (
        tmp_path / "var" / f"{LABEL}.plist"
    ).exists()
    assert any(line.startswith("launchctl bootstrap") for line in plan["install"])
