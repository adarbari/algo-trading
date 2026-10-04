"""`scripts/doctor.py`: each check reports ok / FAIL / warn with a fix, using fake probes."""

import importlib.util
import json
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
