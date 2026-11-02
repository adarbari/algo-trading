"""The exit rule of an option setup (ADR 0088 decision 19, design 2.4a): its declared
``[outcome.exit]`` published as it is (a declared stop a multiple of the credit); only without a
declared stop the 80th percentile of the winners' ``max_adverse`` (a share of collateral), by hand;
UNKNOWN below ``min_winners`` (no ATR fallback); the hold the earlier of the cap and the expiry;
point in time (a trade that exited after the session is never read: the lookahead test)."""

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import pytest

from algotrade.config.edges.positions.cases import Case, CaseValue
from algotrade.config.edges.positions.spec import ExitSettings, exits_digest
from algotrade.config.edges.positions.templates import KIND, NAME
from algotrade.core.model.predicates import Group, Rule
from algotrade.core.time.calendar import next_session, sessions_to
from algotrade.services.read.evaluation import edges, runs
from algotrade.services.read.evaluation.positions import exit_rule as module
from algotrade.services.read.evaluation.positions.exit_rule import (
    ExitRule,
    Stop,
    StopBasis,
    StopKind,
    exit_rule_at,
)
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.services.read.evaluation.conftest import (
    DOCS,
    EDGE,
    END,
    FROZEN,
    session_ctx,
    stores,
    write_run,
)
from tests.unit.services.read.evaluation.positions.test_exit_rule import (
    MIN_WINNERS,
    SETTINGS,
    trade,
)

TEMPLATES = dict(FileConfigStore(REPO_ROOT / "config").load("site", KIND, NAME) or {})
OPTION = {
    "kind": "option_pnl", "horizon_sessions": [20], "benchmark": "none", "tenor_days": 30,
    "position": "short_put", "strike_delta": 0.25, "start_offset_sessions": 1,
}  # fmt: skip


def adverse(i: int, loss: float | None, **changes: Any) -> dict[str, Any]:
    """A winning option trade of the ledger whose worst mark loss over collateral is ``loss``."""
    return trade(i, None, max_adverse=loss, exit_kind="horizon", **changes)


WINNERS = [adverse(i, round(0.01 * (i + 1), 2)) for i in range(10)]  # losses 0.01 .. 0.10


def world(
    trades: list[dict[str, Any]] | None,
    day: date = END,
    recorded: Any = "same",
    **outcome: Any,
) -> tuple[Any, edges.Edge]:
    """``recorded``: the exits digest on the run record ("same": the document's; None: a run
    from before it was recorded; else that digest)."""
    backend = MemoryBackend()
    doc = {**EDGE, "outcome": {**OPTION, **outcome}}
    docs = {**DOCS, **SETTINGS, ("site", "edges", "drift"): doc, ("site", KIND, NAME): TEMPLATES}
    ctx = stores(backend, docs=docs)
    parsed = next(e for e in edges.parsed_edges(ctx, "site") if e.id == "drift")
    digest = exits_digest(parsed.outcome.position) if recorded == "same" else recorded
    write_run(backend, "r1", FROZEN, 0.6, trades=trades, exits_digest=digest)
    edge = edges.load_edge(ctx, "drift")
    assert edge is not None
    return session_ctx(ctx, day), edge


def at(trades: list[dict[str, Any]] | None, **kwargs: Any) -> ExitRule:
    outcome = kwargs.pop("outcome", {})
    ctx, edge = world(trades, recorded=kwargs.pop("recorded", "same"), **outcome)
    return exit_rule_at(ctx, edge, **kwargs)


def test_the_world_is_an_option_setup_with_a_verdict_basis() -> None:
    ctx, edge = world(WINNERS)
    run = runs.load_canonical_run(ctx, edge).run
    assert run is not None and module.declared_outcome(ctx, edge, run) is not None


def test_a_declared_stop_is_published_as_it_is_with_the_other_declared_exits() -> None:
    exits = {"exit": {"stop_loss": 2.0, "take_profit": 0.5, "exit_dte": 21}}
    rule = at(WINNERS, outcome=exits)
    assert rule.stop == Stop(StopKind.DECLARED, fraction=2.0, basis=StopBasis.CREDIT)
    assert (rule.take_profit, rule.exit_dte, rule.hold_sessions) == (0.5, 21, 20)
    assert rule.unknown is None and rule.winners == 0  # the percentile is not read
    assert at(None, outcome=exits).stop == rule.stop  # no ledger needed


def test_without_a_declared_stop_the_stop_is_the_80th_percentile_of_the_winners_max_adverse() -> (
    None
):
    losers = [adverse(20, 0.9, hit=False, status="lost", value=-0.1)]  # a loser never counts
    rule = at([*WINNERS, *losers], outcome={"exit": {"take_profit": 0.5}})
    assert rule.unknown is None and rule.take_profit == 0.5 and rule.winners == 10
    assert rule.stop is not None and rule.stop.kind is StopKind.HISTORY
    assert rule.stop.basis is StopBasis.COLLATERAL
    assert rule.stop.fraction == 0.08  # the smallest loss 80% of the ten winners did not pass
    assert rule.stop.beyond == 0.2


def test_the_share_dip_is_never_read_for_an_option_setup() -> None:
    dips = [trade(i, 0.5, max_adverse=0.01 * (i + 1)) for i in range(10)]
    rule = at(dips)
    assert rule.stop is not None and rule.stop.fraction == 0.08  # max_adverse, not max_drawdown


def test_fewer_winners_than_the_minimum_is_unknown_never_an_atr_fallback() -> None:
    rule = at(WINNERS[: MIN_WINNERS - 1], instrument_id="EQ:1")
    assert rule.stop is None and rule.hold_sessions == 20 and rule.winners == MIN_WINNERS - 1
    assert rule.unknown is not None and rule.unknown.code is UnknownCode.NOT_APPLICABLE
    at_min = at(WINNERS[:MIN_WINNERS])
    assert at_min.stop is not None and at_min.stop.kind is StopKind.HISTORY  # the boundary


def test_a_winning_trade_that_exited_after_the_session_is_never_read() -> None:
    """Lookahead: ten more winners with large losses exit after the served session; the stop is
    the one the ten that exited by it give, and their count is not reached early."""
    late = [adverse(i, 0.9, exit_session=END + timedelta(days=3)) for i in range(20, 30)]
    rule = at([*WINNERS, *late])
    assert rule.stop is not None and rule.stop.fraction == 0.08 and rule.winners == 10
    few = at([*WINNERS[: MIN_WINNERS - 1], *late])
    assert few.stop is None and few.winners == MIN_WINNERS - 1  # the late ones never count


def test_a_run_that_ends_after_the_session_is_not_known_then_even_with_a_declared_stop() -> None:
    ctx, edge = world(WINNERS, END - timedelta(days=1), exit={"stop_loss": 2.0})
    rule = exit_rule_at(ctx, edge)
    assert (rule.stop, rule.hold_sessions) == (None, None)
    assert rule.unknown is not None and rule.unknown.code is UnknownCode.NOT_RUN


def test_a_winners_loss_under_a_licence_the_viewer_lacks_is_unknown_never_a_partial_stop() -> None:
    rows = [*WINNERS, adverse(11, 0.5, value_licence="personal")]
    rule = at(rows)
    assert rule.stop is None and rule.unknown is not None
    assert rule.unknown.code is UnknownCode.LICENCE


def test_a_run_from_before_max_adverse_is_not_stored() -> None:
    rule = at([adverse(i, None) for i in range(10)])
    assert rule.stop is None and rule.unknown is not None
    assert rule.unknown.code is UnknownCode.NOT_STORED


def test_the_hold_is_the_earlier_of_the_cap_and_the_expiry() -> None:
    entry = next_session(END)
    soon = entry + timedelta(days=7)
    rule = at(WINNERS, expiry=soon)
    assert rule.hold_sessions == sessions_to(entry, soon) < 20 and rule.expiry == soon
    assert at(WINNERS, expiry=entry + timedelta(days=90)).hold_sessions == 20  # the cap first
    assert at(WINNERS).hold_sessions == 20  # no expiry given: the cap


def test_a_case_valued_exit_is_published_only_as_resolved_for_the_pick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A case table is refused at load until E13 applies it in runs, so the outcome is given
    one here: its stop is published only as the caller resolved it at the session."""
    high = Group("all", (Rule("market.vix_close", "gt", 30),))
    case = CaseValue("stop_loss", (Case(high, 3.0),), 2.0)
    loaded = module.declared_outcome
    exits = ExitSettings(take_profit=0.5, stop_loss=2.0)

    def with_case(ctx: Any, edge: Any, run: Any) -> Any:
        found = loaded(ctx, edge, run)
        assert found is not None and found.position is not None
        return replace(found, position=replace(found.position, exit=exits, cases=(case,)))

    monkeypatch.setattr(module, "declared_outcome", with_case)
    ctx, edge = world(None)
    run = runs.load_canonical_run(ctx, edge).run
    assert run is not None
    tested = exits_digest(with_case(ctx, edge, run).position)
    unresolved = at(WINNERS, recorded=tested)
    assert unresolved.stop is None and unresolved.take_profit is None
    assert unresolved.unknown is not None
    assert unresolved.unknown.code is UnknownCode.NOT_APPLICABLE
    rule = at(WINNERS, recorded=tested, resolved={"stop_loss": 3.0})
    assert rule.stop == Stop(StopKind.DECLARED, fraction=3.0, basis=StopBasis.CREDIT)
    assert rule.take_profit == 0.5 and rule.unknown is None
    off = at(
        WINNERS, recorded=tested, resolved={"stop_loss": 0}
    )  # 0 is off, as a grid spells it: the percentile
    assert off.stop is not None and off.stop.kind is StopKind.HISTORY


def test_exits_edited_after_the_run_are_not_published_beside_its_verdict() -> None:
    """The rule published is the one the run tested: a document edited since (2.0 -> 3.0) is
    UNKNOWN until re-run, and a run from before the digest was recorded is NOT_STORED."""
    old = ExitSettings(stop_loss=2.0)
    ctx, edge = world(WINNERS, exit={"stop_loss": 3.0})
    run = runs.load_canonical_run(ctx, edge).run
    outcome = module.declared_outcome(ctx, edge, run) if run else None
    assert outcome is not None and outcome.position is not None
    tested = exits_digest(replace(outcome.position, exit=old))
    edited = at(WINNERS, outcome={"exit": {"stop_loss": 3.0}}, recorded=tested)
    assert edited.stop is None and edited.unknown is not None
    assert edited.unknown.code is UnknownCode.NOT_RUN and edited.hold_sessions == 20
    older = at(WINNERS, outcome={"exit": {"stop_loss": 3.0}}, recorded=None)
    assert older.stop is None and older.unknown is not None
    assert older.unknown.code is UnknownCode.NOT_STORED


def test_the_document_is_read_as_the_runs_owner_never_the_viewer() -> None:
    ctx, edge = world(WINNERS, exit={"stop_loss": 2.0})
    run = runs.load_canonical_run(ctx, edge).run
    assert run is not None and run.owner == "site"
    seen: list[str] = []
    real = edges.parsed_edges

    def spy(c: Any, user: str) -> Any:
        seen.append(user)
        return real(c, user)

    with pytest.MonkeyPatch.context() as m:
        m.setattr(module, "parsed_edges", spy)
        module.declared_outcome(ctx, edge, run)
    assert seen == ["site"]


def test_one_winner_with_no_max_adverse_stored_is_unknown_never_a_subset() -> None:
    rule = at([*WINNERS, adverse(11, None)])
    assert rule.stop is None and rule.unknown is not None
    assert rule.unknown.code is UnknownCode.NOT_STORED


def test_an_expiry_not_after_the_entry_session_is_unknown() -> None:
    rule = at(WINNERS, expiry=next_session(END))
    assert rule.stop is None and rule.hold_sessions is None and rule.unknown is not None
    assert rule.unknown.code is UnknownCode.NOT_APPLICABLE
