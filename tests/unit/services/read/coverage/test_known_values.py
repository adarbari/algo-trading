"""``load_known_coverage``: the fundamentals share count by security type and the gaps of
operating companies, from the nightly's coverage check alone. An ETF with a row and no value is
rows without known (the green grid at 47%), a record without the breakdown (a retry, an older
record) is skipped, and nothing for the session is NOT_RUN, never an earlier session's."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

from algotrade.data import StoreReader
from algotrade.services.read.availability.cause import CauseLevel
from algotrade.services.read.availability.data_status import FUNDAMENTALS_FEATURE, check_name
from algotrade.services.read.context import ReadContext
from algotrade.services.read.coverage.known_values import KnownGap, load_known_coverage
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import start_run

DAY = date(2026, 10, 2)
DONE = datetime(2026, 10, 3, 2, tzinfo=UTC)
BREAKDOWN = {
    "by_type": [
        {"security_type": "COMMON_STOCK", "names": 5000, "rows": 5000, "known": 4800},
        {"security_type": "ETF", "names": 4000, "rows": 4000, "known": 0},
    ],
    "causes": {"BLANK_CHECK": 30, "NO_FACTS": 160, "NO_ROW": 10},
}


def _step(data: dict[str, Any]) -> dict[str, Any]:
    check = {"name": check_name(FUNDAMENTALS_FEATURE), "status": "PASS", "data": data}
    return {"rollups": {"checks": [check]}}


def _record(
    backend: MemoryBackend, day: date, steps: dict[str, Any], hours: int, run_id: str
) -> None:
    run = start_run("nightly", day, DONE - timedelta(hours=hours))
    run.run_id = run_id
    run.stats = {"steps": steps}
    backend.runs.save(run)


def _load(backend: MemoryBackend) -> Any:
    ctx = SimpleNamespace(reader=StoreReader(backend), session=SimpleNamespace(date=DAY))
    return load_known_coverage(cast(ReadContext, ctx))


def test_etf_rows_are_not_known_values_and_operating_gaps_have_causes() -> None:
    backend = MemoryBackend()
    _record(backend, DAY, _step({"cells": [], "breakdown": BREAKDOWN}), 3, "night")
    found = _load(backend)
    assert found.unknown is None and found.run_id == "night"
    etf = next(t for t in found.by_type if t.security_type == "ETF")
    assert (etf.rows, etf.known, etf.share) == (4000, 0, 0.0)  # a green row grid, no value
    stock = next(t for t in found.by_type if t.security_type == "COMMON_STOCK")
    assert stock.share == 0.96
    assert [(g.gap, g.names) for g in found.gaps] == [
        (KnownGap.BLANK_CHECK, 30),
        (KnownGap.NO_FACTS, 160),
        (KnownGap.NO_ROW, 10),
    ]


def test_the_newest_record_holding_the_breakdown_wins_over_a_retry_without_it() -> None:
    backend = MemoryBackend()
    _record(backend, DAY, _step({"cells": [], "breakdown": BREAKDOWN}), 4, "first")
    _record(backend, DAY, _step({"cells": []}), 1, "retry")  # carried over, no breakdown
    assert _load(backend).run_id == "first"


def test_a_session_with_no_breakdown_is_not_run_never_an_earlier_session() -> None:
    backend = MemoryBackend()
    _record(backend, DAY - timedelta(days=1), _step({"breakdown": BREAKDOWN}), 3, "yesterday")
    _record(backend, DAY, _step({"cells": []}), 3, "old-format")
    found = _load(backend)
    assert found.run_id is None and found.by_type == () and found.gaps == ()
    assert found.unknown is not None and found.unknown.code is UnknownCode.NOT_RUN
    assert found.unknown.cause.leaf.level is CauseLevel.RUN  # the chain is admin-only
