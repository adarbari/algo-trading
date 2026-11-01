"""The ``option-outcomes`` task on stored chains priced by Black-Scholes at a known vol (ADR 0088,
design 2.5, E4): a position's window is written to its start session's partition under a
``position_key`` of its resolved legs, ``knowledge_ts`` the latest chain and field partition read
up to the row's own exit (an early exit is known before the window's end, never the write time);
two exit rules are two keys and both are stored; an exit rule over a catalogue field reads each
close's own partition, takes the strictest licence into the row, and one over a field with no rows
in range is REFUSED (recorded, the check FAILs, the other positions still write); a stale chain on a
session of the window is an UNMEASURED row with the session in its reason; every start session of a
run of window ends is written (an entry wait); a window starting before the first stored chain is
not computed; one not yet closed is refused; the acceptance check passes on the run's own rows and
fails on a name that has a chain but no row."""

import dataclasses
import tomllib
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.positions.key import parse_position_key
from algotrade.config.edges.positions.templates import load_templates
from algotrade.core.time.calendar import close_time, sessions_ending
from algotrade.features.site import site_features
from algotrade.quant.black_scholes import price
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived import option_outcomes as outcomes_task
from algotrade_ingestion.tasks.derived.option_outcomes import (
    TABLE,
    check_option_outcomes,
    compute_option_outcomes,
    positions_wanted,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import store
from tests.helpers.stored_frames import stamped
from tests.unit.config.edges.test_document import document
from tests.unit.config.edges.test_loading import PRESETS

END = date(2026, 10, 14)
NOW = datetime(2026, 10, 20, tzinfo=UTC)
DAYS = sessions_ending(END, 7)  # the first stored chain is DAYS[0]
EXPIRY = date(2026, 11, 20)
VOL, HALF = 0.30, 0.05
A, B = "EQ:A", "EQ:B"
PERSONAL = "rollup.ibkr_iv@v1.iv30_ibkr"
PERSONAL_TABLE = "rollups/instrument/ibkr_iv@v1"
OUTCOME = {
    "kind": "option_pnl", "horizon_sessions": [2], "benchmark": "none", "tenor_days": 30,
    "start_offset_sessions": 1, "position": "short_put", "strike_delta": 0.25,
}  # fmt: skip
TEMPLATES = tomllib.loads((REPO_ROOT / "config/site/positions/templates.toml").read_text())


def _configs(variants: list[dict[str, Any]] | None = None, **outcome: Any) -> MemoryConfigStore:
    doc = document(schedule="every_session", screeners=[], outcome={**OUTCOME, **outcome})
    if variants:
        doc["variants"] = variants
    docs = {**PRESETS, ("site", "edges", "drift"): doc,
            ("site", "positions", "templates"): TEMPLATES}  # fmt: skip
    return MemoryConfigStore(docs)


def _known(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=23)


def _chains(
    skip_status: dict[tuple[str, date], str] | None = None,
) -> tuple[StoreWriter, StoreReader]:
    """A chain per session for A and B (spot 100 + day index), each OK unless overridden."""
    writer, reader = store()
    for i, day in enumerate(DAYS):
        statuses, unders, options = [], [], []
        for name in (A, B):
            spot = 100.0 + i + (5 if name == B else 0)
            status = (skip_status or {}).get((name, day), "OK")
            statuses.append({"instrument_id": name, "symbol": name[3:], "status": status,
                             "tier": "core"})  # fmt: skip
            stamp = pd.Timestamp(_known(day))
            unders.append({"instrument_id": name, "symbol": name[3:], "ts": stamp, "price": spot,
                           "close": spot, "volume": 1e6, "iv30": VOL})  # fmt: skip
            t = (EXPIRY - day).days / 365
            for strike in (80.0, 85.0, 90.0, 95.0, 100.0, 105.0, 110.0):
                for right in ("C", "P"):
                    mid = float(price(spot, strike, t, 0.0, 0.0, VOL, right == "C"))
                    options.append({
                        "instrument_id": f"OPT:{name}:{right}{int(strike)}", "underlying_id": name,
                        "ts": pd.Timestamp(_known(day)), "expiry": EXPIRY, "right": right,
                        "strike": strike, "bid": max(mid - HALF, 0.01), "ask": mid + HALF,
                        "volume": 10.0, "open_interest": 100.0, "iv": VOL, "delta": 0.5,
                    })  # fmt: skip
        for table, rows in (("chains/status", statuses), ("chains/underlying_quotes", unders),
                            ("chains/option_quotes", options)):  # fmt: skip
            frame = stamped(rows, day, f"c-{day}", _known(day), "test")
            writer.write_table(table, day, f"c-{day}-{table}", frame)
    return writer, reader


def _field(writer: StoreWriter, day: date, values: dict[str, float]) -> datetime:
    """A personal-licence field partition of ``day``, known an hour after the chains."""
    known = _known(day) + timedelta(hours=1)
    rows = [{"instrument_id": n, "iv30_ibkr": v} for n, v in values.items()]
    writer.write_table(PERSONAL_TABLE, day, f"f-{day}", stamped(rows, day, f"f-{day}", known))
    return known


@pytest.fixture(autouse=True)
def _site_features(monkeypatch: pytest.MonkeyPatch) -> None:
    """The site catalogue the licences are read from (the test store holds only edge documents)."""
    real = site_features(FileConfigStore(REPO_ROOT / "config", local=False))
    monkeypatch.setattr(outcomes_task, "site_features", lambda _configs: real)


def _ctx(writer: StoreWriter, configs: MemoryConfigStore, clock=lambda: NOW):  # type: ignore[no-untyped-def]
    return dataclasses.replace(task_ctx(writer, clock=clock), configs=configs)


def _rows(reader: StoreReader) -> pd.DataFrame:
    parts = [reader.table(TABLE, d) for d in reader.dates(TABLE)]
    return pd.concat([p for p in parts if p is not None], ignore_index=True)


def _wanted(configs: MemoryConfigStore) -> list:
    return positions_wanted(load_edges(configs), load_templates(configs))


def test_positions_come_from_the_open_edge_documents_one_key_per_exit_rule_and_hold() -> None:
    (only,) = _wanted(_configs())
    assert only.hold == 2 and only.rules == () and only.fields == ()
    parsed = parse_position_key(only.key)
    assert parsed.collateral == "cash_secured" and parsed.legs[0].delta == 0.25
    both = _wanted(
        _configs(variants=[{"id": "tp", "outcome": {"exit": {"take_profit": 0.5}}}],
                 horizon_sessions=[2, 5])
    )  # fmt: skip
    assert [(w.hold, len(w.rules)) for w in both] == [(2, 0), (2, 1), (5, 0), (5, 1)]
    assert len({w.key for w in both}) == 4
    assert _wanted(MemoryConfigStore({})) == []


def test_a_window_is_written_to_its_start_partition_known_when_its_exit_chain_was() -> None:
    writer, reader = _chains()
    record = compute_option_outcomes(_ctx(writer, _configs()), END)
    assert record.status == RunStatus.COMPLETE, record.stats
    (wanted,) = _wanted(_configs())
    start = sessions_ending(END, 3)[0]
    part = reader.table(TABLE, start)
    assert part is not None and set(part["instrument_id"]) == {A, B}
    a = part[part["instrument_id"] == A].iloc[0]
    assert (a["position_key"], a["hold_sessions"], a["window_end"]) == (wanted.key, 2, END)
    assert (a["price_source"], a["licence"]) == ("cboe", "open")
    assert a["outcome_status"] == "COMPLETE" and a["exit_kind"] == "HORIZON"
    assert a["exit_basis"] == "QUOTE" and a["exit_unknown_closes"] == 0
    assert pd.Timestamp(a["ts"]) == pd.Timestamp(close_time(start))
    assert pd.Timestamp(a["knowledge_ts"]) == pd.Timestamp(_known(END))  # not the write time (NOW)
    assert list(a["leg_kinds"]) == ["option"] and list(a["leg_rights"]) == ["P"]
    assert a["entry_oi_min"] == 100.0 and a["collateral"] == next(iter(a["leg_strikes"]))
    assert pd.isna(a["regt_margin"]) and pd.isna(a["dividend_forgone"])
    assert record.stats[wanted.key]["unmeasured"] == 0


def test_two_exit_rules_are_two_keys_and_an_early_exit_is_known_when_its_close_was() -> None:
    configs = _configs(variants=[{"id": "tp", "outcome": {"exit": {"take_profit": 0.05}}}])
    writer, reader = _chains()
    ctx = _ctx(writer, configs)
    record = compute_option_outcomes(ctx, END)
    held, taken = _wanted(configs)  # sorted by key: the one without exit rules sorts first or not
    if held.rules:
        held, taken = taken, held
    start = sessions_ending(END, 3)[0]
    rows = _rows(reader)
    rows = rows[rows["window_end"] == END]
    assert set(rows["position_key"]) == {held.key, taken.key} and len(rows) == 4
    a_held = rows[(rows["position_key"] == held.key) & (rows["instrument_id"] == A)].iloc[0]
    a_took = rows[(rows["position_key"] == taken.key) & (rows["instrument_id"] == A)].iloc[0]
    assert a_held["exit_kind"] == "HORIZON" and a_took["exit_kind"] == "TAKE_PROFIT"
    first = sessions_ending(END, 2)[0]  # the session after S: the spot rose, the put lost value
    assert a_took["exit_session"] == first and a_took["pnl_mid"] > 0
    assert pd.Timestamp(a_took["knowledge_ts"]) == pd.Timestamp(_known(first))  # stops at its exit
    assert pd.Timestamp(a_held["knowledge_ts"]) == pd.Timestamp(_known(END))
    assert check_option_outcomes(reader, END, ctx.settings)[0].status == "PASS", record.stats
    assert start < first < END


def test_a_catalogue_field_is_read_per_close_from_its_own_partition_and_sets_the_licence() -> None:
    when = {"all": [{"field": PERSONAL, "op": "gt", "value": 0.5}]}
    configs = _configs(exit={"when": when})
    s0, s1 = sessions_ending(END, 3)[0], sessions_ending(END, 2)[0]
    writer, reader = _chains()
    known_s1 = _field(writer, s1, {A: 0.9, B: 0.1})  # high only at the first close, for A
    _field(writer, END, {A: 0.0, B: 0.0})
    ctx = _ctx(writer, configs)
    record = compute_option_outcomes(ctx, END)
    assert record.status == RunStatus.COMPLETE, record.stats
    rows = _rows(reader)
    rows = rows[rows["window_end"] == END].set_index("instrument_id")
    assert rows.at[A, "exit_kind"] == "CONDITION"  # observed at S+1, acts at S+2 (the cap)
    assert rows.at[B, "exit_kind"] == "HORIZON" and rows["licence"].eq("personal").all()
    assert rows.at[A, "exit_unknown_closes"] == 0
    # the exit is at the last close, so the row knows both fields' partitions
    assert pd.Timestamp(rows.at[A, "knowledge_ts"]) == pd.Timestamp(
        max(_known(END), known_s1, _known(END) + timedelta(hours=1))
    )
    assert s0 < s1


def test_a_close_with_no_field_partition_is_counted_unknown_and_never_fires() -> None:
    when = {"all": [{"field": PERSONAL, "op": "gt", "value": 0.5}]}
    writer, reader = _chains()
    _field(writer, END, {A: 0.9, B: 0.9})  # only the last close has a partition
    compute_option_outcomes(_ctx(writer, _configs(exit={"when": when})), END)
    rows = _rows(reader)
    rows = rows[rows["window_end"] == END]
    assert set(rows["exit_kind"]) == {"HORIZON"}  # observed at the cap: it cannot act after it
    assert set(rows["exit_unknown_closes"]) == {1}  # the first close had no value to read


def test_a_rule_over_a_field_with_no_rows_in_range_is_refused_and_the_check_fails() -> None:
    when = {"all": [{"field": PERSONAL, "op": "gt", "value": 0.5}]}
    configs = _configs(variants=[{"id": "w", "outcome": {"exit": {"when": when}}}])
    writer, reader = _chains()
    ctx = _ctx(writer, configs)
    record = compute_option_outcomes(ctx, END)
    plain, gated = _wanted(configs)
    if plain.rules:
        plain, gated = gated, plain
    assert (
        record.items[gated.key].startswith("REFUSED: ")
        and "no stored partition" in (record.items[gated.key])
    )
    assert "refused" in record.stats[gated.key]
    rows = _rows(reader)
    assert set(rows["position_key"]) == {plain.key}  # the other position still wrote
    (failed,) = check_option_outcomes(reader, END, ctx.settings)
    assert failed.status == "FAIL" and "refused" in failed.detail


def test_skip_report_in_life_is_refused_until_the_report_read_lands() -> None:
    writer, reader = _chains()
    ctx = _ctx(writer, _configs(skip_report_in_life=True))
    record = compute_option_outcomes(ctx, END)
    (key,) = (w.key for w in _wanted(_configs(skip_report_in_life=True)))
    assert record.items[key].startswith("REFUSED: skip_report_in_life")
    assert reader.dates(TABLE) == []
    assert check_option_outcomes(reader, END, ctx.settings)[0].status == "FAIL"


def test_every_start_session_of_a_run_of_window_ends_is_written_for_every_name() -> None:
    """An entry wait needs a row at each S it may enter on (G9-M3): the writer already writes
    every S for every name whose chain is OK, so three window ends give three start sessions."""
    writer, reader = _chains()
    ends = DAYS[-3:]
    compute_option_outcomes(_ctx(writer, _configs()), END, start=ends[0], end=END)
    (wanted,) = _wanted(_configs())
    starts = sessions_ending(END, 5)[:3]  # S for T in the last three sessions, hold 2
    for day in starts:
        part = reader.table(TABLE, day)
        assert part is not None, day
        mine = part[part["position_key"] == wanted.key]
        assert set(mine["instrument_id"]) == {A, B}, day


def test_a_stale_hedge_session_costs_only_the_hedged_pnl_and_a_stale_exit_the_row() -> None:
    mid = sessions_ending(END, 2)[0]  # the session before the exit
    writer, reader = _chains(
        {(B, mid): "STALE_DATA: chain is for 2026-10-08", (A, END): "STALE_DATA"}
    )
    record = compute_option_outcomes(_ctx(writer, _configs()), END)
    rows = _rows(reader)
    rows = rows[rows["window_end"] == END]
    b = rows[rows["instrument_id"] == B].iloc[0]
    assert b["outcome_status"] == "COMPLETE" and pd.notna(b["pnl_mid"])
    assert pd.isna(b["pnl_hedged_mid"])  # a hedge session lacked its chain
    a = rows[rows["instrument_id"] == A].iloc[0]  # the exit chain itself is stale
    assert a["outcome_status"] == "UNMEASURED" and a["outcome_reason"] == f"STALE_CHAIN:{END}"
    assert pd.isna(a["pnl_mid"]) and pd.isna(a["exit_kind"])
    (key,) = (w.key for w in _wanted(_configs()))
    assert record.stats[key]["reasons"] == {"STALE_CHAIN": 1}


def test_a_window_before_the_first_stored_chain_is_not_computed() -> None:
    writer, reader = _chains()
    configs = _configs(horizon_sessions=[2, 21])
    record = compute_option_outcomes(_ctx(writer, configs), END)
    long_key = next(w.key for w in _wanted(configs) if w.hold == 21)
    assert record.items[long_key] == "BEFORE_HISTORY"
    assert set(_rows(reader)["hold_sessions"]) == {2}


def test_a_window_that_has_not_closed_is_refused() -> None:
    writer, _ = _chains()
    early = lambda: close_time(END) - timedelta(hours=1)  # noqa: E731
    with pytest.raises(ValueError, match="has not closed"):
        compute_option_outcomes(_ctx(writer, _configs(), early), END)


def test_the_acceptance_check_passes_and_fails_on_a_name_with_a_chain_but_no_row() -> None:
    writer, reader = _chains()
    ctx = _ctx(writer, _configs())
    compute_option_outcomes(ctx, END)
    (passed,) = check_option_outcomes(reader, END, ctx.settings)
    assert passed.status == "PASS", passed.detail
    # a third name gets an OK chain at the entry after the run: the count no longer matches
    start = sessions_ending(END, 3)[0]
    extra = stamped(
        [{"instrument_id": "EQ:C", "symbol": "C", "status": "OK", "tier": "core"}],
        start, "late", _known(start), "test",
    )  # fmt: skip
    status = reader.table("chains/status", start)
    assert status is not None
    writer.write_table("chains/status", start, "late-status", pd.concat([status, extra]))
    (failed,) = check_option_outcomes(reader, END, ctx.settings)
    assert failed.status == "FAIL" and "OK chains" in failed.detail
    assert check_option_outcomes(reader, date(2026, 10, 15), ctx.settings)[0].status == "FAIL"


def test_the_writer_never_starts_before_the_first_cboe_session_whatever_else_is_stored() -> None:
    """A status partition from before 2026-10-02 (bought history's days) must not lower the first
    stored session below the cutover: a window that would start there is not computed."""
    writer, _ = _chains()
    day = date(2026, 10, 1)
    rows = [{"instrument_id": A, "symbol": "A", "status": "OK", "tier": "core"}]
    writer.write_table("chains/status", day, "old", stamped(rows, day, "old", _known(day), "test"))
    configs = _configs(horizon_sessions=[9])  # S = 2026-10-01 for the window ending END
    record = compute_option_outcomes(_ctx(writer, configs), END)
    (key,) = (w.key for w in _wanted(configs))
    assert record.items[key] == "BEFORE_HISTORY"
