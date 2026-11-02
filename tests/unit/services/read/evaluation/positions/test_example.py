"""The example position of a share pick (ADR 0083 decision 3, ADR 0088 2.8, decision 22): the
reference close, the stop price from the exit rule (percentile, declared, or the ATR fallback per
name), the exit session counted from the entry, the short and book shapes, and every part that
cannot be computed UNKNOWN with its reason, never filled."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.services.read.evaluation import pick_edges
from algotrade.services.read.evaluation.positions import example as module
from algotrade.services.read.evaluation.positions.example import (
    PickInput,
    Shape,
    advance,
    load_example_positions,
)
from algotrade.services.read.evaluation.positions.exit_rule import ATR, ExitRule, Stop, StopKind
from algotrade.services.read.values import Unknown, UnknownCode

S = date(2026, 10, 30)  # a Friday: the entry is Monday's close
EDGE: Any = SimpleNamespace(id="drift", schedule="every_session")
CTX: Any = SimpleNamespace(session=SimpleNamespace(date=S))
GONE = Unknown(UnknownCode.NO_ROW, None)  # type: ignore[arg-type]


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    closes: dict[str, float | None],
    rule: ExitRule,
    per_name: dict[str, ExitRule] | None = None,
) -> list[str | None]:
    """Stub the closes and the exit rule; returns the names the rule was asked for."""
    asked: list[str | None] = []

    def values(ctx: Any, ids: list[str], names: list[str]) -> dict[str, tuple[Any, ...]]:
        if names == [ATR]:  # every name's ATR(14) is 2.5
            return {i: (SimpleNamespace(value=2.5, unknown=None),) for i in ids}
        return {
            i: (SimpleNamespace(value=closes[i], unknown=None if closes[i] else GONE),) for i in ids
        }

    def exit_rule_at(ctx: Any, edge: Any, iid: str | None, declared: Any, bounded: bool) -> Any:
        asked.append(iid)
        return rule if iid is None else (per_name or {}).get(iid, rule)

    monkeypatch.setattr(module, "load_feature_values", values)
    monkeypatch.setattr(module, "exit_rule_at", exit_rule_at)
    return asked


def test_a_long_pick_has_its_reference_close_stop_price_and_exit_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = ExitRule("drift", Stop(StopKind.HISTORY, fraction=0.06, winners=40), 20)
    _wire(monkeypatch, {"EQ:A": 100.0}, rule)
    (pos,) = load_example_positions(CTX, EDGE, [PickInput("EQ:A")])
    assert pos.shape is Shape.LONG_SHARES and pos.reference_close == 100.0
    assert pos.stop_price == pytest.approx(94.0) and pos.stop is rule.stop
    assert pos.entry_session == date(2026, 11, 2)  # the next close after Friday's
    assert pos.exit_session == advance(date(2026, 11, 2), 20)
    assert (pos.close_unknown, pos.stop_unknown, pos.exit_unknown) == (None, None, None)


def test_the_atr_fallback_is_taken_per_name_and_placed_below_the_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_name = Unknown(UnknownCode.NOT_APPLICABLE, None)  # type: ignore[arg-type]
    shared = ExitRule("drift", None, 20, no_name, winners=3)
    own = ExitRule("drift", Stop(StopKind.FALLBACK, atr=9.0, multiple=2.0, winners=3), 20)
    asked = _wire(monkeypatch, {"EQ:A": 50.0, "EQ:B": 20.0}, shared, {"EQ:A": own})
    a, b = load_example_positions(CTX, EDGE, [PickInput("EQ:A"), PickInput("EQ:B")])
    assert asked == ["EQ:A"]  # the rule once, for the first long; every ATR in one read
    assert a.stop_price == pytest.approx(45.0) and b.stop_price == pytest.approx(15.0)
    assert a.stop is not None and a.stop.kind is StopKind.FALLBACK and a.exit_session


def test_a_short_pick_assumes_borrow_and_its_stop_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = ExitRule("drift", Stop(StopKind.HISTORY, fraction=0.06, winners=40), 20)
    _wire(monkeypatch, {"EQ:A": 100.0}, rule)
    (pos,) = load_example_positions(CTX, EDGE, [PickInput("EQ:A", side="short")])
    assert pos.shape is Shape.SHORT_SHARES and pos.borrow_assumed
    assert pos.stop_price is None and pos.stop_unknown is not None
    assert pos.reference_close == 100.0 and pos.exit_session is not None


def test_a_book_name_carries_its_weight_and_no_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    rule = ExitRule("drift", Stop(StopKind.HISTORY, fraction=0.06, winners=40), 21)
    _wire(monkeypatch, {"EQ:A": 100.0}, rule)
    book: Any = SimpleNamespace(id="drift", schedule="month_end")
    (pos,) = load_example_positions(CTX, book, [PickInput("EQ:A", book=True)])
    assert pos.shape is Shape.BOOK and not hasattr(pos, "weight")  # no weight or size served
    assert pos.stop_price is None and pos.stop_unknown is not None
    assert pos.exit_session == date(2026, 12, 1)  # the entry after November's last session


def test_a_missing_close_and_a_missing_rule_are_unknown_never_filled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    not_run = Unknown(UnknownCode.NOT_RUN, None)  # type: ignore[arg-type]
    _wire(monkeypatch, {"EQ:A": None}, ExitRule("drift", None, None, not_run))
    (pos,) = load_example_positions(CTX, EDGE, [PickInput("EQ:A")])
    assert pos.reference_close is None and pos.close_unknown is GONE
    assert pos.stop_price is None and pos.stop_unknown is not_run
    assert pos.exit_session is None and pos.exit_unknown is not_run


def test_a_first_long_without_atr_still_falls_back_for_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule asked for the first long found no ATR (a feature gap): the site's multiple and
    every pick's own ATR, never "no name to take the fallback from" for all."""
    gap = Unknown(UnknownCode.NO_ROW, None)  # type: ignore[arg-type]
    _wire(monkeypatch, {"EQ:A": 50.0, "EQ:B": 20.0}, ExitRule("drift", None, 20, gap, winners=3))
    monkeypatch.setattr(module, "fallback_multiple", lambda ctx: 2.0)
    a, b = load_example_positions(CTX, EDGE, [PickInput("EQ:A"), PickInput("EQ:B")])
    assert a.stop_price == pytest.approx(45.0) and b.stop_price == pytest.approx(15.0)


def test_a_gone_ledger_is_no_fallback_and_its_stop_stays_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pruned = Unknown(UnknownCode.NOT_STORED, None)  # type: ignore[arg-type]
    _wire(monkeypatch, {"EQ:A": 50.0}, ExitRule("drift", None, 20, pruned))
    (pos,) = load_example_positions(CTX, EDGE, [PickInput("EQ:A")])
    assert pos.stop_price is None and pos.stop_unknown is pruned


def test_a_setup_with_an_entry_condition_has_no_entry_or_exit_from_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = ExitRule("drift", Stop(StopKind.HISTORY, fraction=0.06, winners=40), 20)
    _wire(monkeypatch, {"EQ:A": 100.0}, rule)
    (pos,) = load_example_positions(CTX, EDGE, [PickInput("EQ:A")], entry_condition=True)
    assert pos.entry_session is None and pos.exit_session is None and pos.exit_unknown
    assert pos.stop_price == pytest.approx(94.0)


def test_no_picks_read_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _wire(monkeypatch, {}, ExitRule("drift", None, None))
    assert load_example_positions(CTX, EDGE, []) == () and asked == []


def _setup(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]], kind: str = "excess_return",
    entry: object = None,
) -> list[Any]:  # fmt: skip
    """Stub the document, the stored night and ``load_example_positions``; returns its calls."""
    outcome = SimpleNamespace(kind=kind, start_offset_sessions=2, entry=entry)
    calls: list[Any] = []
    monkeypatch.setattr(
        module, "parsed_edges", lambda ctx, user: [SimpleNamespace(id="drift", outcome=outcome)]
    )
    monkeypatch.setattr(pick_edges, "partition", lambda ctx, table: pd.DataFrame(rows))

    def examples(ctx: Any, edge: Any, picks: Any, offset: int, entry_condition: bool) -> tuple[()]:
        calls.append((list(picks), offset, entry_condition))
        return ()

    monkeypatch.setattr(module, "load_example_positions", examples)
    return calls


ROW = {"user_id": "site", "edge_id": "drift", "screener": "s", "status": "picked", "reason": None}
CTX_ME: Any = SimpleNamespace(session=SimpleNamespace(date=S), user=SimpleNamespace(user_id="me"))


def test_a_setups_examples_take_each_names_stored_side_and_the_documents_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {**ROW, "pick_ids": ["EQ:A", "EQ:B"], "pick_sides": ["long", "short"]}
    calls = _setup(monkeypatch, [row])
    module.load_setup_examples(CTX_ME, EDGE, ["EQ:A", "EQ:B", "EQ:C"])
    ((picks, offset, entry),) = calls
    assert [(p.instrument_id, p.side, p.book) for p in picks] == [
        ("EQ:A", "long", False), ("EQ:B", "short", False), ("EQ:C", "long", False),
    ]  # fmt: skip
    assert (offset, entry) == (2, False)


def test_a_book_outcome_and_an_entry_condition_reach_the_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _setup(monkeypatch, [{**ROW, "pick_ids": ["EQ:A"]}], "portfolio_return", object())
    module.load_setup_examples(CTX_ME, EDGE, ["EQ:A"])
    ((picks, _, entry),) = calls
    assert picks[0].book and entry


def test_no_session_is_none_and_an_unreadable_document_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert module.load_setup_examples(None, EDGE, ["EQ:A"]) is None
    monkeypatch.setattr(module, "parsed_edges", lambda ctx, user: [])
    assert module.load_setup_examples(CTX_ME, EDGE, ["EQ:A"]) == ()
