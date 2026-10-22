"""`scripts/perf/release_writer_run.py`: every guard, the dry-run plan, the path checks, the
port choice, the config override and the verdicts (subprocess, copy and API calls are fakes)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "perf" / "release_writer_run.py"
_spec = importlib.util.spec_from_file_location("perf_release_writer_run", SCRIPT)
assert _spec and _spec.loader
rw = importlib.util.module_from_spec(_spec)
sys.modules["perf_release_writer_run"] = rw
_spec.loader.exec_module(rw)


def _done(code=0, out=""):
    return subprocess.CompletedProcess([], code, stdout=out, stderr="")


class FakeProc:
    def __init__(self):
        self.terminated = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def _tools(tmp_path, apfs=True, free_gb=500, device=1, port_free=True, calls=None, procs=None):
    calls = calls if calls is not None else []
    procs = procs if procs is not None else []

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[0] == "diskutil":
            return _done(0, "Type (Bundle): apfs" if apfs else "Type (Bundle): hfs")
        return _done(0, "written var/perf/x.json\n" if "load.py" in cmd[1] else "")

    def popen(cmd, **kw):
        calls.append(cmd)
        procs.append(FakeProc())
        return procs[-1]

    return (
        rw.Tools(
            run=run,
            popen=popen,
            healthy=lambda p: True,
            sleep=lambda s: None,
            is_free=lambda p: port_free,
            usage=lambda p: SimpleNamespace(free=free_gb * 1e9),
            device=lambda p: device,
            env={"ALGOTRADE_PORT_BASE": "12180"},
            log=lambda m: None,
        ),
        calls,
        procs,
    )


@pytest.fixture
def store(tmp_path):
    src = tmp_path / "real" / "data"
    src.mkdir(parents=True)
    return src


def _argv(store, dest, *extra):
    return ["--dest", str(dest), "--source-url", f"file://{store}", *extra]


def test_file_path_refuses_non_file_scheme():
    with pytest.raises(rw.RefusalError):
        rw.file_path("memory://")


def test_dest_inside_store_refused(store):
    with pytest.raises(rw.RefusalError):
        rw.check_paths(store / "clone", store, store / "clone" / "data", repo=Path("/nowhere"))


def test_dest_containing_store_refused(store):
    with pytest.raises(rw.RefusalError):
        rw.check_paths(store.parent, store, store.parent / "data", repo=Path("/nowhere"))


def test_dest_in_repo_or_var_refused(tmp_path, store):
    repo = tmp_path / "repo"
    (repo / "var").mkdir(parents=True)
    with pytest.raises(rw.RefusalError):
        rw.check_paths(repo / "scratch", store, repo / "scratch" / "data", repo=repo)
    var = tmp_path / "other" / "var"
    var.mkdir(parents=True)
    realvar = var / "data"
    realvar.mkdir()
    with pytest.raises(rw.RefusalError):
        rw.check_paths(var / "clone", realvar, var / "clone" / "data", repo=repo)


def test_clone_must_be_inside_dest_and_not_the_store(tmp_path, store):
    dest = tmp_path / "dest"
    with pytest.raises(rw.RefusalError):
        rw.check_paths(dest, store, store, repo=Path("/nowhere"))
    with pytest.raises(rw.RefusalError):
        rw.check_paths(dest, store, tmp_path / "elsewhere", repo=Path("/nowhere"))


def test_nonempty_dest_refused(tmp_path, store):
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "x").write_text("1")
    with pytest.raises(rw.RefusalError):
        rw.check_paths(dest, store, dest / "data", repo=Path("/nowhere"))


def test_good_paths_pass(tmp_path, store):
    rw.check_paths(tmp_path / "dest", store, tmp_path / "dest" / "data", repo=Path("/nowhere"))


def test_spare_port_from_base():
    assert rw.spare_port({"ALGOTRADE_PORT_BASE": "12180"}, lambda p: True) == 12187


def test_spare_port_refusals():
    with pytest.raises(rw.RefusalError, match="PORT_BASE"):
        rw.spare_port({}, lambda p: True)
    with pytest.raises(rw.RefusalError, match="in use"):
        rw.spare_port({"ALGOTRADE_PORT_BASE": "12180"}, lambda p: False)


def test_clone_refusals(tmp_path, store):
    t, *_ = _tools(tmp_path, apfs=False)
    with pytest.raises(rw.RefusalError, match="APFS"):
        rw.check_clone_possible(store, tmp_path, 20, t.run, t.usage, t.device)
    t, *_ = _tools(tmp_path, free_gb=5)
    with pytest.raises(rw.RefusalError, match="free space"):
        rw.check_clone_possible(store, tmp_path, 20, t.run, t.usage, t.device)
    t, *_ = _tools(tmp_path)
    with pytest.raises(rw.RefusalError, match="volume"):
        rw.check_clone_possible(
            store, tmp_path, 20, t.run, t.usage, lambda p: p.stat().st_ino + id(p)
        )


def test_config_copy_sets_release_reads_and_leaves_the_source(tmp_path):
    src = tmp_path / "config"
    (src / "site").mkdir(parents=True)
    original = "[serving]\nrelease_reads = true   # x\nother = 1\n"
    (src / "site" / "nightly.toml").write_text(original)
    out = rw.config_copy(src, tmp_path / "off", False)
    assert "release_reads = false   # x" in (out / "site" / "nightly.toml").read_text()
    assert (src / "site" / "nightly.toml").read_text() == original
    (src / "site" / "nightly.toml").write_text("[serving]\n")
    with pytest.raises(rw.RefusalError):
        rw.config_copy(src, tmp_path / "bad", True)


def _report(p95, health):
    return {"levels": [{"pages": {"a": {"p95": p95}}, "health": {"p99": health}, "pass": True}]}


def test_judge_triggers():
    v = rw.judge(
        {
            "w": _report(2.5, 0.249),
            "w2": _report(2.6, 0.1),
            "w3": _report(1, 0.25),
            "cold": _report(1.0, 9),
            "cold2": _report(1.1, 0),
        }
    )
    assert v["w"]["pass"] and not v["w2"]["pass"] and not v["w3"]["pass"]
    assert v["cold"]["pass"] and not v["cold2"]["pass"]
    assert "FAIL" in rw.render_markdown(
        {"when": "t", "clone": "c", "port": 1, "verdicts": v, "pass": False}
    )


def test_dry_run_prints_plan_and_changes_nothing(tmp_path, store, capsys):
    t, calls, _ = _tools(tmp_path)
    lines = []
    t.log = lines.append
    dest = tmp_path / "dest"
    assert rw.main(_argv(store, dest, "--dry-run"), t) == 0
    assert not dest.exists()
    assert any("cp -c -R" in line for line in lines) and any("12187" in line for line in lines)
    assert all(c[0] == "diskutil" for c in calls)


def test_refuses_without_confirm_paused(tmp_path, store, capsys):
    t, _calls, _ = _tools(tmp_path)
    assert rw.main(_argv(store, tmp_path / "dest"), t) == 2
    assert "--confirm-paused" in capsys.readouterr().err
    assert not (tmp_path / "dest").exists()


def test_refuses_dest_in_store(tmp_path, store, capsys):
    t, *_ = _tools(tmp_path)
    assert rw.main(_argv(store, store / "x", "--confirm-paused"), t) == 2


def test_full_run_with_fakes_stops_every_api(tmp_path, store, monkeypatch):
    report = tmp_path / "var-perf.json"
    report.write_text(json.dumps(_report(0.5, 0.01)))
    monkeypatch.setattr(rw, "REPO", tmp_path)
    (tmp_path / "config" / "site").mkdir(parents=True)
    (tmp_path / "config" / "site" / "nightly.toml").write_text("release_reads = true\n")
    (tmp_path / "x.json").write_text(json.dumps(_report(0.5, 0.01)))
    (tmp_path / "scripts" / "perf").mkdir(parents=True)
    t, calls, procs = _tools(tmp_path)
    base_run = t.run

    def run(cmd, **kw):
        if cmd[0] == "cp":
            Path(cmd[-1]).mkdir()
            return _done()
        if "load.py" in str(cmd[1]):
            calls.append(cmd)
            return _done(0, "written x.json\n")
        return base_run(cmd, **kw)

    t.run = run
    dest = tmp_path / "dest"
    assert rw.main(_argv(store, dest, "--confirm-paused"), t) == 0
    assert len(procs) == 3 and all(p.terminated for p in procs)
    summary = json.loads((dest / "results" / "summary.json").read_text())
    assert summary["pass"] and len(summary["verdicts"]) == 3
    assert (dest / "results" / "summary.md").exists()
    assert (
        (dest / "config-off" / "site" / "nightly.toml")
        .read_text()
        .startswith("release_reads = false")
    )
    assert any("--publish-every" in c for c in calls if isinstance(c, list))
