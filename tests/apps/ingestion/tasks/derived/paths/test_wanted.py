"""``positions_wanted`` for a wheel (ADR 0088, EF-G13): the put phase's position at every hold of
its ``horizon_sessions`` and the call phase (``[outcome.wheel]``: a covered call at the wheel's
delta and tenor) at every one of the same holds, each its own key; an edge without a wheel stores
no call phase."""

import tomllib
from typing import Any

from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.positions.key import parse_position_key
from algotrade.config.edges.positions.templates import load_templates
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_ingestion.tasks.derived.paths.wanted import positions_wanted
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.test_document import document
from tests.unit.config.edges.test_loading import PRESETS
from tests.unit.config.edges.test_named import TIMED

TEMPLATES = tomllib.loads((REPO_ROOT / "config/site/positions/templates.toml").read_text())
HOLDS = [18, 19, 24]
WHEEL = {"position": "covered_call", "strike_delta": 0.3, "tenor_days": 28}


def _wanted(wheel: dict[str, Any] | None, holds: list[int] = HOLDS) -> list:  # type: ignore[type-arg]
    outcome = {
        "kind": "option_pnl", "horizon_sessions": holds, "benchmark": "none", "tenor_days": 14,
        "start_offset_sessions": 1, "position": "short_put", "strike_delta": 0.2,
    }  # fmt: skip
    if wheel:
        outcome["wheel"] = wheel  # type: ignore[assignment]
        outcome["book"] = True  # type: ignore[assignment]  # the spot path the cycle reads
    doc = document(
        schedule="calendar:after_monthly_expiry", base="delta_equivalent", screeners=[],
        universe=TIMED["universe"], outcome=outcome,
    )  # fmt: skip
    docs = {**PRESETS, ("site", "edges", "drift"): doc,
            ("site", "positions", "templates"): TEMPLATES}  # fmt: skip
    configs = MemoryConfigStore(docs)
    return positions_wanted(load_edges(configs), load_templates(configs))


def test_a_wheel_stores_both_phases_at_every_hold() -> None:
    wanted = _wanted(WHEEL)
    assert all(w.outcome.position.book for w in wanted)  # both phases store the spot path
    keys = [(parse_position_key(w.key), w.hold) for w in wanted]
    puts = [(k, h) for k, h in keys if not any(leg.kind == "shares" for leg in k.legs)]
    calls = [(k, h) for k, h in keys if any(leg.kind == "shares" for leg in k.legs)]
    assert sorted(h for _, h in puts) == HOLDS and sorted(h for _, h in calls) == HOLDS
    assert {(k.strike_delta, k.tenor_days) for k, _ in puts} == {(0.2, 14)}
    assert {(k.strike_delta, k.tenor_days, k.collateral) for k, _ in calls} == {
        (0.3, 28, "notional")
    }
    assert len({w.key for w in wanted}) == 2 * len(HOLDS)


def test_an_edge_without_a_wheel_stores_no_call_phase() -> None:
    wanted = _wanted(None, [17])  # one hold: only a wheel holds one per gap
    assert [w.hold for w in wanted] == [17]
    assert not any(leg.kind == "shares" for w in wanted for leg in parse_position_key(w.key).legs)
