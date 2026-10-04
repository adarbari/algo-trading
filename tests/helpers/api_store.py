"""The store the API and explore tests read: the golden datasets loaded through ingestion, plus
one session (``END``, the last golden session) of everything else a page shows: universe,
reference facts with review marks, company details, rollups, events, an option chain, the
verification vs IBKR, run records (incl. data-quality checks), screen results and a saved
backtest."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from algotrade.config.user import SITE_USER, UserContext
from algotrade.services.backtests.run import EQUITY, FILLS, PORTFOLIO
from algotrade.services.backtests.run import run_job_name as backtest_job
from algotrade.services.explore.store import ReadStore, store_over
from algotrade.services.screening.run import run_job_name as screen_job
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.runs import RunRecord, start_run
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.golden import load_golden
from algotrade_sources.framework.base import FixtureSource
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import chain_rows, write_chains, write_dividends, write_split
from tests.helpers.stored_frames import stamped, universe_rows

END = date(2022, 11, 23)  # the last golden session
PREVIOUS = date(2022, 11, 22)
NOW = datetime(2022, 11, 24, 2, tzinfo=UTC)
SYMBOLS = ["AAA", "BBB", "BULL", "CCC"]
SPLIT_DAY = date(2022, 6, 1)
CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"


def _write(writer: StoreWriter, table: str, rows: list[dict[str, object]], day: date = END) -> None:
    run = f"{table.replace('/', '_')}-{day}"
    writer.write_table(table, day, run, stamped(rows, day, run))


def _reference(writer: StoreWriter) -> None:
    rows = [
        {
            "instrument_id": f"EQ:{s}",
            "symbol": s,
            "name": f"{s} Corp",
            "asset_class": "EQUITY",
            "security_type": "ETF" if s == "BULL" else "COMMON_STOCK",
            "exchange": "NASDAQ",
            "multiplier": 1.0,
            "status": "ACTIVE",
            "optionable": True,
            "is_leveraged": s == "BULL",
            "leverage_source": "needs_review" if s == "CCC" else "name_rule",
            "vendor_figi": "BBG000000001" if s == "BBB" else None,
        }
        for s in SYMBOLS
    ]
    _write(writer, "instruments/reference", rows)
    company = {"symbol": "AAA", "cik": "1", "name": "AAA Corp", "sic": "3571"}
    _write(writer, "instruments/company", [{
        "instrument_id": "EQ:AAA", **company, "sector": "Technology", "fetched_on": END,
    }])  # fmt: skip
    _write(writer, "universe", universe_rows(SYMBOLS))


# Option liquidity on END: (status, put tier, call tier, chain OI, chain volume). With $200M
# ADV and a close above $10 the liquidity class (an expression feature) is AAA and BULL HIGH,
# BBB MEDIUM (tier B), CCC LOW (no usable options).
OPTIONS = {
    "AAA": ("OK", "A", "A", 100_000, 10_000),
    "BBB": ("OK", "B", "A", 10_000, 100),
    "BULL": ("OK", "A", "A", 100_000, 10_000),
    "CCC": ("OK", "D", "D", 0, 0),
}


def _rollups(writer: StoreWriter) -> None:
    for day, close in ((PREVIOUS, 99.0), (END, 101.0)):
        rows = [{"instrument_id": f"EQ:{s}", "close": close + i, "hv20": 0.2 + i / 100,
                 "adv_usd_20d": 200e6} for i, s in enumerate(SYMBOLS)]  # fmt: skip
        rows[-1]["hv20"] = None
        frame = stamped(rows, day, f"price_stats-{day}").astype(
            {"close": "float32", "hv20": "float32", "adv_usd_20d": "float32"}
        )
        writer.write_table("rollups/instrument/price_stats@v2", day, f"ps-{day}", frame)
    columns = ("liq_status", "put_tier", "call_tier", "chain_oi", "chain_volume")
    _write(writer, "rollups/instrument/option_liquidity@v1", [
        {"instrument_id": f"EQ:{s}", **dict(zip(columns, v, strict=True))}
        for s, v in OPTIONS.items()
    ])  # fmt: skip
    _write(writer, "rollups/instrument/iv30@v1", [{"instrument_id": "EQ:AAA", "iv30": 0.24}])


def _market(writer: StoreWriter) -> None:
    write_split(writer, "EQ:AAA", SPLIT_DAY, 2.0, SPLIT_DAY)
    write_dividends(writer, [("EQ:AAA", date(2022, 9, 1), 0.5, "CD")], END)
    expiries = {END + timedelta(days=30): 0.25, END + timedelta(days=60): 0.27}
    options = chain_rows("EQ:AAA", END, 100.0, expiries, 0.03)
    write_chains(writer, END, options, {"EQ:AAA": 100.0})
    _write(writer, "chains/status", [{"instrument_id": "EQ:AAA", "symbol": "AAA", "status": "OK"}])
    _write(writer, "verification/ibkr", [
        {"instrument_id": f"EQ:{s}", "symbol": s, "check": check, "status": status,
         "ours": 1.0, "theirs": None if diff is None else 1 + diff, "diff": diff,
         "tolerance": 0.001, "note": "rel diff"}
        for s, check, status, diff in (
            ("AAA", "close", "PASS", 0.0), ("AAA", "low", "FAIL", 0.002),
            ("BBB", "low", "FAIL", 0.003), ("BBB", "close", "WARN", 0.0015),
            ("CCC", "div_yield", "NA", None),
        )
    ])  # fmt: skip


def _runs(writer: StoreWriter) -> None:
    nightly = start_run("nightly", END, NOW)
    nightly.items = {"bars": "COMPLETE", "chains": "PARTIAL"}
    nightly.stats = {
        "steps": {
            "bars": {"status": "COMPLETE", "duration_s": 1.5, "result": {"rows": 11}},
            "chains": {"status": "PARTIAL", "duration_s": 9.0, "result": {"statuses": {"OK": 1}}},
        },
        "partial": ["steps not complete: chains"],
    }
    writer.save_run(nightly.finish(NOW + timedelta(minutes=5), complete=False))
    chains = start_run("option_chains", END, NOW)
    chains.items = {"AAA": "OK", "BBB": "NO_CHAIN", "CCC": "STALE_DATA: chain is for 2022-11-21"}
    writer.save_run(chains.finish(NOW, complete=False))
    quality = start_run("data_quality", END, NOW)
    quality.items = {"bars_fresh": "PASS", "chains_stale": "WARN"}
    quality.stats = {"checks": [
        {"name": "bars_fresh", "status": "PASS", "detail": "latest bars session 2022-11-23"},
        {"name": "chains_stale", "status": "WARN", "detail": "25.0% stale (max 20%)"},
    ]}  # fmt: skip
    writer.save_run(quality.finish(NOW))
    build = start_run("universe_build", END, NOW)
    review = {"symbol": "BBB", "held_figi": "", "vendor_figi": "BBG000000001", "note": "shared"}
    writer.save_run(build.finish(NOW, stats={"figi_review": [review]}))


def _screen(writer: StoreWriter) -> None:
    run = start_run(screen_job("short_premium_liquidity", SITE_USER), END, NOW)
    rows = [
        {"instrument_id": f"EQ:{s}", "decision": d, "score": score, "reasons": "",
         "put_tier": "A", "user_id": SITE_USER, "config_id": "short_premium_liquidity",
         "config_hash": "h"}
        for s, d, score in (("AAA", "QUALIFIED", 2.0), ("BBB", "REJECTED", 1.0))
    ]  # fmt: skip
    writer.write_result("short_premium_liquidity", END, run.run_id, stamped(rows, END, run.run_id))
    writer.save_run(run.finish(NOW, stats={"coverage": "COMPLETE", "config_hash": "h"}))


def _ideas(writer: StoreWriter) -> None:
    """Two rule screens over AAA / BBB / CCC (+ earnings context for AAA), for ``/ideas``."""
    common = {"user_id": SITE_USER, "config_hash": "h", "config_version": 1}
    screens = {
        "vrp": [
            ("AAA", "QUALIFIED", 80.0, 1),
            ("BBB", "WATCH", 90.0, 2),
            ("CCC", "REJECT", 0.0, 3),
        ],
        "premium": [("AAA", "QUALIFIED", 100.0, 1), ("CCC", "SKIPPED", None, 2)],
    }
    for config, rows in screens.items():
        run = start_run(screen_job(config, SITE_USER), END, NOW)
        frame = [
            {"instrument_id": f"EQ:{s}", "decision": d, "score": sc, "rank": rank,
             "tie_break": None, "tier": "T1" if d == "QUALIFIED" else "", "class": "",
             "reasons": "iv rank 40 < 50" if d == "WATCH" else "", "config_id": config, **common}
            for s, d, sc, rank in rows
        ]  # fmt: skip
        writer.write_result("rule_screen", END, run.run_id, stamped(frame, END, run.run_id))
        values = [
            {"instrument_id": "EQ:BBB", "user_id": SITE_USER, "config_id": "vrp",
             "criterion_id": "iv_rank", "field": "iv_rank", "mode": "SOFT", "value_num": 40.0,
             "outcome": "NEAR", "distance": 10.0},
            {"instrument_id": "EQ:AAA", "user_id": SITE_USER, "config_id": "vrp",
             "criterion_id": "spread", "field": "spread", "mode": "column", "value_num": 0.05,
             "outcome": "INFO"},
        ]  # fmt: skip
        if config == "vrp":
            frame_values = stamped(values, END, run.run_id)
            writer.write_result("rule_screen_values", END, run.run_id, frame_values)
        writer.save_run(run.finish(NOW, stats={"coverage": "COMPLETE"}))
    _write(writer, "rollups/instrument/earnings@v1", [
        {"instrument_id": "EQ:AAA", "next_earnings_date": date(2022, 12, 1),
         "earnings_time": "pre", "days_to_earnings": 6},
    ])  # fmt: skip


def _backtest(writer: StoreWriter) -> RunRecord:
    run = start_run(backtest_job("sma_trend", "local"), END, NOW)
    days = pd.to_datetime([PREVIOUS, END], utc=True)
    equity = pd.DataFrame({"instrument_id": PORTFOLIO, "ts": days, "equity": [1e5, 1.01e5],
                           "gross_exposure": [0.0, 0.9]})  # fmt: skip
    fills = pd.DataFrame([{"instrument_id": "EQ:AAA", "ts": days[1], "side": "BUY",
                           "quantity": 10.0, "price": 101.0, "commission": 1.0,
                           "multiplier": 1.0}])  # fmt: skip
    with writer.publishing(run.run_id, NOW):
        for name, frame in ((EQUITY, equity), (FILLS, fills)):
            framed = frame.assign(user_id="local", config_id="sma_trend", config_hash="h")
            writer.write_result(name, END, run.run_id, stamped(framed, END, run.run_id, NOW),
                                pending=True)  # fmt: skip
    stats = {"config_id": "sma_trend", "user": "local", "start": "2022-01-03",
             "metrics": {"sharpe": 1.2}, "selection": {"instruments": ["EQ:AAA"]}}  # fmt: skip
    writer.save_run(run.finish(NOW, stats=stats))
    return run


def api_store(source: FixtureSource) -> tuple[ReadStore, dict[str, str]]:
    """-> (the store, ids the tests use: ``nightly``, ``chains``, ``backtest`` run ids)."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    load_golden(task_ctx(writer), source)
    _reference(writer)
    _rollups(writer)
    _market(writer)
    _runs(writer)
    _screen(writer)
    _ideas(writer)
    backtest = _backtest(writer)
    ids = {
        "nightly": writer.runs_for("nightly")[0].run_id,
        "chains": writer.runs_for("option_chains")[0].run_id,
        "backtest": backtest.run_id,
    }
    user = UserContext("local")
    return store_over(backend, FileConfigStore(CONFIG_ROOT), user), ids
