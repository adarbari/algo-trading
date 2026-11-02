"""The ``share-outcomes`` task on a hand-computed bars fixture (ADR 0088, E3c-2a): each eligible
name's walk is written to its start session's partition under the share position key, exits at
closes in declared order (take profit, stop loss, the horizon, a delisting at its last close, a
gap UNMEASURED); ``knowledge_ts`` is the latest bars partition read up to the row's own exit,
never the window's close; a re-run rewrites the same rows (none new, stamps kept); a ``when`` rule
over a catalogue field reads each close's own partition, acts a close later and sets the licence;
one over a field the window cannot read is REFUSED (recorded, the check FAILs), never run as a
rule that never fires; the acceptance check passes on the run's own rows and fails on a name with
a bar at S but no row. A share setup's exit is still refused at load (E3c-2b lifts it), so the
positions here are the loaded edge's with an exit set on them."""

import dataclasses
import tomllib
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.positions.key import parse_position_key
from algotrade.config.edges.positions.spec import ExitSettings
from algotrade.config.edges.positions.templates import SHARES, load_templates
from algotrade.config.strategy.schema import Group, Rule
from algotrade.core.time.calendar import close_time, sessions_ending
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.paths import share_outcomes as task
from algotrade_ingestion.tasks.derived.paths.share_outcomes import (
    TABLE,
    check_share_outcomes,
    compute_share_outcomes,
)
from algotrade_ingestion.tasks.derived.paths.wanted import Wanted, positions_wanted
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import store, write_rows
from tests.helpers.stored_frames import stamped, universe_rows
from tests.unit.config.edges.test_document import document
from tests.unit.config.edges.test_loading import PRESETS

END = date(2026, 10, 2)
NOW = datetime(2026, 10, 3, 6, tzinfo=UTC)
DAYS = sessions_ending(END, 6)  # S = DAYS[2], hold 3: T = END
S = DAYS[2]
NAN = float("nan")
CLOSES = {  # by DAYS index; NaN: no bar
    "EQ:A": [100, 100, 100, 103, 106, 101],  # take profit 5% at 106 (close 2)
    "EQ:B": [100, 100, 100, 98, 94, 99],  # stop loss 5% at 94 (close 2), dipped 6%
    "EQ:C": [100, 100, 100, 101, 102, 103],  # no exit: the horizon, +3%
    "EQ:D": [100, 100, 100, 101, NAN, NAN],  # delisted after close 1
    "EQ:E": [100, 100, 100, 102, NAN, 105],  # a gap before any exit: UNMEASURED
}
SPY = "EQ:SPY"
BENCH = [100, 100, 100, 101, 102, 104]  # the benchmark's closes: in the reference, not the universe
FIELD = "rollup.ibkr_iv@v1.iv30_ibkr"
FIELD_TABLE = "rollups/instrument/ibkr_iv@v1"
OUTCOME = {
    "kind": "excess_return", "horizon_sessions": [3], "benchmark": "SPY",
    "start_offset_sessions": 1, "position": "long_shares",
}  # fmt: skip
TEMPLATES = tomllib.loads((REPO_ROOT / "config/site/positions/templates.toml").read_text())


def _bar_known(day: date) -> datetime:
    return close_time(day) + timedelta(hours=1)


def _bars(writer: StoreWriter, day: date, closes: dict[str, list[float]], run: str) -> None:
    i = DAYS.index(day)
    rows = [
        {"instrument_id": n, "ts": close_time(day), "open": c[i], "high": c[i] * 1.01,
         "low": c[i] * 0.99, "close": c[i], "volume": 1000.0}
        for n, c in closes.items()
        if c[i] == c[i]
    ]  # fmt: skip
    writer.write_table("bars/1d", day, run, stamped(rows, day, run, _bar_known(day)))


def _store() -> tuple[StoreWriter, StoreReader]:
    writer, reader = store()
    for day in DAYS:
        _bars(writer, day, {**CLOSES, SPY: BENCH}, f"bars-{day}")
    reference = [
        {"instrument_id": n, "symbol": n[3:], "asset_class": "EQ",
         "security_type": "COMMON_STOCK", "multiplier": 1.0, "status": "ACTIVE",
         "delisted_on": DAYS[4] if n == "EQ:D" else None}
        for n in (*CLOSES, SPY)
    ]  # fmt: skip
    write_rows(writer, "instruments/reference", DAYS[0], reference)
    write_rows(writer, "universe", DAYS[0], universe_rows([n[3:] for n in CLOSES]))
    return writer, reader


def _field(writer: StoreWriter, day: date, values: dict[str, float]) -> datetime:
    """A personal-licence field partition of ``day``, known two hours after its bars."""
    known = _bar_known(day) + timedelta(hours=1)
    rows = [{"instrument_id": n, "iv30_ibkr": v} for n, v in values.items()]
    writer.write_table(FIELD_TABLE, day, f"f-{day}", stamped(rows, day, f"f-{day}", known))
    return known


def _wanted(**exit: Any) -> list[Wanted]:
    edge = document(schedule="every_session", screeners=[], outcome=OUTCOME)
    docs = {
        **PRESETS,
        ("site", "edges", "drift"): edge,
        ("site", "positions", "templates"): TEMPLATES,
    }
    configs = MemoryConfigStore(docs)
    edges = load_edges(configs)
    edge = next(e for e in edges if e.id == "drift")
    position = dataclasses.replace(edge.outcome.position, exit=ExitSettings(**exit))
    edge = dataclasses.replace(edge, outcome=dataclasses.replace(edge.outcome, position=position))
    return positions_wanted([edge], load_templates(configs), SHARES)


@pytest.fixture(autouse=True)
def _site_features(monkeypatch: pytest.MonkeyPatch) -> None:
    """The site catalogue the licences are read from (the test store holds no documents)."""
    real = site_features(FileConfigStore(REPO_ROOT / "config", local=False))
    monkeypatch.setattr(task, "site_features", lambda _configs: real)


def _run(writer: StoreWriter, wanted: list[Wanted], monkeypatch: pytest.MonkeyPatch,
         clock=lambda: NOW):  # type: ignore[no-untyped-def]  # fmt: skip
    monkeypatch.setattr(task, "positions_wanted", lambda *_: wanted)
    ctx = task_ctx(writer, clock=clock)
    ctx = dataclasses.replace(ctx, configs=MemoryConfigStore(dict(PRESETS)))
    return compute_share_outcomes(ctx, END)


def _rows(reader: StoreReader) -> pd.DataFrame:
    part = reader.table(TABLE, S)
    assert part is not None
    assert set(part["benchmark"]) == {"SPY"}
    return part.set_index("instrument_id").sort_index()


def test_only_share_positions_with_an_exit_are_wanted_one_key_per_hold() -> None:
    wanted = _wanted(take_profit=0.05, stop_loss=0.05)
    assert [w.hold for w in wanted] == [3]
    parsed = parse_position_key(wanted[0].key)
    assert parsed.hold == 3 and parsed.offset == 1 and parsed.tenor_days is None
    assert [x.kind for x in parsed.exits] == ["TAKE_PROFIT", "STOP_LOSS"]
    assert parsed.exits[0].rule.rules()[0].field == "position.move_since_entry_pct"
    assert wanted[0].fields == () and wanted[0].benchmark == "SPY"
    configs = MemoryConfigStore({**PRESETS, ("site", "positions", "templates"): TEMPLATES})
    assert positions_wanted(load_edges(configs), load_templates(configs), SHARES) == []


def test_a_window_is_walked_to_each_exit_and_known_when_its_exit_close_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, reader = _store()
    wanted = _wanted(take_profit=0.05, stop_loss=0.05)
    record = _run(writer, wanted, monkeypatch)
    assert record.status == RunStatus.COMPLETE
    rows = _rows(reader)
    assert set(rows["position_key"]) == {wanted[0].key}
    assert (rows["window_end"].map(pd.Timestamp) == pd.Timestamp(END)).all()
    a, b, c, d, e = (rows.loc[n] for n in CLOSES)
    assert (a["exit_kind"], a["exit_index"], a["gross_return"]) == (
        "TAKE_PROFIT",
        2,
        pytest.approx(0.06),
    )
    assert pd.Timestamp(a["exit_session"]) == pd.Timestamp(DAYS[4]) and a["max_adverse"] == 0.0
    assert (b["exit_kind"], b["gross_return"], b["max_adverse"]) == (
        "STOP_LOSS", pytest.approx(-0.06), pytest.approx(0.06),
    )  # fmt: skip
    assert (c["exit_kind"], c["exit_index"], c["gross_return"]) == (
        "HORIZON",
        3,
        pytest.approx(0.03),
    )
    assert (d["outcome_status"], d["exit_kind"], d["exit_index"]) == ("DELISTED", "DELISTED", 1)
    assert (e["outcome_status"], e["outcome_reason"]) == ("UNMEASURED", "NO_BAR")
    assert pd.isna(e["gross_return"]) and pd.isna(e["exit_session"])
    assert (rows["licence"] == "open").all() and (rows["entry_close"] == 100.0).all()
    # the benchmark over the same S..exit: an excess outcome is scored at the exit
    assert a["benchmark_return"] == pytest.approx(0.02) and c["benchmark_return"] == pytest.approx(
        0.04
    )
    assert pd.isna(e["benchmark_return"])
    # known when the bars through its own exit were: the early exits before the window's end
    assert pd.Timestamp(a["knowledge_ts"]) == pd.Timestamp(_bar_known(DAYS[4]))
    assert pd.Timestamp(c["knowledge_ts"]) == pd.Timestamp(_bar_known(END))
    assert pd.Timestamp(d["knowledge_ts"]) == pd.Timestamp(NOW)  # the delisting: when written
    assert check_share_outcomes(reader, END, None)[0].status == "PASS"  # type: ignore[arg-type]


def test_a_rerun_rewrites_the_same_rows_and_keeps_their_stamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, reader = _store()
    wanted = _wanted(take_profit=0.05, stop_loss=0.05)
    _run(writer, wanted, monkeypatch)
    first = _rows(reader)
    later = NOW + timedelta(days=2)
    _run(writer, wanted, monkeypatch, clock=lambda: later)
    again = _rows(reader)
    pd.testing.assert_frame_equal(first.drop(columns="run_id"), again.drop(columns="run_id"))


def test_a_recheck_that_changes_a_stored_row_stamps_it_no_earlier_than_its_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, reader = _store()
    wanted = _wanted(take_profit=0.05, stop_loss=0.05)
    _run(writer, wanted, monkeypatch)
    # A's close at DAYS[4] restated (as a cleared flag would): the bars' own stamp does not move
    restated = {**CLOSES, SPY: BENCH, "EQ:A": [100, 100, 100, 103, 104, 101]}
    _bars(writer, DAYS[4], restated, "restated")
    later = NOW + timedelta(days=2)
    _run(writer, wanted, monkeypatch, clock=lambda: later)
    rows = _rows(reader)
    assert rows.loc["EQ:A", "exit_kind"] == "HORIZON"
    assert pd.Timestamp(rows.loc["EQ:A", "knowledge_ts"]) == pd.Timestamp(later)
    assert pd.Timestamp(rows.loc["EQ:B", "knowledge_ts"]) == pd.Timestamp(_bar_known(DAYS[4]))


def test_a_field_rule_reads_each_close_acts_a_close_later_and_sets_the_licence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, reader = _store()
    known = {
        day: _field(writer, day, {n: (60.0 if n == "EQ:C" and day == DAYS[3] else 10.0)
                                  for n in CLOSES})
        for day in DAYS[3:]
    }  # fmt: skip
    wanted = _wanted(when=Group("all", (Rule(FIELD, "gt", 50.0),)))
    assert wanted[0].fields == (FIELD,)
    _run(writer, wanted, monkeypatch)
    rows = _rows(reader)
    c = rows.loc["EQ:C"]
    assert (c["exit_kind"], c["exit_index"]) == ("CONDITION", 2)  # seen at close 1, acts at 2
    assert pd.Timestamp(c["knowledge_ts"]) == pd.Timestamp(known[DAYS[4]])
    assert rows.loc["EQ:A", "exit_kind"] == "HORIZON"
    assert set(rows["licence"]) == {"personal"}


def test_a_rule_over_a_field_the_window_cannot_read_is_refused_and_the_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, reader = _store()
    wanted = _wanted(when=Group("all", (Rule(FIELD, "gt", 50.0),)))
    record = _run(writer, wanted, monkeypatch)
    assert "refused" in record.stats[f"SPY:{wanted[0].key}"]
    assert reader.table(TABLE, S) is None  # never run as a rule that never fires
    check = check_share_outcomes(reader, END, None)[0]  # type: ignore[arg-type]
    assert check.status == "FAIL" and "refused" in check.detail


def test_the_check_fails_on_a_name_with_a_bar_at_s_but_no_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, reader = _store()
    _run(writer, _wanted(take_profit=0.05), monkeypatch)
    # a sixth name joins the universe with a bar at S after the run: the count no longer matches
    write_rows(writer, "universe", DAYS[0], universe_rows([*(n[3:] for n in CLOSES), "F"]))
    bars = reader.table("bars/1d", S)
    assert bars is not None
    extra = bars[bars["instrument_id"] == "EQ:A"].assign(instrument_id="EQ:F", run_id="late")
    writer.write_table("bars/1d", S, "late", pd.concat([bars.assign(run_id="late"), extra]))
    check = check_share_outcomes(reader, END, None)[0]  # type: ignore[arg-type]
    assert check.status == "FAIL" and "6 eligible" in check.detail, check.detail


def test_a_window_that_has_not_closed_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    writer, _ = _store()
    with pytest.raises(ValueError, match="has not closed"):
        _run(
            writer,
            _wanted(take_profit=0.05),
            monkeypatch,
            clock=lambda: close_time(END) - timedelta(hours=1),
        )
