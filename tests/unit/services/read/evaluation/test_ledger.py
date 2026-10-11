"""A run's trade ledger read by run (ADR 0064): the one reader serves a page of it in key order,
a hidden copy's rows before its split only, a personal-licence per-name value as LICENCE to
anyone but the licence holder (by the recorded column licence, never the column name), a pruned
ledger as PRUNED and a run from before the ledger as NOT_STORED; and the partitions the
retention purge spares."""

from datetime import date, timedelta
from typing import Any

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import open_stores
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.evaluation.runs import (
    EdgeRun,
    ledger_keep,
    load_canonical_run,
    load_run_trades,
)
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.edge_schemas import EDGE_TRADES
from algotrade.storage.tables.result_writer import ResultWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.evaluation.conftest import DOCS, END, FROZEN, START, T, stores

USERS = {"user": [{"id": "owner", "role": "admin", "licences": ["personal"]},
                  {"id": "me", "role": "trader"}]}  # fmt: skip


def trade(day: date, iid: str, rank: int, before: bool, **changes: Any) -> dict[str, Any]:
    row = {
        "edge_id": "drift", "user_id": "site", "edge_variant": None, "variant": "momo",
        "role": "screener", "horizon_sessions": 20, "range_from": START, "range_to": END,
        "split_from": FROZEN, "decision_session": day, "instrument_id": iid, "rank": rank,
        "entry_session": day + timedelta(days=1), "status": "won", "hit": True,
        "value": 0.02, "gross_value": 0.021, "score": 3.0, "adv_usd_20d": 1e7,
        "max_drawdown": 0.01, "before_split": before, "delisted": False, "licence": "open",
        "value_licence": "open", "score_licence": "open", "adv_licence": "open",
    }  # fmt: skip
    return {**row, **changes}


ROWS = [
    trade(date(2026, 2, 2), "EQ:B", 2, True),
    trade(date(2026, 2, 2), "EQ:A", 1, True, score_licence="personal", licence="personal"),
    trade(date(2026, 7, 1), "EQ:C", 1, False, status="excluded", hit=None, value=None,
          excluded_reason="NO_ENTRY_BAR"),
]  # fmt: skip


def write_ledger(
    backend: MemoryBackend,
    run_id: str,
    rows: list[dict[str, Any]] | None,
    owner: str = "site",
    end: date = END,
    split: date | None = FROZEN,
    minutes: int = 0,
    count: int | None = None,
) -> None:
    """A committed run of ``drift`` with ``rows`` as its ledger (None: a run from before the
    ledger, no count on its record); ``count`` overrides the recorded row count."""
    writer = ResultWriter(backend)
    at = T + timedelta(minutes=minutes)
    stats: dict[str, Any] = {"edge": "drift", "split_from": split and split.isoformat(),
                             "range": [START.isoformat(), end.isoformat()]}  # fmt: skip
    if rows is not None:
        stats["ledger_rows"] = len(rows) if count is None else count
    record = RunRecord(run_id, f"edge-eval:drift:{owner}", end, at)
    with writer.publishing(run_id, at):
        if rows:
            frame = stamped([{**r, "user_id": owner} for r in rows], end, run_id, at, "edge-eval")
            writer.write_result("edge_trades", end, run_id, frame, pending=True)
        writer.save_run(record.finish(at, complete=True, stats=stats))


def viewer(backend: MemoryBackend, user: str) -> Any:
    configs = MemoryConfigStore({**DOCS, ("site", "settings", "users"): USERS})
    return open_stores(StoreReader(backend), configs, UserContext(user))


def canonical(ctx: Any) -> EdgeRun:
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None
    return run


def test_a_page_of_the_ledger_in_key_order(backend: MemoryBackend) -> None:
    write_ledger(backend, "r1", ROWS)
    ctx = viewer(backend, "owner")
    found = load_run_trades(ctx, canonical(ctx))
    assert (found.unknown, found.total, found.licence) == (None, 3, "personal")
    assert [r.instrument_id for r in found.rows] == ["EQ:A", "EQ:B", "EQ:C"]
    assert found.rows[0].score.value == 3.0  # the licence holder sees the personal score
    gone = found.rows[2]
    assert (gone.status, gone.excluded_reason, gone.value.value, gone.hit) == (
        "excluded", "NO_ENTRY_BAR", None, None
    )  # fmt: skip
    page = load_run_trades(ctx, canonical(ctx), offset=1, limit=1)
    assert [r.instrument_id for r in page.rows] == ["EQ:B"] and page.total == 3
    late = load_run_trades(ctx, canonical(ctx), before_split=False)
    assert [r.instrument_id for r in late.rows] == ["EQ:C"]


def test_a_personal_value_is_licence_to_anyone_but_the_holder(backend: MemoryBackend) -> None:
    write_ledger(backend, "r1", ROWS)
    ctx = viewer(backend, "me")
    first, second, _ = load_run_trades(ctx, canonical(ctx)).rows
    assert (
        isinstance(first.score.unknown, Unknown) and first.score.unknown.code is UnknownCode.LICENCE
    )
    assert first.value.value == 0.02 and first.adv_usd.value == 1e7  # their licences are open
    assert second.score.value == 3.0  # the recorded licence decides, row by row


def test_a_hidden_copys_ledger_is_its_rows_before_the_split(backend: MemoryBackend) -> None:
    write_ledger(backend, "r1", ROWS)
    ctx = viewer(backend, "owner")
    hidden = EdgeRun(**{**canonical(ctx).__dict__, "oos_hidden": True})
    found = load_run_trades(ctx, hidden, before_split=False)  # asking for more changes nothing
    assert {r.instrument_id for r in found.rows} == {"EQ:A", "EQ:B"} and found.total == 2


def test_a_pruned_ledger_and_a_run_from_before_it_are_told_apart(backend: MemoryBackend) -> None:
    write_ledger(backend, "old", None)
    ctx = stores(backend)
    old = load_run_trades(ctx, canonical(ctx)).unknown
    assert old is not None and old.code is UnknownCode.NOT_STORED  # ADR 0056: with its cause
    assert old.cause.links and "old" in old.cause.links[0].message
    write_ledger(backend, "pruned", [], minutes=5, count=12)
    pruned = load_run_trades(ctx, canonical(ctx)).unknown
    assert pruned is not None and pruned.code is UnknownCode.PRUNED
    assert "re-run" in pruned.cause.links[0].message
    write_ledger(backend, "none", [], minutes=9)
    empty = load_run_trades(ctx, canonical(ctx))
    assert (empty.unknown, empty.rows, empty.total) == (None, (), 0)  # it wrote no rows


def test_the_purge_spares_the_canonical_latest_and_cited_runs(backend: MemoryBackend) -> None:
    days = [date(2026, 6, 1) + timedelta(days=7 * k) for k in range(5)]
    write_ledger(backend, "old", ROWS, end=days[1], minutes=1)  # at the frozen split, superseded
    write_ledger(backend, "canon", ROWS, end=days[0], minutes=2)  # a later run of an older range
    write_ledger(backend, "cited", ROWS, end=days[2], split=None, minutes=3)
    write_ledger(backend, "latest", ROWS, end=days[3], split=None, minutes=4)
    write_ledger(backend, "mine", ROWS, owner="me", end=days[4], minutes=5)
    cited = {**DOCS[("site", "edges", "drift")], "status": "evidenced",
             "evidence": {"run_id": "cited", "split_from": FROZEN}}  # fmt: skip
    users = {"user": [{"id": "site", "role": "admin"}, {"id": "me", "role": "trader"}]}
    configs = MemoryConfigStore({**DOCS, ("site", "edges", "drift"): cited,
                                 ("site", "settings", "users"): users})  # fmt: skip
    since = (T + timedelta(days=1)).date()  # every run here finished before it
    keep = ledger_keep(StoreReader(backend), configs, since)
    # "old" is none of them; "mine" is kept though "me" has no config folder (users.toml)
    assert keep == {days[0], days[2], days[3], days[4]}
    # a run that finished within the retention window is kept, whatever its range end
    assert days[1] in ledger_keep(StoreReader(backend), configs, T.date())
    assert EDGE_TRADES.retention_days == 45
