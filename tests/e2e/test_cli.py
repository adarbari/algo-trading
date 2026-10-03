"""End-to-end: drive the CLI exactly as CI and humans do, against the committed data.

Most tests call ``main()`` in-process (fast, and counted in coverage); one test runs the
real ``python -m algotrade.cli`` subprocess to prove the packaging/entry point works.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from algotrade.cli.main import main
from tests.conftest import GOLDEN_DIR, REPO_ROOT

pytestmark = pytest.mark.e2e


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str


def cli(*args: str) -> Result:
    out, err = io.StringIO(), io.StringIO()
    cwd = Path.cwd()
    os.chdir(REPO_ROOT)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
    finally:
        os.chdir(cwd)
    return Result(code, out.getvalue(), err.getvalue())


def test_module_entry_point_runs_as_subprocess() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "algotrade.cli", "datasets", "verify"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_datasets_verify() -> None:
    proc = cli("datasets", "verify")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "datasets OK" in proc.stdout


def test_datasets_list() -> None:
    assert "bull_trend" in cli("datasets", "list").stdout


def test_evaluate_matches_committed_baseline(tmp_path: Path) -> None:
    report = tmp_path / "scorecard.md"
    proc = cli("evaluate", "--report", str(report))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "all results match baseline" in proc.stdout
    assert report.read_text().startswith("# Strategy scorecard")


def test_backtest_outputs_json() -> None:
    proc = cli("backtest", "--strategy", "sma_crossover", "--dataset", "bull_trend",
               "--param", "fast=10", "--param", "slow=50")  # fmt: skip
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["params"] == {"fast": 10, "slow": 50}
    assert "sharpe" in payload["metrics"]


def test_bad_input_returns_error_code() -> None:
    proc = cli("backtest", "--strategy", "nope", "--dataset", "bull_trend")
    assert proc.returncode == 2
    assert "Unknown strategy" in proc.stderr
    assert (
        cli("backtest", "--strategy", "buy_and_hold", "--dataset", "x", "--param", "bad").returncode
        == 2
    )


def test_rebuilding_datasets_is_deterministic(tmp_path: Path) -> None:
    out = tmp_path / "golden"
    assert cli("--datasets-dir", str(out), "datasets", "build").returncode == 0
    rebuilt = json.loads((out / "manifest.json").read_text())
    committed = json.loads((GOLDEN_DIR / "manifest.json").read_text())
    assert rebuilt == committed


def test_evaluate_detects_drift_and_updates_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    shutil.copy(REPO_ROOT / "benchmarks" / "baseline.json", baseline)
    data = json.loads(baseline.read_text())
    data["results"]["buy_and_hold@bull_trend"]["sharpe"] += 1
    baseline.write_text(json.dumps(data))

    drift = cli("evaluate", "--baseline", str(baseline))
    assert drift.returncode == 1
    assert "buy_and_hold@bull_trend.sharpe" in drift.stdout

    assert cli("evaluate", "--baseline", str(baseline), "--update-baseline").returncode == 0
    assert cli("evaluate", "--baseline", str(baseline)).returncode == 0
    assert cli("evaluate", "--baseline", str(tmp_path / "none.json")).returncode == 1
