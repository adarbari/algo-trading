"""`scripts/perf/release_writer_run.py`: every guard, the dry-run plan, the path checks, the
port choice, the config override and the verdicts (subprocess, copy and API calls are fakes)."""

import importlib.util
import json
import signal
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
        if cmd[0] == "df":
            return _done(
                0,
                "Filesystem 512-blocks Used Available Capacity Mounted on\n/dev/disk3s5 1 1 1 1% /",
            )
        if cmd[0] == "diskutil":
            assert cmd[2] == "/dev/disk3s5"  # a device: diskutil rejects a plain path
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
    assert all(c[0] in ("df", "diskutil") for c in calls)


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


def _full(tmp_path, store, monkeypatch, env=None, run_hook=None, procs=None):
    """A full fake run; returns (exit code, dest, spawned (cmd, kwargs) list, procs)."""
    monkeypatch.setattr(rw, "REPO", tmp_path)
    (tmp_path / "config" / "site").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "site" / "nightly.toml").write_text("release_reads = true\n")
    (tmp_path / "x.json").write_text(json.dumps(_report(0.5, 0.01)))
    t, _calls, procs = _tools(tmp_path, procs=procs)
    t.env = {**t.env, **(env or {})}
    spawned = []

    def run(cmd, **kw):
        spawned.append((cmd, kw))
        if cmd[0] == "df":
            return _done(
                0,
                "Filesystem 512-blocks Used Available Capacity Mounted on\n/dev/disk3s5 1 1 1 1% /",
            )
        if cmd[0] == "diskutil":
            return _done(0, "apfs")
        if cmd[0] == "cp":
            Path(cmd[-1]).mkdir()
            return _done()
        if run_hook:
            run_hook(cmd)
        return _done(0, "written x.json\n")

    def popen(cmd, **kw):
        spawned.append((cmd, kw))
        procs.append(FakeProc())
        return procs[-1]

    t.run, t.popen = run, popen
    dest = tmp_path / "dest"
    return rw.main(_argv(store, dest, "--confirm-paused"), t), dest, spawned, procs


def test_children_get_the_clone_and_dest_config_not_the_inherited_store(
    tmp_path, store, monkeypatch
):
    env = {"ALGOTRADE_DATA_URL": "file:///real/var/data", "ALGOTRADE_CONFIG_DIR": "/real/config"}
    code, dest, spawned, _ = _full(tmp_path, store, monkeypatch, env)
    assert code == 0
    clone_url = f"file://{dest.resolve()}/data"
    children = [(c, k) for c, k in spawned if c[0] not in ("df", "diskutil", "cp")]
    assert len(children) == 7  # serve-release, 3 APIs, 3 load.py
    for cmd, kw in children:
        assert kw["env"]["ALGOTRADE_DATA_URL"] == clone_url, cmd
        assert Path(kw["env"]["ALGOTRADE_CONFIG_DIR"]).parent == dest.resolve(), cmd
        assert kw["env"]["ALGOTRADE_AUTH"] == "off"
        assert Path(kw["cwd"]) == dest.resolve() / "results", cmd  # never the operator's cwd
    loads = [c for c, _ in children if "load.py" in str(c[1])]
    assert all(c[c.index("--out") + 1] == str(dest.resolve() / "results") for c in loads)
    writers = [c[c.index("--writer-store") + 1] for c in loads if "--writer-store" in c]
    assert writers == [clone_url, clone_url]


def test_cold_run_is_one_level_within_five_minutes(tmp_path, store, monkeypatch):
    _, _, spawned, _ = _full(tmp_path, store, monkeypatch)
    cold = next(c for c, _ in spawned if "cold" in c)
    assert cold[cold.index("--users") + 1 : cold.index("--seconds")] == ["100"]
    assert int(cold[cold.index("--seconds") + 1]) <= 300


def test_sigterm_stops_the_api(tmp_path, store, monkeypatch):
    def hook(cmd):
        if "load.py" in str(cmd[1]):
            signal.raise_signal(signal.SIGTERM)

    before = signal.getsignal(signal.SIGTERM)
    procs = []
    with pytest.raises(SystemExit):
        _full(tmp_path, store, monkeypatch, run_hook=hook, procs=procs)
    assert procs and all(p.terminated for p in procs)
    assert signal.getsignal(signal.SIGTERM) == before


def test_sighup_terminates_started_api(tmp_path, store, monkeypatch):
    def hook(cmd):
        if "load.py" in str(cmd[1]):
            signal.raise_signal(signal.SIGHUP)

    procs = []
    with pytest.raises(SystemExit) as exc:
        _full(tmp_path, store, monkeypatch, run_hook=hook, procs=procs)
    assert exc.value.code == 128 + signal.SIGHUP
    assert procs and all(p.terminated for p in procs)


def test_api_that_exited_is_not_healthy_even_if_something_answers(tmp_path):
    t, _, _ = _tools(tmp_path)

    class Dead(FakeProc):
        def poll(self):
            return 1

    t.popen = lambda cmd, **kw: Dead()
    with pytest.raises(RuntimeError), rw.api_process(t, 1, {}, tmp_path / "log", tmp_path):
        pass


def test_dest_in_main_checkout_refused(tmp_path):
    main = tmp_path / "main"
    store = main / "var" / "data"
    store.mkdir(parents=True)
    with pytest.raises(rw.RefusalError, match="main checkout"):
        rw.check_paths(main / "scratch", store, main / "scratch" / "data", repo=tmp_path / "wt")


def test_missing_store_is_a_clean_refusal(tmp_path, capsys):
    t, *_ = _tools(tmp_path)
    argv = ["--dest", str(tmp_path / "d"), "--source-url", f"file://{tmp_path}/nope"]
    assert rw.main(argv, t) == 2
    assert "does not exist" in capsys.readouterr().err


def test_child_env_drops_inherited_algotrade_settings():
    env = rw.child_env(
        {
            "ALGOTRADE_DATA_URL": "real",
            "ALGOTRADE_CACHE": "x",
            "ALGOTRADE_PORT_BASE": "5",
            "A": "b",
        },
        "file:///c",
        Path("/cfg"),
    )
    assert env["ALGOTRADE_DATA_URL"] == "file:///c" and "ALGOTRADE_CACHE" not in env
    assert env["ALGOTRADE_PORT_BASE"] == "5" and env["A"] == "b"
