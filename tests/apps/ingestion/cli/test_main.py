"""End-to-end: the ingestion CLI against a local store, with fake vendor feeds (no network)."""

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from algotrade_ingestion.cli import main as cli
from algotrade_ingestion.ops import checkout
from algotrade_sources.framework.http import RetryPolicy
from algotrade_sources.framework.registry import build_sources
from algotrade_sources.vendors.cboe.option_chains import CboeOptionsSource
from algotrade_sources.vendors.ishares.etf_holdings import IsharesHoldings
from algotrade_sources.vendors.massive.bars import MassiveDailyBars
from algotrade_sources.vendors.massive.corporate_actions import MassiveCorporateActions
from algotrade_sources.vendors.massive.overview import MassiveOverview
from algotrade_sources.vendors.massive.tickers import MassiveTickers
from algotrade_sources.vendors.nasdaq.earnings import NasdaqEarningsSource
from algotrade_sources.vendors.proshares.etf_holdings import ProsharesHoldings
from algotrade_sources.vendors.ssga.etf_holdings import SsgaHoldings
from algotrade_sources.vendors.treasury.par_yields import TreasuryParYields
from tests.apps.ingestion.tasks.market.test_option_chains import FakeFeed
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for, use_source
from tests.helpers.payloads import cboe as fx
from tests.helpers.payloads import massive as massive_payloads
from tests.helpers.payloads import treasury as treasury_payloads

pytestmark = pytest.mark.e2e
DAY = fx.SESSION.isoformat()


@pytest.fixture(autouse=True)
def _any_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests run from worktrees too; the main-checkout guard has its own tests."""
    monkeypatch.setattr(cli, "ensure_main_checkout", lambda: None)


def massive_feed(url: str) -> bytes:
    """Massive: the asked session's grouped bars for this universe; no corporate actions,
    tickers or descriptions. The nightly's bars and corporate actions are critical (ADR 0039)."""
    if "/aggs/grouped/" in url:
        day = date.fromisoformat(url.split("/stocks/", 1)[1][:10])
        rows = [("AAPL", 230.0, 233.0, 229.0, 232.0, 5e7), ("TQQQ", 80.0, 82.0, 79.0, 81.0, 6e7)]
        return massive_payloads.grouped(day, rows)
    if "/reference/tickers/" in url:
        return massive_payloads.overview(url.rsplit("/", 1)[-1].split("?", maxsplit=1)[0])
    return massive_payloads.page([])


def treasury_feed(url: str) -> bytes:
    """The nightly's rates step: the recorded 2025 curves, nothing published for other years."""
    return treasury_payloads.payload(2025) if "/2025/" in url else b""


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ALGOTRADE_DATA_URL", f"file://{tmp_path / 'data'}")
    # The repo's universe.toml builds from the network; these tests use CSV-import mode.
    import shutil  # noqa: PLC0415

    shutil.copytree(REPO_ROOT / "config" / "site", tmp_path / "config" / "site")
    (tmp_path / "config" / "site" / "universe.toml").write_text('source = "csv_import"\n')
    # A tiered chain status needs a core name (an empty core fails the check): AAPL is pinned.
    cboe = tmp_path / "config" / "site" / "sources.toml"
    cboe.write_text(
        cboe.read_text().replace("priority_symbols = [", 'priority_symbols = [ "AAPL",', 1)
    )
    # No economic-series feed here: the macro step's sources are off, so it has nothing to grade.
    import re  # noqa: PLC0415

    off = re.sub(r"(\[(?:fred|published)\][^\n]*\nenabled = )true", r"\1false", cboe.read_text())
    assert off.count("enabled = false") >= 2
    cboe.write_text(off)
    # Every site screener runs nightly (ADR 0033); the rule preset reads rollups this fixture
    # does not build, so the pipeline test keeps to the one screener its data supports.
    shutil.rmtree(tmp_path / "config" / "site" / "presets" / "screeners")
    monkeypatch.setenv("ALGOTRADE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)  # the nightly writes var/logs/nightly-latest.json here
    # The nightly's "now": the evening of the fixture session, so it is the last closed one.
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    from algotrade_ingestion.workflows.nightly import nightly  # noqa: PLC0415

    evening = datetime.combine(fx.SESSION, datetime.min.time(), UTC) + timedelta(hours=23)
    monkeypatch.setattr(nightly, "utc_now", lambda: evening)
    from tests.helpers.payloads.nasdaq_earnings import calendar  # noqa: PLC0415

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
    use_source(monkeypatch, "treasury", TreasuryParYields(http_for(treasury_feed, policy)))
    monkeypatch.setenv("ALGOTRADE_MASSIVE_API_KEY", "test-key")
    for name, kind in (
        ("massive_bars", MassiveDailyBars),
        ("massive_corporate_actions", MassiveCorporateActions),
        ("massive_tickers", MassiveTickers),
        ("massive_overview", MassiveOverview),
    ):
        use_source(monkeypatch, name, kind(http_for(massive_feed, policy)))
    fixtures = REPO_ROOT / "tests" / "fixtures" / "sources"
    use_source(  # fund lists: State Street and iShares list none of this universe's one ETF
        monkeypatch,
        "ssga_holdings",
        SsgaHoldings(http_for(lambda url: (fixtures / "ssga" / "fundfinder.json").read_bytes())),
    )
    screener = (fixtures / "ishares" / "product-screener.json").read_bytes()
    use_source(monkeypatch, "ishares_holdings", IsharesHoldings(http_for(lambda url: screener)))
    daily = (fixtures / "proshares" / "psdlyhld_sample.csv").read_bytes()  # lists TQQQ
    use_source(monkeypatch, "proshares_holdings", ProsharesHoldings(http_for(lambda url: daily)))
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
    steps = nightly["runs"][-1]["steps"]
    why = {
        n: s.get("error") or s.get("reason") for n, s in steps.items() if s["status"] != "SUCCEEDED"
    }
    assert code == 0 and nightly["status"] == "SUCCEEDED" and nightly["sessions"] == [DAY], why
    screens = steps["screens"]["result"]["screens"]
    assert screens[0]["coverage"] == "COMPLETE" and screens[0]["job_id"].startswith("job-screen")
    assert screens[0]["decisions"] == {"QUALIFIED": 1, "LIQUIDITY_RISK": 1}
    assert screens[0]["universe_pre_snapshot"] is False
    assert all("duration_s" in s for s in steps.values())
    purged = nightly["steps"]["purge-raw"]["result"]
    assert purged["raw_keep_days"]["cboe_delayed"] == 90  # per-source windows
    latest = json.loads((env / "var" / "logs" / "nightly-latest.json").read_text())
    assert latest["status"] == "SUCCEEDED" and latest["sessions"] == [DAY]
    with (env / "out" / f"short_premium_candidates_{DAY}.csv").open() as fh:
        assert [r["ticker"] for r in csv.DictReader(fh)] == ["AAPL"]
    # The nightly summary email, re-rendered from the stored run records (read-only).
    code = cli.main(["report", "--date", DAY, "--out", str(env / "r.html")])
    text = capsys.readouterr().out
    assert code == 0 and text.startswith(f"[algotrade] {DAY} nightly: SUCCEEDED")
    assert "chains 2 OK · 0 failures" in text and "FAILURE DEEP DIVE" in text
    assert (env / "r.html").read_text().startswith("<!doctype html>")


def test_arrivals_command_prints_the_first_published_percentiles(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        cli.main(["arrivals", "--sessions", "0"])
    capsys.readouterr()
    assert cli.main(["arrivals"]) == 0
    assert "no arrival records yet" in capsys.readouterr().out
    import_universe(env, capsys, DAY)
    assert call(capsys, "nightly", "--date", DAY, "--workers", "1")[0] == 0
    assert cli.main(["arrivals", "--sessions", "5"]) == 0
    out = capsys.readouterr().out
    assert "bars" in out and "chains" in out and "min after close" in out


def test_report_command_errors_and_send(
    env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert cli.main(["report", "--date", DAY]) == 2
    assert "no nightly run record" in capsys.readouterr().err
    import_universe(env, capsys, DAY)
    assert call(capsys, "nightly", "--date", DAY, "--workers", "1")[0] == 0
    for name in ("ALGOTRADE_NOTIFY_EMAIL_TO", "ALGOTRADE_SMTP_USER", "ALGOTRADE_SMTP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    assert cli.main(["report", "--date", DAY, "--send", "--max-examples", "1"]) == 1
    assert "email not configured" in capsys.readouterr().err
    sent: list[object] = []

    class FakeSMTP:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def starttls(self, context: object = None) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            pass

        def send_message(self, msg: object) -> None:
            sent.append(msg)

    import smtplib  # noqa: PLC0415

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("ALGOTRADE_NOTIFY_EMAIL_TO", "owner@example.com")
    monkeypatch.setenv("ALGOTRADE_SMTP_USER", "owner@example.com")
    monkeypatch.setenv("ALGOTRADE_SMTP_PASSWORD", "test-app-password")
    assert cli.main(["report", "--date", DAY, "--send"]) == 0
    assert "email sent" in capsys.readouterr().err and len(sent) == 1


def test_individual_steps_and_purge(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    call(capsys, "universe", "--stocks", str(env / "stocks.csv"), "--version", "v", "--date", DAY)
    code, chains = call(capsys, "chains", "--date", DAY, "--symbols", "aapl")
    assert (code, chains["universe"], chains["status"]) == (0, 1, "complete")
    code, dry = call(capsys, "migrate-ids", "--dry-run")
    assert (code, dry["dry_run"], dry["mapped_ids"], dry["tables"]) == (0, True, 0, {})
    code, features = call(capsys, "features", "--date", DAY)  # the pre-2b.2 name, an alias
    assert (code, features["option_liquidity@v1"]["rows"]) == (0, 1)
    assert features["price_stats@v2"]["no_input_sessions"] == [DAY]  # no bars stored
    code, again = call(capsys, "run", "rollups", "--date", DAY)  # the generic form
    assert (code, again["option_liquidity@v1"]["rows"], again["status"]) == (0, 1, "complete")
    code, only = call(
        capsys, "rollups", "--from", "2026-09-30", "--to", DAY, "--only", "option_liquidity@v1"
    )
    assert only["range"] == ["2026-09-30", DAY, 3]
    assert (only["option_liquidity@v1"]["sessions"], only["option_liquidity@v1"]["no_input"]) == (
        1,
        2,
    )
    assert "price_stats@v2" not in only
    code, audit = call(capsys, "screen", "--date", DAY, "--export-dir", str(env / "out"))
    assert audit["coverage"] == "COMPLETE"
    code, retire = call(capsys, "retire-features", "--group", "price_stats@v1", "--dry-run")
    assert (code, retire["sessions"], retire["dry_run"], retire["status"]) == (
        0,
        0,
        True,
        "complete",
    )
    code, purged = call(capsys, "purge-raw", "--keep-days", "0", "--date", "2026-10-03")
    assert (purged["raw_files_removed"], purged["staging_runs_removed"]) == (1, 0)
    assert purged["raw_files_removed_by_source"] == {"cboe_delayed": 1}


def test_rollups_only_iv30(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from algotrade.storage.factory import open_backend  # noqa: PLC0415
    from algotrade.storage.tables.readers import StoreReader  # noqa: PLC0415
    from algotrade.storage.tables.writers import StoreWriter  # noqa: PLC0415
    from tests.helpers.rollup_store import write_curve  # noqa: PLC0415

    call(capsys, "universe", "--stocks", str(env / "stocks.csv"), "--version", "v", "--date", DAY)
    call(capsys, "chains", "--date", DAY, "--symbols", "aapl")
    code, before = call(capsys, "rollups", "--date", DAY, "--only", "iv30@v1")
    assert (before["iv30@v1"]["no_input"], before["status"]) == (1, "partial")
    backend = open_backend(f"file://{env / 'data'}")
    write_curve(StoreWriter(backend), fx.SESSION, 0.04)
    code, only = call(capsys, "rollups", "--date", DAY, "--only", "iv30@v1")
    assert (code, only["iv30@v1"]["rows"], only["status"]) == (0, 1, "complete")
    assert set(only) & {"price_stats@v1", "iv_history@v1"} == set()
    frame = StoreReader(backend).table("rollups/instrument/iv30@v1", fx.SESSION)
    assert frame is not None and frame["iv30_cboe"].iloc[0] == pytest.approx(0.42)
    assert frame["iv30_status"].iloc[0] in ("OK", "SINGLE_EXPIRY")


def test_missing_data_is_a_clean_error(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["screen", "--date", DAY]) == 2
    assert "universe import" in capsys.readouterr().err


def test_default_session_is_the_last_closed_session(env: Path) -> None:
    import argparse  # noqa: PLC0415
    from datetime import UTC, date, datetime  # noqa: PLC0415

    args = argparse.Namespace(config_dir=None)
    sunday = datetime(2026, 10, 4, 15, tzinfo=UTC)
    assert cli.default_session(args, sunday) == date(2026, 10, 2)
    friday_evening_et = datetime(2026, 10, 3, 2, tzinfo=UTC)
    assert cli.default_session(args, friday_evening_et) == date(2026, 10, 2)
    during_market = datetime(2026, 10, 2, 15, tzinfo=UTC)  # 11:00 New York
    assert cli.default_session(args, during_market) == date(2026, 10, 1)
    good_friday = datetime(2027, 3, 26, 23, tzinfo=UTC)
    assert cli.default_session(args, good_friday) == date(2027, 3, 25)


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
        'extends = "short_premium_liquidity"\n'
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
    assert written["install"][1].startswith("launchctl unload")  # replaces an installed agent
    assert written["install"][-1].startswith("launchctl load")
    assert written["optional_wake"]["command"] == "sudo pmset repeat wakeorpoweron MTWRF 14:55:00"
    agent = plistlib.loads((env / "agent.plist").read_bytes())
    assert agent["StartCalendarInterval"][0]["Minute"] == 15 and agent["StartInterval"] == 3600
    code, written = call(
        capsys, "schedule", "--watchdog-minutes", "0", "--out", str(env / "agent.plist")
    )
    assert written["weekdays_at"] == "15:00" and written["watchdog_minutes"] is None
    agent = plistlib.loads((env / "agent.plist").read_bytes())
    assert agent["StartCalendarInterval"][0]["Hour"] == 15 and "StartInterval" not in agent


def test_company_details_command(
    env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from algotrade.config.site.settings import SourcesSettings  # noqa: PLC0415
    from tests.apps.ingestion.tasks.reference.test_company_details import (  # noqa: PLC0415
        FakeSec,
        sources,
    )

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
    details = nightly["runs"][-1]["steps"]["company-details"]
    assert details["result"]["requested"] == 0  # already fresh: no requests


def test_nightly_skips_company_details_without_contact(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    call(capsys, "universe", "--stocks", str(env / "stocks.csv"), "--version", "v", "--date", DAY)
    _, nightly = call(capsys, "nightly", "--date", DAY, "--workers", "1")
    details = nightly["runs"][-1]["steps"]["company-details"]
    assert details["status"] == "SKIPPED" and details["reason"].startswith("skipped")


def test_a_second_writing_run_exits_3_unless_it_waits(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import threading  # noqa: PLC0415

    from algotrade.config.env import data_url  # noqa: PLC0415
    from algotrade.services.jobs import exclusive_run  # noqa: PLC0415
    from algotrade.storage.factory import open_backend  # noqa: PLC0415

    other = open_backend(data_url())  # its own lock file handle: behaves like another process
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

    from algotrade.config.env import data_url  # noqa: PLC0415
    from algotrade.config.user import SITE_USER, UserContext  # noqa: PLC0415
    from algotrade.services.jobs import JobRecord, JobStatus, job_id_for  # noqa: PLC0415
    from algotrade.storage.factory import open_backend  # noqa: PLC0415

    call(capsys, "universe", "--stocks", str(env / "stocks.csv"), "--version", "v", "--date", DAY)
    params = {
        "session": DAY,
        "catch_up": False,
        "resume": True,
        "waive": {},
        "workers": 1,
        "export_dir": None,
    }
    job_id = job_id_for("nightly", params, UserContext(SITE_USER))
    stuck = JobRecord(job_id, "nightly", params, SITE_USER, datetime.now(UTC))
    stuck.status = JobStatus.RUNNING
    open_backend(data_url()).runs.save(stuck.to_run())
    _, result = call(capsys, "nightly", "--date", DAY, "--workers", "1")
    assert result["job_id"] == job_id and "earnings" in result["runs"][-1]["steps"]


def import_universe(env: Path, capsys: pytest.CaptureFixture[str], day: str) -> None:
    code, _ = call(
        capsys, "universe", "--stocks", str(env / "stocks.csv"), "--etfs", str(env / "etfs.csv"),
        "--version", "v", "--date", day,
    )  # fmt: skip
    assert code == 0


def accept_stale_chains(env: Path) -> None:
    sources = env / "config" / "site" / "sources.toml"
    text = (
        sources.read_text()
        .replace("max_chain_stale_share = 0.20", "max_chain_stale_share = 1.0")
        .replace("max_chain_stale_share_core = 0.02", "max_chain_stale_share_core = 1.0")
    )
    sources.write_text(text)


def nightly_records() -> list:  # type: ignore[type-arg]
    from algotrade.config.env import data_url  # noqa: PLC0415
    from algotrade.storage.factory import open_backend  # noqa: PLC0415

    backend = open_backend(data_url())
    return [*backend.runs.find("nightly"), *backend.runs.find("job:nightly")]


def all_run_files(env: Path) -> set[str]:
    return {p.name for p in (env / "data" / "runs").glob("*.json")}


def scheduled_at(monkeypatch: pytest.MonkeyPatch, session: str) -> None:
    """The last closed session the scheduled (no --date) nightly sees."""
    from datetime import date  # noqa: PLC0415

    monkeypatch.setattr(cli, "default_session", lambda args, now: date.fromisoformat(session))


def no_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    from algotrade_ingestion.workflows.nightly import nightly  # noqa: PLC0415

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("the no-op path must not notify")

    monkeypatch.setattr(nightly, "report", boom)
    monkeypatch.setattr(nightly, "default_notifier", boom)


def test_scheduled_nightly_catches_up_then_is_a_quiet_no_op(
    env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import time  # noqa: PLC0415

    from algotrade.core.time.calendar import previous_session  # noqa: PLC0415

    before = previous_session(fx.SESSION).isoformat()
    import_universe(env, capsys, before)
    # The fake Cboe feed serves one session's snapshot: accept its stale chains, and leave
    # the screens (covered end to end above) out of this catch-up test.
    accept_stale_chains(env)
    from algotrade_ingestion.workflows.nightly import screens  # noqa: PLC0415

    monkeypatch.setattr(screens, "nightly_screeners", lambda configs: [])
    scheduled_at(monkeypatch, before)
    code, first = call(capsys, "nightly", "--workers", "1")  # no earlier nightly: one session
    why = {
        n: v.get("error") or v.get("reason")
        for n, v in first["runs"][-1]["steps"].items()
        if v["status"] not in ("SUCCEEDED", "SKIPPED")
    }
    assert code == 0 and first["sessions"] == [before], why
    # The Mac was off over the next close: the next start catches the missed session up.
    scheduled_at(monkeypatch, DAY)
    code, caught_up = call(capsys, "nightly", "--workers", "1")
    assert code == 0 and caught_up["sessions"] == [DAY]
    assert caught_up["catch_up"]["last_done"] == before
    # Up to date: one line, exit 0, no run record of any kind, no notification, fast.
    files = all_run_files(env)
    no_notifications(monkeypatch)
    started = time.perf_counter()
    assert cli.main(["nightly", "--workers", "1"]) == 0
    elapsed = time.perf_counter() - started
    out = capsys.readouterr()
    assert out.out == f"nothing to do: {DAY} already ingested\n" and out.err == ""
    assert all_run_files(env) == files
    assert elapsed < 1.0


def test_force_reruns_the_last_session_when_up_to_date(
    env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import_universe(env, capsys, DAY)
    scheduled_at(monkeypatch, DAY)
    call(capsys, "nightly", "--workers", "1")
    count = len(nightly_records())
    code, forced = call(capsys, "nightly", "--force", "--workers", "1")
    assert code == 0 and forced["sessions"] == [DAY]
    assert len(nightly_records()) > count  # a new run record for the same session


def test_scheduled_nightly_while_locked_exits_quietly(
    env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from algotrade.config.env import data_url  # noqa: PLC0415
    from algotrade.services.jobs import exclusive_run  # noqa: PLC0415
    from algotrade.storage.factory import open_backend  # noqa: PLC0415

    scheduled_at(monkeypatch, DAY)
    no_notifications(monkeypatch)
    with exclusive_run(open_backend(data_url())):  # e.g. the nightly started an hour ago
        assert cli.main(["nightly"]) == cli.LOCKED_EXIT
        out = capsys.readouterr()
        assert out.out.startswith("busy: ") and out.err == ""
        assert cli.main(["nightly", "--date", DAY]) == cli.LOCKED_EXIT  # explicit: an error
        assert "pass --wait" in capsys.readouterr().err
    assert nightly_records() == []


def test_nightly_refuses_code_from_a_worktree(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    wt = env / "algo-trading-feat-x"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: /main/.git/worktrees/x\n")
    init = wt / "src" / "algotrade" / "__init__.py"
    init.parent.mkdir(parents=True)
    init.touch()
    monkeypatch.setattr(cli, "ensure_main_checkout", lambda: checkout.ensure_main_checkout((init,)))
    assert cli.main(["nightly", "--force"]) == 2
    assert "refusing to run the nightly" in capsys.readouterr().err
    assert not (env / "data").exists()  # refused before touching the store
