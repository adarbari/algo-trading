"""End-to-end: the ingestion CLI against a local store, with a fake Cboe feed."""

import csv
import json
from pathlib import Path

import pytest

from algotrade_ingestion import cli
from algotrade_ingestion.sources.cboe import CboeOptionsSource
from algotrade_ingestion.sources.http import RetryPolicy
from tests import cboe_fixture as fx
from tests.apps.ingestion.test_jobs import FakeFeed

pytestmark = pytest.mark.e2e
DAY = fx.SESSION.isoformat()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ALGOTRADE_DATA_URL", f"file://{tmp_path / 'data'}")
    feed = FakeFeed(
        {
            "AAPL": fx.payload("AAPL", options=fx.chain("AAPL", spread=0.02, oi=5000)),
            "TQQQ": fx.payload("TQQQ", options=fx.chain("TQQQ", spread=1.0, oi=5)),
        }
    )
    monkeypatch.setattr(
        cli, "_source", lambda: CboeOptionsSource(feed, lambda s: None, RetryPolicy(tries=1))
    )
    (tmp_path / "stocks.csv").write_text(
        f"ticker,company_name,security_type,last_verified\nAAPL,Apple,COMMON_STOCK,{DAY}\n"
    )
    (tmp_path / "etfs.csv").write_text(f"ticker,company_name,last_verified\nTQQQ,ProShares,{DAY}\n")
    return tmp_path


def call(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict]:  # type: ignore[type-arg]
    code = cli.main(list(args))
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip().startswith("{") else {}


def test_nightly_pipeline_end_to_end(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, imported = call(
        capsys,
        "universe",
        "--stocks",
        str(env / "stocks.csv"),
        "--etfs",
        str(env / "etfs.csv"),
        "--version",
        "2026-10",
        "--date",
        DAY,
    )
    assert code == 0 and imported["unique_tickers"] == 2
    code, nightly = call(
        capsys, "nightly", "--date", DAY, "--export-dir", str(env / "out"), "--workers", "2"
    )
    assert code == 0
    assert nightly["screens"][0]["coverage"] == "COMPLETE"
    assert nightly["screens"][0]["decisions"] == {"QUALIFIED": 1, "LIQUIDITY_RISK": 1}
    with (env / "out" / f"short_premium_candidates_{DAY}.csv").open() as fh:
        assert [r["ticker"] for r in csv.DictReader(fh)] == ["AAPL"]


def test_individual_steps_and_purge(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    call(capsys, "universe", "--stocks", str(env / "stocks.csv"), "--version", "v", "--date", DAY)
    code, chains = call(capsys, "chains", "--date", DAY, "--symbols", "aapl")
    assert (code, chains["universe"], chains["status"]) == (0, 1, "complete")
    code, features = call(capsys, "features", "--date", DAY)
    assert features["liq_status"] == {"OK": 1}
    code, audit = call(capsys, "screen", "--date", DAY, "--export-dir", str(env / "out"))
    assert audit["coverage"] == "COMPLETE"
    code, purged = call(capsys, "purge-raw", "--keep-days", "0", "--date", "2026-10-03")
    assert purged["raw_files_removed"] == 1


def test_missing_data_is_a_clean_error(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["screen", "--date", DAY]) == 2
    assert "universe import" in capsys.readouterr().err


def test_last_session_skips_weekends() -> None:
    from datetime import UTC, date, datetime  # noqa: PLC0415

    assert cli.last_session(datetime(2026, 10, 4, 15, tzinfo=UTC)) == date(2026, 10, 2)  # Sunday
    assert cli.last_session(datetime(2026, 10, 3, 2, tzinfo=UTC)) == date(
        2026, 10, 2
    )  # Fri evening ET


def test_screen_runs_a_user_config(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    call(
        capsys,
        "universe",
        "--stocks",
        str(env / "stocks.csv"),
        "--etfs",
        str(env / "etfs.csv"),
        "--version",
        "v",
        "--date",
        DAY,
    )
    call(capsys, "chains", "--date", DAY)
    call(capsys, "features", "--date", DAY)
    user_dir = env / "config" / "users" / "alice" / "strategies"
    user_dir.mkdir(parents=True)
    (user_dir / "stocks_only.toml").write_text(
        'extends = "short_premium_liquidity"\nschedule = "nightly"\n'
        '[selection_overrides]\nall = [{field = "instrument.is_etf", op = "eq", value = false}]\n'
    )
    site = Path(__file__).resolve().parents[3] / "config" / "site"
    import shutil  # noqa: PLC0415

    shutil.copytree(site, env / "config" / "site")
    code, audit = call(
        capsys,
        "--config-dir",
        str(env / "config"),
        "screen",
        "--date",
        DAY,
        "--config",
        "stocks_only",
        "--user",
        "alice",
    )
    assert code == 0
    assert audit["user"] == "alice"
    assert audit["selection"]["selected"] == 1  # TQQQ (an ETF) narrowed away
