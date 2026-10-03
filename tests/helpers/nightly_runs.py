"""Nightly report builders: a summary + run records shaped like the real 2026-10-02 run."""

from datetime import UTC, date, datetime
from typing import Any

from algotrade.storage.runs import RunRecord, RunStatus

D = date(2026, 10, 2)
START = datetime(2026, 10, 3, 13, 26, 14, tzinfo=UTC)
END = datetime(2026, 10, 3, 13, 52, 14, tzinfo=UTC)
SCREEN = {
    "config": "short_premium_liquidity",
    "status": "partial",
    "coverage": "PARTIAL",
    "coverage_pct": 0.8775,
    "decisions": {"LIQUIDITY_RISK": 3299, "QUALIFIED": 324, "REJECT": 65, "UNKNOWN": 515},
    "skipped_reasons": {
        "STALE_DATA: chain is for 2026-09-30": 50,
        "STALE_DATA: chain is for 2026-10-01": 401,
    },
}
QUALITY = {
    "checks": [
        {"name": "bars_fresh", "status": "PASS", "detail": "latest bars session 2026-10-02"},
        {
            "name": "chains_fetch",
            "status": "FAIL",
            "detail": "7.1% failed to fetch (max 5%); of 14 underlyings: OK 4, STALE_DATA 7, "
            "NO_CHAIN 2, NO_STANDARD_SERIES 0, fetch failures 1",
        },
        {
            "name": "chains_stale",
            "status": "WARN",
            "detail": "50.0% stale (max 20%); of 14 underlyings: OK 4, STALE_DATA 7, "
            "NO_CHAIN 2, NO_STANDARD_SERIES 0, fetch failures 1",
        },
    ],
    "failed": ["chains_fetch"],
}
ROLLUPS = {
    "range": ["2026-10-02", "2026-10-02", 1],
    "option_liquidity@v1": {"sessions": 1, "rows": 4203, "no_input": 0, "seconds": 12.49},
    "price_stats@v1": {"sessions": 1, "rows": 12601, "no_input": 0, "seconds": 2.92},
    "failed": [],
}


def summary(status: str = "PARTIAL") -> dict[str, Any]:
    steps = {
        "universe-build": {
            "status": "FAILED",
            "duration_s": 175.109,
            "error": "DataValidationError: instruments/symbol_history: duplicate rows for the "
            "table key",
        },
        "shares": {
            "status": "PARTIAL",
            "duration_s": 11.585,
            "result": {"requested": 17, "with_facts": 5358, "failed_count": 3, "rows": 417993},
        },
        "bars": {"status": "COMPLETE", "duration_s": 0.007, "result": {"sessions": {"STORED": 1}}},
        "chains": {
            "status": "PARTIAL",
            "duration_s": 1237.083,
            "result": {"universe": 14, "statuses": {"OK": 4, "STALE_DATA": 7, "NO_CHAIN": 2}},
        },
        "rollups": {"status": "COMPLETE", "duration_s": 20.033, "result": ROLLUPS},
        "screens": {"status": "PARTIAL", "duration_s": 0.424, "result": {"screens": [SCREEN]}},
        "quality": {"status": "PARTIAL", "duration_s": 0.015, "result": QUALITY},
    }
    return {
        "status": status,
        "sessions": [D.isoformat()],
        "runs": [{"session": D.isoformat(), "status": status, "steps": steps}],
        "steps": {
            "purge-raw": {
                "status": "COMPLETE",
                "duration_s": 0.002,
                "result": {"raw_files_removed": 0},
            }
        },
        "started_at": START.isoformat(),
        "finished_at": END.isoformat(),
        "duration_s": 1559.67,
        "warnings": [{"check": "nightly_duration", "status": "WARN", "detail": "took long"}],
    }


def chains_items() -> dict[str, str]:
    items = {f"EQ:OK{i}": "OK" for i in range(4)}
    items |= {f"EQ:ST{i}": f"STALE_DATA: chain is for 2026-09-{20 + i}" for i in range(7)}
    items |= {"EQ:BBG000QL42S5": "NO_CHAIN", "EQ:BBG008P5VFV1": "NO_CHAIN"}
    items["EQ:CB0"] = (
        "FETCH_ERROR: circuit open for cdn.cboe.com after 10 failures "
        "(https://cdn.cboe.com/api/global/delayed_quotes/options/CB0.json)"
    )
    return items


def record(job: str, items: dict[str, str], status: RunStatus = RunStatus.PARTIAL) -> RunRecord:
    return RunRecord(
        f"{job}-{D.isoformat()}-20261003T133000Z",
        job,
        D,
        START,
        status,
        END,
        items,
        {},
    )


def records() -> dict[tuple[str, str], RunRecord]:
    shares = {
        "0000001750": "OK: 129 facts",
        "0000002230": "NO_SHARE_FACTS",
        "0000759828": "FETCH_ERROR: companyfacts document has no CIK",
        "0000759866": "FETCH_ERROR: companyfacts document has no CIK",
        "0000855886": "FETCH_ERROR: HTTP 503 for https://data.sec.gov/x/0000855886.json",
    }
    return {
        (D.isoformat(), "chains"): record("option_chains", chains_items()),
        (D.isoformat(), "shares"): record("shares", shares),
        (D.isoformat(), "quality"): record(
            "data_quality", {"bars_fresh": "PASS", "chains_fetch": "FAIL", "chains_stale": "WARN"}
        ),
    }
