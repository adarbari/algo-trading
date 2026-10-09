"""The deploy cycle's decisions (ADR 0057): the path-to-action mapping and the verify poll."""

import json
import subprocess
import tomllib
from pathlib import Path

import pytest

from algotrade_api import cli
from algotrade_api.ops.deploy import (
    PLIST_WRITERS,
    Action,
    actions,
    verify,
)
from tests.conftest import REPO_ROOT

S, W, R, P = Action.SYNC, Action.WEB, Action.RESTART, Action.PLISTS


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["uv.lock"], [S, R]),
        (["apps/api/pyproject.toml"], [S, R]),
        (["libs/sources/pyproject.toml"], [S, R]),
        ([".python-version"], [S, R]),
        (["apps/web/src/app/x.tsx"], [W]),
        (["apps/web/package-lock.json"], [W]),
        (["Makefile"], [W]),
        (["apps/api/schema.graphql"], [W, R]),
        (["apps/api/algotrade_api/app.py"], [R]),
        (["src/algotrade/core/x.py"], [R]),
        (["libs/sources/algotrade_sources/x.py"], [R]),
        (["config/site/sources.toml"], [R]),
        (["apps/ingestion/algotrade_ingestion/tasks/x.py"], []),
        (["docs/roadmap.md", "tests/unit/x.py", "config/users/a.toml"], []),
        (["apps/ingestion/algotrade_ingestion/ops/schedule.py"], [P]),
        (["apps/api/algotrade_api/ops/schedule.py"], [R, P]),
        (["apps/web/a.ts", "src/a.py", "uv.lock", "docs/x.md"], [S, W, R]),
        ([], []),
    ],
)
def test_what_a_change_needs(paths: list[str], expected: list[Action]) -> None:
    assert actions(paths) == expected


def test_the_deploy_cycle_is_owned_by_the_api_module_and_the_ingestion_hold() -> None:
    owners = tomllib.loads((REPO_ROOT / "architecture" / "api_ownership.toml").read_text())
    (cycle,) = [r for r in owners["responsibility"] if r["id"] == "deploy-cycle"]
    assert set(cycle["owner"]) == {
        "apps/api/algotrade_api/ops/deploy.py",
        "apps/ingestion/algotrade_ingestion/ops/hold.py",
    }


def test_the_plist_writers_are_the_launchd_agents_owners() -> None:
    owners = tomllib.loads((REPO_ROOT / "architecture" / "ingestion_ownership.toml").read_text())
    (agents,) = [r for r in owners["responsibility"] if r["id"] == "launchd-agents"]
    assert set(PLIST_WRITERS) == set(agents["owner"])


def _health(api: str, web: str | None, mismatches: tuple[str, ...] = ()) -> bytes:
    stamp = lambda sha: {"git_sha": sha, "schema_hash": "h", "at": None}  # noqa: E731
    build = {
        "api": stamp(api),
        "web": stamp(web) if web else None,
        "checkout": stamp(api),
        "stale": bool(mismatches),
        "mismatches": list(mismatches),
    }
    return json.dumps({"status": "ok", "build": build}).encode()


def test_verify_retries_until_the_api_answers() -> None:
    answers = [OSError("down"), OSError("down"), _health("abc1234", "abc1234")]
    waits: list[float] = []

    def fetch(url: str) -> bytes:
        got = answers[0] if len(answers) == 1 else answers.pop(0)
        if isinstance(got, OSError):
            raise got
        return got

    assert verify("http://x", "abc1234", fetch, "web", tries=5, sleep=waits.append) == []
    assert len(waits) == 2


def test_verify_fails_after_its_tries_naming_what_is_wrong() -> None:
    sha = "b" * 40
    fetch = lambda url: _health("a" * 40, "a" * 40, ("restart the API",))  # noqa: E731
    out = verify("http://x", sha, fetch, "web", tries=3, sleep=lambda s: None)
    assert "restart the API" in out
    assert any("api is at commit aaaaaaaaa, expected bbbbbbbbb" in line for line in out)
    assert any(line.startswith("the web is at") for line in out)


def test_verify_says_so_when_nothing_answers() -> None:
    def down(url: str) -> bytes:
        raise OSError("refused")

    assert verify("http://x", "abc", down, tries=2, sleep=lambda s: None) == [
        "no API answering at http://x"
    ]


def test_the_checks_ask_for_more_of_the_site() -> None:
    old_web = lambda url: _health("new", "old", ("web differs",))  # noqa: E731
    none = lambda s: None  # noqa: E731
    assert verify("http://x", "new", old_web, "api", tries=1, sleep=none) == []
    assert verify("http://x", "new", old_web, "full", tries=1, sleep=none) == ["web differs"]
    assert len(verify("http://x", "new", old_web, "web", tries=1, sleep=none)) == 2
    with pytest.raises(ValueError, match="check"):
        verify("http://x", "new", old_web, "bogus")


# ---- the CLI the script calls ---------------------------------------------------------------


def _commit(repo: Path, rel: str) -> str:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(rel)
    ident = ["-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), *ident, "commit", "-qm", rel], check=True)
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def test_deploy_plan_prints_the_actions_between_two_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    first = _commit(tmp_path, "README")
    second = _commit(tmp_path, "apps/web/src/a.ts")
    third = _commit(tmp_path, "src/algotrade/a.py")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    cli.main(["deploy-plan", "--since", first, "--to", third])
    assert capsys.readouterr().out.split() == ["web", "restart"]
    cli.main(["deploy-plan", "--since", second, "--to", third])
    assert capsys.readouterr().out.split() == ["restart"]
    cli.main(["deploy-plan", "--since", third, "--to", third])
    assert capsys.readouterr().out.strip() == ""


def test_deploy_verify_exits_one_with_the_problems(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "verify", lambda *a, **k: ["no API answering at http://x"])
    with pytest.raises(SystemExit) as done:
        cli.main(["deploy-verify", "--expect", "abc", "--check", "api"])
    assert done.value.code == 1 and "no API answering" in capsys.readouterr().out
