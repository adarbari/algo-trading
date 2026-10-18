"""Criterion groups in the read model (ADR 0071): a group row of ``results/rule_screen_values``
is a ``ScreenGroup`` on the result, never a criterion; member rows name their parent."""

from datetime import timedelta

from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens import results
from algotrade.services.read.screens.results import CriterionResult, load_results
from algotrade.services.read.screens.runs import latest_run
from algotrade.services.read.screens.screeners import ScreenGroup
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.schemas import GROUP_MODE, is_criterion_row, is_group_row
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.screens.conftest import D1, T, context, write_gated


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
        ScreenGroup("oversold", "any", ("low", "dip"), None, "FAIL", "low"),
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
