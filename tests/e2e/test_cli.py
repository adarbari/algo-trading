"""End-to-end: drive the CLI exactly as CI and humans do, against the committed data.

Most tests call ``main()`` in-process (fast, and counted in coverage); one test runs the
real ``python -m algotrade_backtest`` subprocess to prove the packaging/entry point works.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from algotrade_backtest.cli import main
from algotrade_ingestion.cli.main import main as ingest_main
from tests.conftest import GOLDEN_DIR, REPO_ROOT

pytestmark = pytest.mark.e2e


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str


type Cli = Callable[..., Result]


def _run(entry: Callable[[list[str]], int], args: list[str]) -> Result:
    out, err = io.StringIO(), io.StringIO()
    cwd = Path.cwd()
    os.chdir(REPO_ROOT)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = entry(args)
    finally:
        os.chdir(cwd)
    return Result(code, out.getvalue(), err.getvalue())


@pytest.fixture
def cli(golden_url: str) -> Cli:
    """Run ``algotrade-backtest`` in-process against the golden fixture store."""
    return lambda *args: _run(main, ["--data-url", golden_url, *args])


def test_module_entry_point_runs_as_subprocess(golden_url: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "algotrade_backtest", "--data-url", golden_url, "datasets", "list"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "bull_trend" in proc.stdout


def test_golden_files_verify() -> None:
    proc = _run(ingest_main, ["golden", "verify"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["ok"] is True


def test_datasets_list(cli: Cli) -> None:
    assert "bull_trend" in cli("datasets", "list").stdout


def test_data_url_comes_from_dotenv(
    golden_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(f"ALGOTRADE_DATA_URL={golden_url}\n")
    monkeypatch.delenv("ALGOTRADE_DATA_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main(["datasets", "list"]) == 0
    assert "bull_trend" in out.getvalue()


def test_evaluate_matches_committed_baseline(cli: Cli, tmp_path: Path) -> None:
    report = tmp_path / "scorecard.md"
    proc = cli("evaluate", "--report", str(report))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "all results match baseline" in proc.stdout
    assert report.read_text().startswith("# Strategy scorecard")
    # ADR 0049: the golden store has no regime rows yet; the comparison says so, never fails
    assert "regime overlay: no market feature rows in the store" in proc.stdout


def test_regime_scorecard_says_no_data_on_a_store_without_macro_rows(
    cli: Cli, tmp_path: Path
) -> None:
    report = tmp_path / "regime.txt"
    proc = cli("regime-scorecard", "--report", str(report))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.count("no data: run the macro backfill") == 6  # (a)-(d), (f), (g)
    assert "algotrade-ingest run macro --since 1970-01-01" in proc.stdout
    assert report.read_text() == proc.stdout == cli("regime-scorecard").stdout  # deterministic


def test_backtest_outputs_json(cli: Cli) -> None:
    proc = cli("backtest", "--strategy", "sma_crossover", "--dataset", "bull_trend",
               "--param", "fast=10", "--param", "slow=50")  # fmt: skip
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["params"] == {"fast": 10, "slow": 50}
    assert "sharpe" in payload["metrics"]


def test_bad_input_returns_error_code(cli: Cli, tmp_path: Path) -> None:
    proc = cli("backtest", "--strategy", "nope", "--dataset", "bull_trend")
    assert proc.returncode == 2
    assert "Unknown strategy" in proc.stderr
    unknown = cli("backtest", "--strategy", "buy_and_hold", "--dataset", "nope")
    assert unknown.returncode == 2
    assert "unknown dataset" in unknown.stderr
    empty = _run(main, ["--data-url", f"file://{tmp_path}", "datasets", "list"])
    assert empty.returncode == 2
    assert "make golden-store" in empty.stderr
    assert (
        cli("backtest", "--strategy", "buy_and_hold", "--dataset", "x", "--param", "bad").returncode
        == 2
    )


def test_rebuilding_golden_files_is_deterministic(tmp_path: Path) -> None:
    out = tmp_path / "golden"
    assert _run(ingest_main, ["golden", "build", "--golden-dir", str(out)]).returncode == 0
    rebuilt = json.loads((out / "manifest.json").read_text())
    committed = json.loads((GOLDEN_DIR / "manifest.json").read_text())
    assert rebuilt == committed


def test_evaluate_detects_drift_and_updates_baseline(cli: Cli, tmp_path: Path) -> None:
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


def test_config_validate_and_show_site_presets(cli: Cli) -> None:
    ok = cli("config", "validate", "short_premium_liquidity")
    assert ok.returncode == 0, ok.stderr
    assert "OK (hash" in ok.stdout
    shown = json.loads(cli("config", "show", "sma_trend").stdout)
    assert shown["impl"] == "sma_crossover"
    assert shown["selection"]["name"] == "liquid_optionable"
    assert cli("config", "validate", "nope").returncode == 2


def test_user_config_backtest_reproduces_baseline(cli: Cli, tmp_path: Path) -> None:
    strategies = tmp_path / "users" / "tester" / "strategies"
    strategies.mkdir(parents=True)
    (strategies / "bull_bh.toml").write_text(
        'id = "bull_bh"\nkind = "strategy"\nimpl = "buy_and_hold"\n'
        '[selection]\nname = "bull_only"\n'
        '[selection.where]\nall = [{field = "instrument.symbol", op = "eq", value = "BULL"}]\n'
    )
    args = ("--config-dir", str(tmp_path), "--user", "tester", "backtest", "--config", "bull_bh")
    proc = cli(*args, "--start", "2020-01-01", "--end", "2022-12-31")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    baseline = json.loads((REPO_ROOT / "benchmarks" / "baseline.json").read_text())
    expected = baseline["results"]["buy_and_hold@bull_trend"]["total_return"]
    assert payload["metrics"]["total_return"] == pytest.approx(expected, rel=1e-9)
    assert payload["selection"]["selected"] == 1
    assert payload["user"] == "tester"
    assert payload["survivorship_bias"] is False and payload["as_of"]  # the version pin
    early = cli(*args, "--start", "2019-12-02", "--end", "2022-12-31")  # before the reference
    assert early.returncode == 0, early.stderr
    assert json.loads(early.stdout)["survivorship_bias"] is True
    assert "survivorship bias" in early.stderr
    assert cli(*args).returncode == 2  # --config needs --start/--end
    assert cli("backtest", "--dataset", "bull_trend").returncode == 2  # needs --strategy


def test_config_validate_features_reports_each_user_feature(cli: Cli, tmp_path: Path) -> None:
    (tmp_path / "site").symlink_to(REPO_ROOT / "config" / "site")
    features = tmp_path / "users" / "tester" / "features"
    features.mkdir(parents=True)
    (features / "mine.toml").write_text(
        '[gap]\nexpr = "price_stats.close / price_stats.sma_200 - 1"\ndtype = "float"\n'
        'unit = "decimal"\ndescription = "d"\nnull_meaning = "n"\n'
    )
    args = ("--config-dir", str(tmp_path), "--user", "tester", "config", "validate-features")
    ok = cli(*args)
    assert ok.returncode == 0, ok.stderr
    assert "tester: 1 user feature(s), all valid" in ok.stdout
    assert "feature.gap  expression float  (config/users/tester/features/mine.toml [gap])" in (
        ok.stdout
    )
    assert "inputs: price_stats.close@v2, price_stats.sma_200@v2" in ok.stdout
    (features / "mine.toml").write_text(
        (features / "mine.toml").read_text().replace("sma_200", "sma_201")
    )
    bad = cli(*args)
    assert bad.returncode == 2
    assert "mine.toml [gap] expr, line 1 col 21: price_stats@v2 has no feature 'sma_201'" in (
        bad.stderr
    )
    assert cli("config", "show").returncode == 2  # show needs a config id


def test_evaluate_edges_needs_stored_outcomes_and_a_known_edge(cli: Cli) -> None:
    proc = cli("evaluate-edges")  # the golden store has no outcomes grain
    assert proc.returncode == 2
    assert "no outcomes stored" in proc.stderr
    unknown = cli("evaluate-edges", "--edge", "nope")
    assert unknown.returncode == 2 and "no edge to evaluate" in unknown.stderr
