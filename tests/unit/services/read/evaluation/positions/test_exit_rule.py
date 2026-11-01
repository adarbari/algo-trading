"""The historical exit rule of a share setup (ADR 0083 decision 3): the stop is the 80th percentile
of the basis's winners' ``max_drawdown`` (a hand-computed value on a ledger fixture), the ATR
fallback below ``min_winners``, a declared stop published as it is, the hold the verdict's basis
horizon; point in time (the canonical run ends by the session, only trades that exited by it
count) and never filled (no basis, no ledger, short picks, no ATR: UNKNOWN with the reason)."""

from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.services.read.evaluation import edges, runs
from algotrade.services.read.evaluation.positions import exit_rule as module
from algotrade.services.read.evaluation.positions.exit_rule import (
    ATR,
    ExitRule,
    Stop,
    StopKind,
    exit_rule_at,
)
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.evaluation.conftest import (
    DOCS,
    END,
    FROZEN,
    session_ctx,
    stores,
    write_run,
)

MIN_WINNERS = 5
SETTINGS = {("site", "settings", "verdict"): {"exit_rule": {"min_winners": MIN_WINNERS}}}
DAY = date(2026, 3, 2)


def trade(i: int, dip: float | None, **changes: Any) -> dict[str, Any]:
    day = DAY + timedelta(days=i)
    row = {
        "edge_id": "drift", "user_id": "site", "edge_variant": None, "variant": "momo",
        "role": "screener", "horizon_sessions": 20, "range_from": date(2026, 1, 5),
        "range_to": END, "split_from": FROZEN, "decision_session": day,
        "instrument_id": f"EQ:{i}", "rank": 1, "entry_session": day + timedelta(days=1),
        "exit_session": day + timedelta(days=29), "status": "won", "hit": True, "value": 0.02,
        "gross_value": 0.02, "score": 1.0, "adv_usd_20d": 1e7, "max_drawdown": dip,
        "before_split": True, "delisted": False, "licence": "open", "value_licence": "open",
        "score_licence": "open", "adv_licence": "open",
    }  # fmt: skip
    return {**row, **changes}


WINNERS = [trade(i, round(0.01 * (i + 1), 2)) for i in range(10)]  # dips 0.01 .. 0.10


def world(trades: list[dict[str, Any]] | None, day: date = END) -> Any:
    backend = MemoryBackend()
    write_run(backend, "r1", FROZEN, 0.6, trades=trades)
    ctx = stores(backend, docs={**DOCS, **SETTINGS})
    edge = edges.load_edge(ctx, "drift")
    assert edge is not None
    return session_ctx(ctx, day), edge


def at(
    trades: list[dict[str, Any]] | None,
    instrument_id: str | None = None,
    declared: Stop | None = None,
) -> ExitRule:
    ctx, edge = world(trades)
    return exit_rule_at(ctx, edge, instrument_id, declared)


def test_the_stop_is_the_80th_percentile_of_the_winners_dips_and_the_hold_the_basis_horizon() -> (
    None
):
    ctx, edge = world(
        [*WINNERS, trade(20, 0.50, hit=False, status="lost", value=-0.1)]  # a loser never counts
    )
    rule = exit_rule_at(ctx, edge)
    assert rule.unknown is None and rule.hold_sessions == 20 and rule.winners == 10
    assert rule.stop is not None and rule.stop.kind is StopKind.HISTORY
    assert (
        rule.stop.fraction == 0.08
    )  # the smallest observed dip 80% of the ten winners did not exceed, by hand
    assert rule.stop.winners == 10 and rule.stop.beyond == pytest.approx(0.2)


def test_a_trade_that_had_not_exited_by_the_session_is_not_read() -> None:
    late = [trade(i, 0.9, exit_session=END + timedelta(days=3)) for i in range(20, 30)]
    ctx, edge = world([*WINNERS, *late])
    rule = exit_rule_at(ctx, edge)
    assert rule.stop is not None and rule.stop.fraction == 0.08
    assert rule.winners == 10


def test_a_run_that_ends_after_the_session_is_not_known_then() -> None:
    ctx, edge = world(WINNERS, day=END - timedelta(days=1))
    rule = exit_rule_at(ctx, edge)
    assert rule.stop is None and rule.hold_sessions is None  # no verdict of that run is known
    assert isinstance(rule.unknown, Unknown) and rule.unknown.code is UnknownCode.NOT_RUN


def test_fewer_winners_than_the_minimum_fall_back_to_the_atr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[Any] = []

    def values(ctx: Any, ids: Any, names: Any) -> Any:
        asked.append((list(ids), list(names)))
        return {ids[0]: (SimpleNamespace(value=1.5, unknown=None),)}

    monkeypatch.setattr(module, "load_feature_values", values)
    ctx, edge = world(WINNERS[: MIN_WINNERS - 1])
    rule = exit_rule_at(ctx, edge, "EQ:1")
    assert rule.stop == Stop(
        StopKind.FALLBACK, atr=1.5, multiple=2.0, winners=MIN_WINNERS - 1
    ) and rule.unknown is None  # fmt: skip
    assert asked == [(["EQ:1"], [ATR])]
    at_min = at(WINNERS[:MIN_WINNERS])
    assert at_min.stop is not None and at_min.stop.kind is StopKind.HISTORY  # the boundary


def test_a_missing_atr_is_unknown_never_filled(monkeypatch: pytest.MonkeyPatch) -> None:
    why = Unknown(UnknownCode.NULL, None)  # type: ignore[arg-type]
    monkeypatch.setattr(
        module, "load_feature_values",
        lambda ctx, ids, names: {ids[0]: (SimpleNamespace(value=None, unknown=why),)},
    )  # fmt: skip
    rule = at(WINNERS[:2], "EQ:1")
    assert rule.stop is None and rule.unknown is why and rule.hold_sessions == 20
    nameless = at(WINNERS[:2])
    assert nameless.stop is None and nameless.unknown is not None
    assert nameless.unknown.code is UnknownCode.NOT_APPLICABLE


def test_a_declared_stop_is_published_as_it_is_and_the_percentile_is_not_read() -> None:
    own = Stop(StopKind.DECLARED, fraction=0.05)
    rule = at(WINNERS, declared=own)
    assert rule.stop is own and rule.hold_sessions == 20
    assert at(None, declared=own).stop is own  # no ledger needed


def test_a_run_from_before_the_ledger_is_not_stored_and_keeps_the_hold() -> None:
    rule = at(None)
    assert rule.stop is None and rule.hold_sessions == 20
    assert isinstance(rule.unknown, Unknown) and rule.unknown.code is UnknownCode.NOT_STORED


def test_short_picks_have_no_published_exit_rule() -> None:
    rule = at([*WINNERS, trade(30, 0.02, side="short")])
    assert rule.stop is None and rule.unknown is not None
    assert rule.unknown.code is UnknownCode.NOT_APPLICABLE


def test_a_setup_with_no_verdict_basis_is_not_run() -> None:
    backend = MemoryBackend()
    ctx = session_ctx(stores(backend, docs={**DOCS, **SETTINGS}), END)
    edge = edges.load_edge(ctx, "drift")
    assert edge is not None
    rule = exit_rule_at(ctx, edge)
    assert (rule.stop, rule.hold_sessions) == (None, None)
    assert rule.unknown is not None and rule.unknown.code is UnknownCode.NOT_RUN


def test_tied_dips_give_an_observed_stop_and_the_real_share_past_it() -> None:
    ties = [trade(i, 0.0) for i in range(9)] + [trade(9, 0.1)]
    rule = at(ties)
    assert rule.stop is not None and rule.stop.fraction == 0.0  # an observed dip, not interpolated
    assert rule.stop.beyond == pytest.approx(0.1)  # one of ten went past it, not the nominal 20%


def test_a_personal_licence_ledger_is_licence_unknown_to_a_viewer_without_it() -> None:
    rows = [trade(i, 0.05, licence="personal") for i in range(10)]
    rule = at(rows)
    assert rule.stop is None and rule.hold_sessions == 20
    assert rule.unknown is not None and rule.unknown.code is UnknownCode.LICENCE


def test_a_run_hiding_its_out_of_sample_trades_says_only_in_sample_winners_were_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def hidden(ctx: Any, edge: Any) -> Any:
        found = runs.load_canonical_run(ctx, edge)
        assert found.run is not None
        return replace(found, run=replace(found.run, oos_hidden=True))

    late = [trade(i, 0.9, before_split=False) for i in range(20, 30)]  # out-of-sample winners
    proxy = SimpleNamespace(
        load_canonical_run=hidden, load_run_trades=runs.load_run_trades, OPEN=runs.OPEN
    )
    monkeypatch.setattr(module, "runs", proxy)
    rule = at([*WINNERS, *late])
    assert rule.in_sample_only and rule.winners == 10  # the reader served in-sample rows only
    assert rule.stop is not None and rule.stop.fraction == 0.08
