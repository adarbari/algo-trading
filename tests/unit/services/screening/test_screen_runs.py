"""ScreenRun and ScreenPick (ADR 0077 amendment (c)): the run's object rows are framed from the
rule screen's own rows and published in its one atomic block, so they cannot differ from it."""

from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import DataValidationError
from algotrade.services.configs import resolve_config
from algotrade.services.licences import HARNESS_ALL
from algotrade.services.read.screens.results import _compare
from algotrade.services.screening import run as run_module
from algotrade.services.screening.rule_results import (
    Lineage,
    Stamp,
    change_counts,
    picks_frame,
    rule_frames,
)
from algotrade.services.screening.run import run_screener
from algotrade.storage.tables.schemas import SCREEN_PICKS, SCREEN_RUNS
from algotrade.strategies.screeners.rules.summary import summarise
from tests.helpers.stored_frames import T0, stamped
from tests.unit.services.screening.test_rule_screens import DAY, LIQ, configs, seeded

PREVIOUS = DAY - timedelta(days=1)
FEATURES = "rollups/instrument/option_liquidity@v1"
OPEN_ONLY = frozenset({"open"})


def previous_session(writer: Any) -> None:
    """A session before ``DAY`` on which AAA fails the price and ETF1 qualifies."""
    rows = [
        {"instrument_id": "EQ:AAA", "underlying_price": 40.0, "chain_oi": 5000, "put_tier": "A"},
        {"instrument_id": "EQ:BBB", "underlying_price": 60.0, "chain_oi": 700, "put_tier": "C"},
        {"instrument_id": "EQ:ETF1", "underlying_price": 80.0, "chain_oi": 5000, "put_tier": "B"},
    ]
    writer.write_table(FEATURES, PREVIOUS, "f0", stamped(rows, PREVIOUS, "f0"))


def table(reader: Any, name: str, day: date = DAY) -> pd.DataFrame:
    frame = reader.table(f"results/{name}", day)
    assert frame is not None
    return frame


def config() -> Any:
    return resolve_config(configs(), "big_liquid", UserContext(SITE_USER))


def test_the_run_objects_equal_the_rule_screen_they_come_from() -> None:
    """Equivalence: screen_runs row == summarise(rule_screen rows) == the run record's summary;
    screen_picks == rule_screen filtered to picked or PAUSED, every column equal."""
    reader, writer = seeded()
    outcome = run_screener(reader, writer, config(), DAY, now=T0, held=HARNESS_ALL)
    screen, runs, picks = (table(reader, n) for n in ("rule_screen", "screen_runs", "screen_picks"))
    (row,) = runs.to_dict("records")
    assert outcome.rules is not None
    summary = outcome.rules.summary
    assert summary == summarise(outcome.rules.rows)
    assert (row["rows"], row["passed"]) == (summary.rows, summary.passed) == (len(screen), 1)
    assert dict(zip(row["decision_names"], row["decision_counts"], strict=True)) == dict(
        summary.decisions
    )
    (record,) = reader.runs("screen-big_liquid-site", DAY)
    assert dict(summary.decisions) == record.stats["summary"]["decisions"]
    assert (row["picked"], row["paused"]) == (2, 0)  # QUALIFIED and WATCH are picks
    wanted = screen[screen["decision"].isin(["QUALIFIED", "WATCH"])]
    columns = [c.name for c in SCREEN_PICKS.columns]
    pd.testing.assert_frame_equal(
        picks.sort_values("instrument_id").reset_index(drop=True),
        wanted[columns].sort_values("instrument_id").reset_index(drop=True),
        check_dtype=False,
    )
    assert set(picks["run_id"]) == set(runs["run_id"]) == {outcome.run_id}


def test_a_paused_pick_is_in_screen_picks_and_counted_not_picked() -> None:
    screen = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B", "EQ:C"],
            "user_id": "site",
            "config_id": "s",
            "config_version": 1,
            "decision": ["PAUSED", "REJECT", "QUALIFIED"],
            "score": [1.0, 0.0, 2.0],
            "rank": [2, 3, 1],
            "regime": "Storm",
            "size_multiplier": 0.0,
            "session_date": DAY,
            "knowledge_ts": pd.Timestamp(T0),
            "source": "s",
            "run_id": "r",
        }
    )
    assert list(picks_frame(screen)["instrument_id"]) == ["EQ:A", "EQ:C"]


def test_the_changes_are_frozen_at_write_against_the_previous_run() -> None:
    reader, writer = seeded()
    previous_session(writer)
    first = run_screener(reader, writer, config(), PREVIOUS, now=T0, held=HARNESS_ALL)
    second = run_screener(reader, writer, config(), DAY, now=T0, held=HARNESS_ALL)
    (before,) = table(reader, "screen_runs", PREVIOUS).to_dict("records")
    assert pd.isna(before["previous_run_id"]) and pd.isna(before["new_picks"])  # none, not 0
    (row,) = table(reader, "screen_runs").to_dict("records")
    assert row["previous_run_id"] == first.run_id and row["previous_session"] == PREVIOUS
    assert (row["previous_version"], row["config_version"]) == (4, 4)
    assert (row["new_picks"], row["dropped"]) == (1, 1)  # AAA is new, ETF1 dropped
    # the same counts the read model derives from the two runs' rows
    now = table(reader, "rule_screen")[["instrument_id", "decision"]]
    was = table(reader, "rule_screen", PREVIOUS)
    moved = _compare(now, dict(zip(was["instrument_id"], was["decision"], strict=True)))
    assert sorted(c for c, _ in moved.values() if c) == ["dropped", "new"]
    assert second.run_id != first.run_id
    assert row["started_at"] == pd.Timestamp(T0) and row["finished_at"] >= row["started_at"]


def test_a_changed_definition_keeps_both_versions() -> None:
    reader, writer = seeded()
    previous_session(writer)
    run_screener(reader, writer, config(), PREVIOUS, now=T0, held=HARNESS_ALL)
    newer = resolve_config(configs(version=5), "big_liquid", UserContext(SITE_USER))
    run_screener(reader, writer, newer, DAY, now=T0, held=HARNESS_ALL)
    (row,) = table(reader, "screen_runs").to_dict("records")
    assert (row["previous_version"], row["config_version"]) == (4, 5)


def test_change_counts_count_this_runs_names_only() -> None:
    now = {"A": "QUALIFIED", "B": "REJECT", "C": "PAUSED", "D": "WATCH"}
    before = {"A": "REJECT", "B": "WATCH", "C": "QUALIFIED", "Z": "QUALIFIED"}
    assert change_counts(now, before) == (2, 2)  # A, D new; B, C dropped; Z is not in this run


def test_the_frames_are_deterministic_and_the_row_is_the_runs() -> None:
    reader, writer = seeded()
    outcome = run_screener(reader, writer, config(), DAY, now=T0, held=HARNESS_ALL)
    assert outcome.rules is not None
    stamp = Stamp(DAY, outcome.run_id, T0, SITE_USER, "big_liquid", config().hash, 4)
    lineage = Lineage("p", PREVIOUS, 3, {"EQ:AAA": "REJECT"}, T0, T0 + timedelta(seconds=3))
    one, two = (rule_frames(outcome.rules, stamp, lineage) for _ in range(2))
    for name in one:
        pd.testing.assert_frame_equal(one[name], two[name])
    assert one["screen_picks"]["instrument_id"].is_monotonic_increasing
    assert one["screen_runs"].iloc[0]["knowledge_ts"] == pd.Timestamp(T0)


def test_point_in_time_columns_are_the_runs() -> None:
    reader, writer = seeded()
    outcome = run_screener(reader, writer, config(), DAY, now=T0, held=HARNESS_ALL)
    for name in ("screen_runs", "screen_picks", "rule_screen"):
        frame = table(reader, name)
        assert set(frame["knowledge_ts"]) == {pd.Timestamp(T0)}, name
        assert set(frame["session_date"]) == {DAY} and set(frame["run_id"]) == {outcome.run_id}


def test_screen_picks_holds_no_field_value() -> None:
    """Licence: the run's values stay in rule_screen_values; the object tables carry none."""
    names = {c.name for c in (*SCREEN_PICKS.columns, *SCREEN_RUNS.columns)}
    assert not names & {"value_num", "value_str", "criterion_id", "field", "reasons", "flags"}
    reader, writer = seeded()
    run_screener(reader, writer, config(), DAY, now=T0, held=OPEN_ONLY)
    assert LIQ not in " ".join(map(str, table(reader, "screen_picks").to_numpy().ravel()))


@pytest.mark.parametrize("broken", ["screen_runs", "screen_picks"])
def test_a_failed_object_frame_publishes_none_of_the_three(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    reader, writer = seeded()
    real = run_module.rule_frames

    def failing(*args: Any) -> dict[str, Any]:
        frames = real(*args)
        frames[broken] = frames[broken].drop(columns="decision" if "picks" in broken else "rows")
        return frames

    monkeypatch.setattr(run_module, "rule_frames", failing)
    with pytest.raises(DataValidationError):
        run_screener(reader, writer, config(), DAY, now=T0, held=HARNESS_ALL)
    for name in ("rule_screen", "rule_screen_values", "screen_runs", "screen_picks"):
        assert reader.table(f"results/{name}", DAY) is None, name
