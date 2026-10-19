"""`scripts/ops/xdist_workers.py`: the worker count is capped to 2 above a load of 12 and
``auto`` otherwise; only the count changes."""

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "xdist_workers.py"
spec = importlib.util.spec_from_file_location("xdist_workers", SCRIPT)
assert spec and spec.loader
xdist_workers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xdist_workers)


def test_a_loaded_machine_is_capped_to_two_workers() -> None:
    assert xdist_workers.workers(12.1) == "2"
    assert xdist_workers.workers(40.0) == "2"


def test_an_idle_or_borderline_machine_keeps_auto() -> None:
    assert xdist_workers.workers(12.0) == "auto"
    assert xdist_workers.workers(0.5) == "auto"


def test_the_limit_override_decides() -> None:
    assert xdist_workers.workers(5.0, limit=4.0) == "2"


def _run(*args: str, limit: str) -> str:
    env = {"ALGOTRADE_LOAD_LIMIT": limit, "PATH": ""}
    done = subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=True, env=env
    )
    return done.stdout.strip()


def test_the_script_prints_two_when_the_limit_is_below_any_load() -> None:
    assert _run(limit="-1") == "2"
    assert _run(limit="1000000") == "auto"
    assert "xdist workers 2" in _run("--explain", limit="-1")
