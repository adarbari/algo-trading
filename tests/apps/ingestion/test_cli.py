"""End-to-end: the ingestion CLI against a local store, with a fake Cboe feed."""

import csv
import json
from pathlib import Path

import pytest

from algotrade_ingestion import cli
from algotrade_ingestion.sources.cboe import CboeOptionsSource
from algotrade_ingestion.sources.http import RetryPolicy
from algotrade_ingestion.sources.registry import build_sources
from tests import cboe_fixture as fx
from tests.apps.ingestion.tasks.test_option_chains import FakeFeed
from tests.ingest_helpers import http_for, use_source

pytestmark = pytest.mark.e2e
DAY = fx.SESSION.isoformat()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ALGOTRADE_DATA_URL", f"file://{tmp_path / 'data'}")
    # The repo's universe.toml builds from the network; these tests use CSV-import mode.
    import shutil  # noqa: PLC0415

    shutil.copytree(
        Path(__file__).resolve().parents[3] / "config" / "site", tmp_path / "config" / "site"
    )
    (tmp_path / "config" / "site" / "universe.toml").write_text('source = "csv_import"\n')
    monkeypatch.setenv("ALGOTRADE_CONFIG_DIR", str(tmp_path / "config"))
    from algotrade_ingestion.sources.nasdaq_earnings import NasdaqEarningsSource  # noqa: PLC0415
    from tests.earnings_fixture import calendar  # noqa: PLC0415

    earnings = calendar([("AAPL", "time-after-hours")])
    policy = RetryPolicy(tries=1)
    use_source(
        monkeypatch, "nasdaq_earnings", NasdaqEarningsSource(http_for(lambda url: earnings, policy))
    )
    feed = FakeFeed(
        {
            "AAPL": fx.payload("AAPL", options=fx.chain("AAPL", spread=0.02, oi=5000)),
            "TQQQ": fx.payload("TQQQ", options=fx.chain("TQQQ", spread=1.0, oi=5)),
        }
    )
    use_source(monkeypatch, "cboe", CboeOptionsSource(http_for(feed, policy)))
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
    code, dry = call(capsys, "migrate-ids", "--dry-run")
    assert (code, dry["dry_run"], dry["mapped_ids"], dry["tables"]) == (0, True, 0, {})
    code, features = call(capsys, "features", "--date", DAY)
    assert features["liq_status"] == {"OK": 1}
    code, again = call(capsys, "run", "features", "--date", DAY)  # the generic form
    assert (code, again["liq_status"], again["status"]) == (0, {"OK": 1}, "complete")
    code, audit = call(capsys, "screen", "--date", DAY, "--export-dir", str(env / "out"))
    assert audit["coverage"] == "COMPLETE"
    code, purged = call(capsys, "purge-raw", "--keep-days", "0", "--date", "2026-10-03")
    assert (purged["raw_files_removed"], purged["staging_runs_removed"]) == (1, 0)


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


def test_quality_and_schedule_commands(
    env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import plistlib  # noqa: PLC0415

    code, result = call(capsys, "quality", "--date", DAY)
    assert code == 1 and "universe_present" in result["failed"]  # empty store fails closed
    monkeypatch.chdir(env)
    code, written = call(capsys, "schedule", "--time", "22:15", "--out", str(env / "agent.plist"))
    assert code == 0 and written["weekdays_at"] == "22:15"
    assert any(step.startswith("launchctl load") for step in written["install"])
    assert (
        plistlib.loads((env / "agent.plist").read_bytes())["StartCalendarInterval"][0]["Minute"]
        == 15
    )


def test_company_details_command(
    env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from algotrade_ingestion.settings import SourcesSettings  # noqa: PLC0415
    from tests.apps.ingestion.tasks.test_company_details import FakeSec, sources  # noqa: PLC0415

    call(capsys, "universe", "--stocks", str(env / "stocks.csv"), "--version", "v", "--date", DAY)
    assert cli.main(["company-details", "--date", DAY]) == 2  # no contact email configured
    assert "company-details skipped: ALGOTRADE_SEC_CONTACT is not set" in capsys.readouterr().err
    names = ["sec_tickers", "sec_submissions"]
    none = build_sources(SourcesSettings(), lambda name: None, names)
    assert none.sources == {} and "ALGOTRADE_SEC_CONTACT" in none.skipped["sec_tickers"]
    real = build_sources(SourcesSettings(), lambda name: "ops@example.org", names, env / "lim")
    assert set(real.sources) == set(names)  # built without the network
    monkeypatch.setenv("ALGOTRADE_SEC_CONTACT", "ops@example.org")
    fake = sources(FakeSec())
    use_source(monkeypatch, "sec_tickers", fake.tickers)
    use_source(monkeypatch, "sec_submissions", fake.submissions)
    code, result = call(capsys, "company-details", "--date", DAY, "--limit", "5")
    assert (code, result["rows"], result["cik_from_sec_map"]) == (0, 1, 1)  # AAPL via the map
    _, nightly = call(capsys, "nightly", "--date", DAY, "--workers", "1")
    assert nightly["company_details"]["requested"] == 0  # already fresh: no requests


def test_nightly_skips_company_details_without_contact(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    call(capsys, "universe", "--stocks", str(env / "stocks.csv"), "--version", "v", "--date", DAY)
    _, nightly = call(capsys, "nightly", "--date", DAY, "--workers", "1")
    assert nightly["company_details"].startswith("skipped")


def test_a_second_writing_run_exits_3_unless_it_waits(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import threading  # noqa: PLC0415

    from algotrade.services.jobs import exclusive_run  # noqa: PLC0415
    from algotrade.storage.factory import open_backend  # noqa: PLC0415

    other = open_backend()  # its own lock file handle: behaves like another process
    with exclusive_run(other):
        assert cli.main(["purge-raw", "--date", DAY]) == cli.LOCKED_EXIT
        assert "pass --wait" in capsys.readouterr().err
        code, _ = call(capsys, "schedule", "--out", str(env / "agent.plist"))
        assert code == 0  # writes no store data: no lock needed
        codes: list[int] = []
        waiter = threading.Thread(
            target=lambda: codes.append(cli.main(["purge-raw", "--date", DAY, "--wait"]))
        )
        waiter.start()
        waiter.join(timeout=0.3)
        assert waiter.is_alive() and codes == []  # queued behind the holder
    waiter.join(timeout=30)
    assert codes == [0]


def test_nightly_recovers_a_job_left_running_by_a_crashed_process(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from datetime import UTC, datetime  # noqa: PLC0415

    from algotrade.config.user import SITE_USER, UserContext  # noqa: PLC0415
    from algotrade.services.jobs import JobRecord, JobStatus, job_id_for  # noqa: PLC0415
    from algotrade.storage.factory import open_backend  # noqa: PLC0415

    call(capsys, "universe", "--stocks", str(env / "stocks.csv"), "--version", "v", "--date", DAY)
    params = {"session": DAY, "workers": 1, "export_dir": None}
    job_id = job_id_for("nightly", params, UserContext(SITE_USER))
    stuck = JobRecord(job_id, "nightly", params, SITE_USER, datetime.now(UTC))
    stuck.status = JobStatus.RUNNING
    open_backend().runs.save(stuck.to_run())
    code, result = call(capsys, "nightly", "--date", DAY, "--workers", "1")
    assert code == 0 and result["job_id"] == job_id and "earnings" in result
