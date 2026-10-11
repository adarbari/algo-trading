"""The ledger of the verdict's basis (ADR 0064 decisions 2, 10): the basis's rows only, a period
filter, paging and a server sort; excluded picks with their public reason; a personal-licence
value `LICENCE` to a viewer without the licence (and its sort order never disclosing it); a hidden
copy's in-sample rows only; PRUNED and NOT_STORED told apart; live rows from the paper record as
the session's cutoff knew them."""

from datetime import date, datetime
from typing import Any

import pytest

from algotrade.data import StoreReader
from algotrade.services.evaluation.cross_section.detail.trades import EXCLUDED_KINDS
from algotrade.services.read.edge_ledger.trades import EXCLUDED_REASONS, Period, load_edge_trades
from algotrade.services.read.evaluation.edges import Edge, load_edge
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.result_writer import ResultWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.edge_desk.conftest import CUTOFF, KNOWN, store, trade
from tests.unit.services.read.edge_ledger.conftest import LEDGER, context, pick
from tests.unit.services.read.evaluation.conftest import END, FROZEN, write_run
from tests.unit.services.read.evaluation.test_versions import MOVED, write_own_run


@pytest.fixture
def backend() -> MemoryBackend:
    b = MemoryBackend()
    write_run(b, "site1", FROZEN, 0.6, trades=LEDGER)
    return b


def edge_of(ctx: Any) -> Edge:
    found = load_edge(ctx, "drift")
    assert found is not None
    return found


def ids(period: Period, backend: MemoryBackend, user: str = "owner", **kw: Any) -> list[str]:
    ctx = context(backend, user)
    return [r.instrument_id for r in load_edge_trades(ctx, edge_of(ctx), period, **kw).rows]


def test_the_page_is_the_bases_picks_in_key_order(backend: MemoryBackend) -> None:
    ctx = context(backend, "owner")
    page = load_edge_trades(ctx, edge_of(ctx), Period.ALL)
    assert page.basis == "momo, 20 trading days" and page.unknown is None
    assert [r.instrument_id for r in page.rows] == ["EQ:A", "EQ:B", "EQ:C", "EQ:D"]  # not EQ:X
    assert (page.total, page.licence, page.oos_hidden) == (4, "personal", False)
    gone = page.rows[2]
    assert (gone.status, gone.excluded_reason, gone.value.value) == (
        "excluded",
        "NO_ENTRY_BAR",
        None,
    )


def test_a_period_and_a_page_filter_the_rows(backend: MemoryBackend) -> None:
    assert ids(Period.IN_SAMPLE, backend) == ["EQ:A", "EQ:B"]
    assert ids(Period.OUT_OF_SAMPLE, backend) == ["EQ:C", "EQ:D"]
    ctx = context(backend, "owner")
    second = load_edge_trades(ctx, edge_of(ctx), Period.ALL, page=2, limit=3)
    assert [r.instrument_id for r in second.rows] == ["EQ:D"] and second.total == 4


def test_a_server_sort_orders_the_whole_ledger_not_the_page(backend: MemoryBackend) -> None:
    ctx = context(backend, "owner")
    top = load_edge_trades(ctx, edge_of(ctx), Period.ALL, sort="value", descending=True, limit=2)
    assert [r.instrument_id for r in top.rows] == ["EQ:B", "EQ:A"]  # 0.04, 0.02; None last


def test_a_personal_value_is_licence_to_a_viewer_without_it(backend: MemoryBackend) -> None:
    ctx = context(backend, "me")
    rows = load_edge_trades(ctx, edge_of(ctx), Period.ALL).rows
    first = rows[0]  # EQ:A: its score's recorded licence is personal
    assert (
        isinstance(first.score.unknown, Unknown) and first.score.unknown.code is UnknownCode.LICENCE
    )
    assert (
        first.value.value == 0.02 and rows[1].score.value == 6.0
    )  # the recorded licence decides, per row
    owner = context(backend, "owner")
    assert load_edge_trades(owner, edge_of(owner), Period.ALL).rows[0].score.value == 3.0


def test_a_sort_never_discloses_a_value_the_viewer_may_not_see(backend: MemoryBackend) -> None:
    ctx = context(backend, "me")
    by_score = load_edge_trades(ctx, edge_of(ctx), Period.IN_SAMPLE, sort="score", descending=True)
    assert [r.instrument_id for r in by_score.rows] == [
        "EQ:B",
        "EQ:A",
    ]  # A's score sorts as missing
    held = context(backend, "owner")
    low = load_edge_trades(held, edge_of(held), Period.IN_SAMPLE, sort="score")
    assert [r.instrument_id for r in low.rows] == ["EQ:A", "EQ:B"]


def run_record(backend: MemoryBackend, run_id: str) -> RunRecord:
    record = StoreReader(backend).run(run_id)
    assert record is not None
    return record


def test_a_pruned_ledger_and_one_never_written_are_told_apart() -> None:
    old, pruned = MemoryBackend(), MemoryBackend()
    write_run(old, "old", FROZEN, 0.6)  # a run from before the ledger: no count on its record
    write_run(pruned, "p", FROZEN, 0.6, trades=[])
    record = run_record(pruned, "p")
    record.stats["ledger_rows"] = 9  # it wrote nine rows the retention purge has removed
    ResultWriter(pruned).save_run(record)
    ctx = context(old)
    found = load_edge_trades(ctx, edge_of(ctx))
    assert found.unknown is not None and found.unknown.code is UnknownCode.NOT_STORED
    ctx = context(pruned)
    found = load_edge_trades(ctx, edge_of(ctx))
    assert found.unknown is not None and found.unknown.code is UnknownCode.PRUNED
    assert found.rows == () and found.basis == "momo, 20 trading days"


def test_an_edge_with_no_official_run_has_no_ledger() -> None:
    ctx = context(MemoryBackend())
    page = load_edge_trades(ctx, edge_of(ctx))
    assert page.unknown is not None and page.unknown.code is UnknownCode.NOT_RUN and page.rows == ()


def test_a_hidden_copys_ledger_is_its_in_sample_rows(backend: MemoryBackend) -> None:
    write_own_run(backend)
    record = run_record(backend, "mine1")
    rows = [
        {**pick(FROZEN, "EQ:A", 1, True, edge_id="mine", split_from=MOVED), "user_id": "me"},
        {**pick(END, "EQ:Z", 1, False, edge_id="mine", split_from=MOVED), "user_id": "me"},
    ]
    frame = stamped(rows, END, "mine1", record.started_at, "edge-eval")
    writer = ResultWriter(backend)
    with writer.publishing("mine1", record.started_at):
        writer.write_result("edge_trades", END, "mine1", frame, pending=True)
        record.stats["ledger_rows"] = 2
        writer.save_run(record)
    docs = {("me", "edges", "mine"): {"extends": "drift", "screeners": ["momo"]}}
    ctx = context(backend, "me", docs)
    edge = load_edge(ctx, "mine")
    assert edge is not None and edge.oos_hidden
    everything = load_edge_trades(ctx, edge, Period.ALL)
    assert [r.instrument_id for r in everything.rows] == ["EQ:A"] and everything.oos_hidden
    late = load_edge_trades(ctx, edge, Period.OUT_OF_SAMPLE)
    assert (late.rows, late.total, late.oos_hidden) == ((), 0, True)


def test_the_live_period_reads_the_paper_record_as_the_cutoff_knew_it(
    backend: MemoryBackend,
) -> None:
    sell = FROZEN.replace(month=9, day=30)
    store(backend, [trade("EQ:L", FROZEN.replace(month=9, day=1), "won", sell=sell),
                    trade("EQ:S", FROZEN.replace(month=9, day=1), "skipped", sell=sell, rank=2),
                    trade("EQ:O", FROZEN.replace(month=9, day=1), "won", sell=sell, rank=3,
                          screener="other")])  # fmt: skip
    ctx = context(backend, "me", cutoff=CUTOFF)
    page = load_edge_trades(ctx, edge_of(ctx), Period.LIVE)
    assert [r.instrument_id for r in page.rows] == ["EQ:L", "EQ:S"]  # the basis's screen only
    won, skipped = page.rows
    assert (won.source, won.status, won.hit, won.value.value) == ("live", "won", True, 0.02)
    assert (skipped.status, skipped.excluded_reason, skipped.value.value) == (
        "excluded",
        "SKIPPED",
        None,
    )
    assert won.before_split is False and won.score.value is None
    # a settlement a later night recorded is not read for the earlier session
    late = datetime(2026, 10, 6, tzinfo=KNOWN.tzinfo)
    store(backend, [trade("EQ:N", FROZEN.replace(month=9, day=2), "won", sell=sell)], late)
    again = load_edge_trades(ctx, edge_of(ctx), Period.LIVE)
    assert [r.instrument_id for r in again.rows] == ["EQ:L", "EQ:S"]


def test_every_public_reason_the_ledger_writes_is_one_the_guide_names() -> None:
    assert set(EXCLUDED_KINDS.values()) <= set(EXCLUDED_REASONS)  # the writer's kinds, ADR 0056


def test_a_page_below_the_first_is_the_first(backend: MemoryBackend) -> None:
    ctx = context(backend, "owner")
    page = load_edge_trades(ctx, edge_of(ctx), Period.ALL, page=-3, limit=2)
    assert page.page == 1 and [r.instrument_id for r in page.rows] == ["EQ:A", "EQ:B"]


def test_the_live_total_counts_every_settled_row_beyond_the_lookback(
    backend: MemoryBackend,
) -> None:
    old = date(2024, 1, 2)  # well over 400 days before the session
    store(backend, [trade("EQ:OLD", old, "won", sell=date(2024, 2, 1))])
    ctx = context(backend, "me", cutoff=CUTOFF)
    page = load_edge_trades(ctx, edge_of(ctx), Period.LIVE)
    assert [r.instrument_id for r in page.rows] == ["EQ:OLD"] and page.total == 1


def test_a_hidden_copys_live_trades_are_served() -> None:
    backend = MemoryBackend()
    write_own_run(backend)
    store(backend, [trade("EQ:F", date(2026, 9, 1), "won", sell=date(2026, 9, 30), edge="mine",
                          user="me")])  # fmt: skip
    docs = {("me", "edges", "mine"): {"extends": "drift", "screeners": ["momo"]}}
    ctx = context(backend, "me", docs, cutoff=CUTOFF)
    edge = load_edge(ctx, "mine")
    assert edge is not None and edge.oos_hidden
    page = load_edge_trades(ctx, edge, Period.LIVE)
    assert [r.instrument_id for r in page.rows] == ["EQ:F"] and not page.oos_hidden
