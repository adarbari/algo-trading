"""The exit rule of a share setup that declares an ``[outcome.exit]`` (ADR 0088, E3c-2c): a declared
stop published as declared (a fall of the entry close), the take profit a rise of it
(``take_profit_basis`` ENTRY), the percentile stop only without a declared stop, the run's
``exits_digest`` checked, a short setup NOT_APPLICABLE; an option setup's rule keeps its CREDIT."""

from datetime import date
from typing import Any

from algotrade.config.edges.positions.spec import exits_digest
from algotrade.config.edges.positions.templates import KIND, NAME
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
from tests.unit.services.read.evaluation.positions.test_exit_rule import SETTINGS, WINNERS
from tests.unit.services.read.evaluation.positions.test_exit_rule_option import (
    WINNERS as OPTION_WINNERS,
)
from tests.unit.services.read.evaluation.positions.test_exit_rule_option import (
    world as option_world,
)

TEMPLATES = dict(FileConfigStore(REPO_ROOT / "config").load("site", KIND, NAME) or {})
SHARE = {"position": "long_shares", "exit": {"take_profit": 0.1, "stop_loss": 0.05}}
WHEN = {"all": [{"field": "momentum.rsi_14", "op": "gt", "value": 70}]}


def world(
    trades: list[dict[str, Any]] | None, day: date = END, recorded: Any = "same", **outcome: Any
) -> tuple[Any, edges.Edge]:
    """A share setup (``recorded``: the exits digest on the run record, as in the option tests)."""
    backend = MemoryBackend()
    doc = {**EDGE, "outcome": {**EDGE["outcome"], **SHARE, **outcome}}
    docs = {**DOCS, **SETTINGS, ("site", "edges", "drift"): doc, ("site", KIND, NAME): TEMPLATES}
    ctx = stores(backend, docs=docs)
    parsed = next(e for e in edges.parsed_edges(ctx, "site") if e.id == "drift")
    digest = exits_digest(parsed.outcome.position) if recorded == "same" else recorded
    write_run(backend, "r1", FROZEN, 0.6, trades=trades, exits_digest=digest)
    edge = edges.load_edge(ctx, "drift")
    assert edge is not None
    return session_ctx(ctx, day), edge


def at(trades: list[dict[str, Any]] | None, **kwargs: Any) -> ExitRule:
    ctx, edge = world(trades, recorded=kwargs.pop("recorded", "same"), **kwargs.pop("outcome", {}))
    return exit_rule_at(ctx, edge, **kwargs)


def test_a_declared_share_stop_is_published_as_declared_with_the_target_as_a_rise() -> None:
    rule = at(None)  # no ledger needed
    assert rule.stop == Stop(StopKind.DECLARED, fraction=0.05, basis=StopBasis.ENTRY)
    assert (rule.take_profit, rule.take_profit_basis) == (0.1, StopBasis.ENTRY)
    assert rule.hold_sessions == 20 and rule.unknown is None and rule.winners == 0


def test_the_condition_fields_of_a_share_exit_are_published() -> None:
    rule = at(None, outcome={"exit": {**SHARE["exit"], "when": WHEN}})
    assert rule.condition_fields == ("momentum.rsi_14",)


def test_a_share_setup_with_no_stop_loss_keeps_the_percentile_stop_and_the_declared_target() -> (
    None
):
    rule = at(WINNERS, outcome={"exit": {"take_profit": 0.1, "when": WHEN}})
    assert rule.stop is not None and rule.stop.kind is StopKind.HISTORY
    assert rule.stop.basis is StopBasis.ENTRY and rule.stop.fraction == 0.08  # the 80th percentile
    assert (rule.take_profit, rule.take_profit_basis) == (0.1, StopBasis.ENTRY)
    assert rule.condition_fields == ("momentum.rsi_14",) and rule.winners == 10


def test_exits_edited_after_the_run_make_the_share_rule_unknown_and_keep_the_hold() -> None:
    ctx, edge = world(WINNERS)
    run = runs.load_canonical_run(ctx, edge).run
    assert run is not None and module.declared_outcome(ctx, edge, run) is not None
    edited = at(WINNERS, recorded="0" * 16)
    assert edited.stop is None and edited.take_profit is None and edited.hold_sessions == 20
    assert edited.unknown is not None and edited.unknown.code is UnknownCode.NOT_RUN
    older = at(WINNERS, recorded=None)
    assert older.unknown is not None and older.unknown.code is UnknownCode.NOT_STORED


def test_a_short_share_setup_is_published_for_long_picks_only() -> None:
    rule = at(WINNERS, outcome={"side": "short", "position": "short_shares"})
    assert rule.stop is None and rule.take_profit is None and rule.hold_sessions == 20
    assert rule.unknown is not None and rule.unknown.code is UnknownCode.NOT_APPLICABLE


def test_an_option_setup_keeps_its_take_profit_as_a_share_of_the_credit() -> None:
    ctx, edge = option_world(OPTION_WINNERS, exit={"stop_loss": 2.0, "take_profit": 0.5})
    rule = exit_rule_at(ctx, edge)
    assert (rule.take_profit, rule.take_profit_basis) == (0.5, StopBasis.CREDIT)
    assert rule.stop == Stop(StopKind.DECLARED, fraction=2.0, basis=StopBasis.CREDIT)
