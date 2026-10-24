"""The viewer's screeners, and criterion groups in the read model (ADR 0071): a group row of
``results/rule_screen_values`` is a ``ScreenGroup`` on the result, never a criterion; member rows
name their parent."""

from datetime import timedelta

import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.screens import results, screeners
from algotrade.services.read.screens.results import CriterionResult, load_results
from algotrade.services.read.screens.runs import latest_run
from algotrade.services.read.screens.screeners import (
    ScreenColumn,
    ScreenCriterion,
    Screener,
    ScreenGroup,
    load_screener,
    load_screeners,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.schemas import GROUP_MODE, is_criterion_row, is_group_row
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.screens.conftest import CONFIGS, D1, T, context, write_gated


def test_one_screener_per_id_the_users_own_config_first(ctx: ReadContext) -> None:
    found = {s.id: s for s in load_screeners(ctx)}
    assert list(found) == ["alpha", "beta", "gamma"]
    assert (found["alpha"].owner, found["alpha"].scope, found["alpha"].name) == (
        "site", "site", "Alpha"
    )  # fmt: skip
    beta = found["beta"]  # me's own beta wins over the site preset of the same id
    assert (beta.owner, beta.scope, beta.name, beta.version) == ("me", "me", "My beta", 2)
    assert found["gamma"].name == "gamma"  # no name: the id
    assert beta.hash


def test_another_user_sees_the_presets(reader: StoreReader) -> None:
    others = load_screeners(context(reader, user="you"))
    assert [(s.id, s.owner) for s in others] == [("alpha", "site"), ("beta", "site")]


def test_only_rule_screens_that_resolve(reader: StoreReader) -> None:
    docs = {
        ("site", "strategies", "trend"): {"id": "trend", "kind": "strategy", "impl": "sma"},
        ("me", "screeners", "broken@1"): {"id": "broken", "kind": "screener", "impl": "rules"},
    }
    ctx = context(reader, docs)
    assert [s.id for s in load_screeners(ctx)] == ["alpha", "beta", "gamma"]
    assert load_screener(ctx, "trend") is None
    assert load_screener(ctx, "broken") is None
    assert load_screener(ctx, "nope") is None
    assert isinstance(load_screener(ctx, "alpha"), Screener)


def test_criteria_and_display_columns_in_spec_order(reader: StoreReader) -> None:
    doc = {
        "id": "cols", "kind": "screener", "impl": "rules", "version": 1,
        "selection": "all_active",
        "criteria": {
            "price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 5},
            "adv": {"field": "rollup.price_stats@v2.adv_usd_20d", "op": "gte", "value": 1},
        },
        "columns": {"close": "rollup.price_stats@v2.close"},
    }  # fmt: skip
    found = load_screener(context(reader, {("me", "screeners", "cols@1"): doc}), "cols")
    assert found is not None
    assert found.criteria == (
        ScreenCriterion("price", "rollup.price_stats@v2.close", "hard", "gt", 5),
        ScreenCriterion("adv", "rollup.price_stats@v2.adv_usd_20d", "hard", "gte", 1),
    )
    assert found.display_columns == (ScreenColumn("close", "rollup.price_stats@v2.close"),)


def test_criteria_carry_the_configs_op_and_threshold(reader: StoreReader) -> None:
    """The web reads each rule from here, not from the untyped resolved config (whose criteria
    sit under ``rules``): op and value are the config's, a list stays a tuple, none is None."""
    doc = {
        "id": "ops", "kind": "screener", "impl": "rules", "version": 1,
        "selection": "all_active",
        "criteria": {
            "band": {"field": "rollup.price_stats@v2.close", "op": "between", "value": [5, 10]},
            "kind": {"field": "instrument.security_type", "op": "in", "value": ["ETF", "ADR"]},
            "has": {"field": "instrument.sector", "op": "not_null"},
        },
    }  # fmt: skip
    found = load_screener(context(reader, {("me", "screeners", "ops@1"): doc}), "ops")
    assert found is not None
    assert [(c.id, c.op, c.value) for c in found.criteria] == [
        ("band", "between", (5, 10)),
        ("kind", "in", ("ETF", "ADR")),
        ("has", "not_null", None),
    ]


def test_screeners_resolve_once_across_requests_until_a_version_is_saved(
    reader: StoreReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One page load asks for the screeners three times (regime strip, status strip, ideas);
    resolving re-reads every config's TOML, so a later request shares the first's answer, and a
    saved version (a new key) is seen at once."""
    calls: list[str] = []
    real = screeners._resolved

    def counting(ctx: ReadContext, config_id: str, owner: str) -> Screener | None:
        calls.append(config_id)
        return real(ctx, config_id, owner)

    monkeypatch.setattr(screeners, "_resolved", counting)
    first = context(reader)
    assert load_screeners(first) == load_screeners(first)
    assert len(calls) == 3

    # a later request: its own context over the same shared cache
    later = open_context(reader, first.configs, UserContext("me"), cache=first.cache)
    load_screeners(later)
    assert len(calls) == 3

    beta2 = CONFIGS[("me", "screeners", "beta@2")]
    saved = {**CONFIGS, ("me", "screeners", "beta@3"): {**beta2, "version": 3}}
    after = open_context(reader, MemoryConfigStore(saved), UserContext("me"), cache=first.cache)
    assert {s.id: s.version for s in load_screeners(after)}["beta"] == 3


def _row(criterion: str, field: str, mode: str, outcome: str, parent: str | None, **extra: object):
    return {
        "instrument_id": "EQ:AAA", "user_id": "site", "config_id": "alpha",
        "criterion_id": criterion, "field": field, "mode": mode, "value_num": 41.0,
        "value_str": None, "outcome": outcome, "distance": None, "group_id": parent, **extra,
    }  # fmt: skip


def write_grouped(backend: MemoryBackend) -> None:
    """``alpha``'s run ``r2``: AAA has the gate ``oversold`` (any of ``dip``, an all of ``rsi``
    and ``vol``, and ``low``) that fails on ``low`` while ``rsi`` passes, plus a plain ``q``."""
    write_gated(backend)
    rows = [
        _row("rsi", "feature.rsi", "hard", "PASS", "dip"),
        _row("vol", "feature.vol", "hard", "FAIL", "dip"),
        _row("low", "feature.low", "hard", "FAIL", "oversold"),
        _row("q", "feature.q", "hard", "PASS", None),
        _row("dip", "all", GROUP_MODE, "FAIL", "oversold", value_str="vol", value_num=None),
        _row("oversold", "any", GROUP_MODE, "FAIL", None, value_str="low", value_num=None),
    ]
    stored = stamped(rows, D1, "r2", T + timedelta(hours=2))
    StoreWriter(backend).write_result("rule_screen_values", D1, "r2", stored)


def test_a_group_row_is_a_screen_group_never_a_criterion(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_grouped(backend)
    ctx = context(reader)
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    found = load_results(ctx, {"r2": ["EQ:AAA"]}, [run])[("r2", "EQ:AAA")]
    assert [(c.id, c.group) for c in found.criteria] == [
        ("rsi", "dip"), ("vol", "dip"), ("low", "oversold"), ("q", None)
    ]  # fmt: skip
    assert all(not is_group_row(c.mode) for c in found.criteria)
    assert found.groups == (
        ScreenGroup("dip", "all", ("rsi", "vol"), "oversold", "FAIL", "vol"),
        ScreenGroup("oversold", "any", ("dip", "low"), None, "FAIL", "low"),
    )


def test_a_group_over_a_field_the_viewer_may_not_see_is_missing_to_them(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_grouped(backend)
    trader = context(reader, user="trader")  # holds no licence; the stored fields fail closed
    run = latest_run(trader, "site", "alpha").run
    assert run is not None
    found = load_results(trader, {"r2": ["EQ:AAA"]}, [run])[("r2", "EQ:AAA")]
    assert {g.id: (g.outcome, g.decided_by) for g in found.groups} == {
        "dip": ("MISSING", None),
        "oversold": ("MISSING", None),
    }
    assert {c.outcome for c in found.criteria} == {"MISSING"}


def test_an_older_partition_without_group_rows_reads_no_groups(ctx: ReadContext) -> None:
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    found = load_results(ctx, {"r1": ["EQ:AAA"]}, [run])[("r1", "EQ:AAA")]
    assert found.groups == ()
    assert found.criteria == (
        CriterionResult("iv30", "feature.vrp_iv30", "hard", "PASS", "high", None, None),
    )


def test_a_sort_key_never_resolves_to_a_group_row(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_grouped(backend)
    ctx = context(reader)
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    assert results._stored_key(ctx, run, "criterion:oversold") == {}
    assert results._stored_key(ctx, run, "criterion:q") == {"EQ:AAA": 41.0}


def test_the_row_predicates_agree() -> None:
    assert is_criterion_row("hard") and is_criterion_row("score")
    assert not is_criterion_row("column") and not is_criterion_row(GROUP_MODE)
