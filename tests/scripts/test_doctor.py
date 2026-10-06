"""`scripts/doctor.py`: each check reports ok / FAIL / warn with a fix, using fake probes."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "doctor.py"
_spec = importlib.util.spec_from_file_location("doctor", SCRIPT)
assert _spec and _spec.loader
doctor = importlib.util.module_from_spec(_spec)
sys.modules["doctor"] = doctor
_spec.loader.exec_module(doctor)


def probes(tmp_path: Path, tools: dict[str, str], **kw: object) -> "doctor.Probes":
    def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
        rc, _, out = tools.get(" ".join(cmd[:2]), "0|").partition("|")
        return int(rc), out

    base: dict[str, object] = {
        "repo": tmp_path,
        "which": lambda name: f"/bin/{name}" if name in tools.get("have", "") else None,
        "run": run,
        "port_open": lambda host, port: False,
    }
    return doctor.Probes(**{**base, **kw})


def test_uv_missing_is_a_hard_failure_with_the_install_command(tmp_path: Path) -> None:
    r = doctor.check_uv(probes(tmp_path, {"have": ""}))
    assert r.level == doctor.FAIL and r.fix == "brew install uv"


def test_node_must_be_24(tmp_path: Path) -> None:
    assert (
        doctor.check_node(probes(tmp_path, {"have": "node", "node --version": "0|v24.1.0"})).level
        == "ok"
    )
    bad = doctor.check_node(probes(tmp_path, {"have": "node", "node --version": "0|v20.0.0"}))
    assert bad.level == doctor.FAIL and "node@24" in bad.fix


def test_docker_is_only_a_warning(tmp_path: Path) -> None:
    assert doctor.check_docker(probes(tmp_path, {"have": ""})).level == doctor.WARN
    assert (
        doctor.check_docker(probes(tmp_path, {"have": "docker", "docker info": "1|x"})).level
        == doctor.WARN
    )


def test_gh_auth(tmp_path: Path) -> None:
    assert doctor.check_gh(probes(tmp_path, {"have": "gh", "gh auth": "0|ok"})).level == "ok"
    assert (
        doctor.check_gh(probes(tmp_path, {"have": "gh", "gh auth": "1|no"})).fix == "gh auth login"
    )


def _venv(tmp_path: Path) -> None:
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("")


def test_venv_missing_fails_and_other_python_only_warns(tmp_path: Path) -> None:
    assert doctor.check_venv(probes(tmp_path, {"have": ""}))[0].level == doctor.FAIL
    _venv(tmp_path)
    py = f"{tmp_path}/.venv/bin/python -c"
    out = doctor.check_venv(probes(tmp_path, {"have": "", py: "0|3.13"}))
    assert [r.level for r in out] == [doctor.WARN, doctor.INFO]  # no uv: lock check skipped
    assert "skipped" in out[1].detail


def test_venv_out_of_sync_with_the_lock_fails(tmp_path: Path) -> None:
    _venv(tmp_path)
    py = f"{tmp_path}/.venv/bin/python -c"
    tools = {"have": "uv", py: "0|3.12", "uv sync": "2|stale"}
    out = doctor.check_venv(probes(tmp_path, tools))
    assert out[0].level == "ok" and out[1].level == doctor.FAIL and out[1].fix == "make install"


def _web(tmp_path: Path, want: str, have: str | None) -> None:
    web = tmp_path / "apps" / "web"
    (web / "node_modules").mkdir(parents=True)
    pkg = lambda v: json.dumps({"packages": {"": {}, "node_modules/x": {"version": v}}})  # noqa: E731
    (web / "package-lock.json").write_text(pkg(want))
    if have:
        (web / "node_modules" / ".package-lock.json").write_text(pkg(have))


@pytest.mark.parametrize(("have", "level"), [("1.0.0", "ok"), ("0.9.0", "FAIL"), (None, "FAIL")])
def test_node_modules_match_the_lockfile(tmp_path: Path, have: str | None, level: str) -> None:
    _web(tmp_path, "1.0.0", have)
    r = doctor.check_node_modules(probes(tmp_path, {}))
    assert r.level == level
    if level == "FAIL":
        assert r.fix == "make web-install"


def test_env_reports_names_never_values(tmp_path: Path) -> None:
    p = probes(tmp_path, {}, env_keys=lambda: {"A"}, required=("A", "B_KEY"))
    r = doctor.check_env(p)
    assert r.level == doctor.FAIL and "B_KEY" in r.detail and "A," not in r.detail
    assert (
        doctor.check_env(probes(tmp_path, {}, env_keys=lambda: {"A"}, required=("A",))).level
        == "ok"
    )


def test_ibkr_port_is_info_either_way(tmp_path: Path) -> None:
    assert doctor.check_ibkr(probes(tmp_path, {})).level == doctor.INFO
    assert doctor.check_ibkr(probes(tmp_path, {}, port_open=lambda h, p: True)).level == doctor.INFO


def test_store_path_must_exist(tmp_path: Path) -> None:
    missing = doctor.check_store(probes(tmp_path, {}, data_url=lambda: "file://./var/data"))
    assert missing.level == doctor.FAIL and "ALGOTRADE_DATA_URL" in missing.fix
    (tmp_path / "var" / "data").mkdir(parents=True)
    assert (
        doctor.check_store(probes(tmp_path, {}, data_url=lambda: "file://./var/data")).level == "ok"
    )


def test_exit_code_is_non_zero_only_for_hard_failures() -> None:
    soft = [doctor.Result(doctor.WARN, "a", "x", "fix a"), doctor.Result(doctor.INFO, "b", "y")]
    text, code = doctor.render(soft)
    assert code == 0 and "fix: fix a" in text and text.endswith("ready")
    text, code = doctor.render([*soft, doctor.Result(doctor.FAIL, "c", "z", "do c")])
    assert code == 1 and "fix: do c" in text


def _shared_venv(main: Path, src: Path, python: Path) -> None:
    """A main checkout whose venv's editable install points at ``src`` and whose console
    script runs ``python`` (as uv writes them)."""
    (main / ".git").mkdir(parents=True)
    site = main / ".venv" / "lib" / "python3.12" / "site-packages"
    site.mkdir(parents=True)
    (site / "_editable_impl_algotrade.pth").write_text(str(src))
    (site / "other.pth").write_text("/elsewhere/entirely")  # not ours: never inspected
    bin_ = main / ".venv" / "bin"
    bin_.mkdir()
    (bin_ / "algotrade-ingest").write_text(f"#!{python}\nimport sys\n")
    (bin_ / "activate").write_text("# no shebang\n")


def test_venv_paths_ok_when_everything_points_at_the_main_checkout(tmp_path: Path) -> None:
    main = tmp_path / "algo-trading"
    _shared_venv(main, main / "src", main / ".venv" / "bin" / "python3")
    r = doctor.check_venv_paths(probes(tmp_path, {}, main=lambda: main))
    assert r.level == "ok", r.detail


@pytest.mark.parametrize(
    "where",
    [
        "algo-trading-feat-x",  # scripts/worktree.sh: a sibling of the main checkout
        "algo-trading/.claude/worktrees/agent-abc",  # Claude agent worktrees nest inside it
    ],
)
def test_venv_paths_fail_when_a_worktree_synced_the_shared_venv(tmp_path: Path, where: str) -> None:
    main, wt = tmp_path / "algo-trading", tmp_path / where
    _shared_venv(main, wt / "src", main / ".venv" / "bin" / "python3")
    r = doctor.check_venv_paths(probes(tmp_path, {}, main=lambda: main))
    assert r.level == doctor.FAIL
    assert f"{wt}/src" in r.detail
    assert r.fix == f"cd {main} && uv sync --all-packages --locked"


def test_venv_paths_fail_on_a_script_shebang_into_a_worktree(tmp_path: Path) -> None:
    main = tmp_path / "algo-trading"
    wt = main / ".claude" / "worktrees" / "agent-abc"
    _shared_venv(main, main / "src", wt / ".venv" / "bin" / "python3")
    r = doctor.check_venv_paths(probes(tmp_path, {}, main=lambda: main))
    assert r.level == doctor.FAIL and "bin/algotrade-ingest" in r.detail


def test_venv_paths_see_uvs_exec_trampoline_for_long_paths(tmp_path: Path) -> None:
    main, wt = tmp_path / "algo-trading", tmp_path / "algo-trading-feat-x"
    _shared_venv(main, main / "src", main / ".venv" / "bin" / "python3")
    (main / ".venv" / "bin" / "algotrade-api").write_text(
        f"#!/bin/sh\n'''exec' \"{wt}/.venv/bin/python3\" \"$0\" \"$@\"\n' '''\n"
    )
    r = doctor.check_venv_paths(probes(tmp_path, {}, main=lambda: main))
    assert r.level == doctor.FAIL and "bin/algotrade-api" in r.detail


def test_venv_paths_fail_under_a_nested_checkout_with_its_own_git(tmp_path: Path) -> None:
    main = tmp_path / "algo-trading"
    nested = main / "elsewhere" / "wt"
    _shared_venv(main, nested / "src", main / ".venv" / "bin" / "python3")
    (nested / "src").mkdir(parents=True)
    (nested / ".git").write_text("gitdir: ../../.git/worktrees/wt\n")
    r = doctor.check_venv_paths(probes(tmp_path, {}, main=lambda: main))
    assert r.level == doctor.FAIL


def test_main_checkout_comes_from_the_git_common_dir(tmp_path: Path) -> None:
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", str(main)], check=True)
    assert doctor._main_checkout(main) == main.resolve()
    assert doctor._main_checkout(tmp_path / "nowhere") == tmp_path / "nowhere"


def test_web_build_is_checked_only_when_set(tmp_path: Path) -> None:
    unset = doctor.check_web_dist(probes(tmp_path, {}))
    assert unset.level == doctor.INFO
    missing = doctor.check_web_dist(probes(tmp_path, {}, web_dist=lambda: Path("var/web")))
    assert missing.level == doctor.FAIL and "make web-build" in missing.fix
    (tmp_path / "var" / "web").mkdir(parents=True)
    (tmp_path / "var" / "web" / "index.html").write_text("<!doctype html>")
    found = doctor.check_web_dist(probes(tmp_path, {}, web_dist=lambda: Path("var/web")))
    assert found.level == "ok"


def test_a_wrong_llm_toml_is_a_warning_with_the_message(tmp_path: Path) -> None:
    ok = doctor.check_llm(probes(tmp_path, {}, main=lambda: tmp_path))
    assert ok.level == "ok"
    bad = doctor.check_llm(
        probes(
            tmp_path,
            {},
            main=lambda: tmp_path,
            llm_error=lambda main: "llm.toml: unknown keys ['request_']",
        )
    )
    assert bad.level == doctor.WARN and "unknown keys" in bad.detail and "llm.toml" in bad.fix


def test_llm_error_reads_the_main_checkouts_file(tmp_path: Path) -> None:
    assert doctor.llm_error(tmp_path) is None  # no file: drafting is simply off
    site = tmp_path / "config" / "site"
    site.mkdir(parents=True)
    (site / "llm.toml").write_text('enabled = false\n[request]\nreasoning_effort = "low"\n')
    assert doctor.llm_error(tmp_path) is None
    (site / "llm.toml").write_text("[request]\nmodel = 'x'\n")
    assert "the adapter sets" in (doctor.llm_error(tmp_path) or "")
    (site / "llm.toml").write_text("enabled = \n")
    assert "llm.toml" in (doctor.llm_error(tmp_path) or "")


def _agent(agents: Path, label: str, repo: Path, program: str) -> None:
    agents.mkdir(exist_ok=True)
    plist = {"Label": label, "ProgramArguments": [program], "WorkingDirectory": str(repo)}
    (agents / f"{label}.plist").write_bytes(doctor.plistlib.dumps(plist))


def test_installed_agents_must_run_the_main_checkout(tmp_path: Path) -> None:
    main, agents = tmp_path / "main", tmp_path / "LaunchAgents"
    (main / ".venv" / "bin").mkdir(parents=True)
    (main / ".venv" / "bin" / "algotrade-api").write_text("#!/bin/sh\n")
    p = probes(tmp_path, {}, main=lambda: main, launch_agents=agents)
    assert [r.level for r in doctor.check_agents(p)] == [doctor.INFO, doctor.INFO]
    _agent(agents, "com.algotrade.api", main, str(main / ".venv" / "bin" / "algotrade-api"))
    api = doctor.check_agents(p)[1]
    assert (api.name, api.level) == ("com.algotrade.api", "ok")
    worktree = main / ".claude" / "worktrees" / "wt"
    _agent(agents, "com.algotrade.api", worktree, str(worktree / ".venv" / "bin" / "algotrade-api"))
    bad = doctor.check_agents(p)[1]
    assert bad.level == doctor.FAIL and "algotrade-api schedule" in bad.fix
    (agents / "com.algotrade.nightly.plist").write_bytes(b"not a plist")
    assert doctor.check_agents(p)[0].level == doctor.FAIL


def test_low_disk_only_warns_and_points_at_the_prune(tmp_path: Path) -> None:
    low = probes(tmp_path, {}, main=lambda: tmp_path, free_bytes=lambda path: 5 * 10**9)
    r = doctor.check_disk(low)
    assert r.level == doctor.WARN and "--prune-merged" in r.fix
    ok = probes(tmp_path, {}, main=lambda: tmp_path, free_bytes=lambda path: 50 * 10**9)
    assert doctor.check_disk(ok).level == "ok"


def _worktrees(tmp_path: Path, rc: int, merged: int) -> "doctor.Result":
    lines = [f"would remove /w/algo-trading-{i} (feat/{i})" for i in range(merged)]
    lines += [
        "kept /w/algo-trading-open (feat/open): open PR",
        f"would remove {merged} worktree(s)",
    ]
    return doctor.check_worktrees(
        probes(
            tmp_path, {}, main=lambda: tmp_path, run=lambda cmd, cwd=None: (rc, "\n".join(lines))
        )
    )


def test_many_merged_worktrees_warn_with_the_prune_fix(tmp_path: Path) -> None:
    assert _worktrees(tmp_path, 0, 10).level == "ok"
    r = _worktrees(tmp_path, 0, 11)
    assert r.level == doctor.WARN and "11 worktrees" in r.detail
    assert r.fix.endswith("scripts/worktree.sh --prune-merged")


def test_worktree_check_is_skipped_without_gh(tmp_path: Path) -> None:
    assert _worktrees(tmp_path, 1, 50).level == doctor.INFO
