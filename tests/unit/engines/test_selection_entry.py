"""``first_entry`` (ADR 0088, design 2.4a): the first TRUE close of the wait enters; FALSE closes
continue it; an UNKNOWN close before a TRUE one stops it (``ENTRY_UNKNOWN``); never TRUE is
``NOT_TRIGGERED``. Pure and deterministic."""

from hypothesis import given
from hypothesis import strategies as st

from algotrade.config.strategy.schema import parse_group
from algotrade.engines.selection.entry import ENTRY_UNKNOWN, NOT_TRIGGERED, first_entry

DIP = parse_group({"all": [{"field": "x", "op": "lt", "value": 0}]}, "entry")
LABEL = parse_group({"all": [{"field": "s", "op": "ne", "value": "calm"}]}, "entry")


def test_the_first_true_close_enters() -> None:
    assert first_entry(DIP, [{"x": -1}]).close == 0
    assert first_entry(DIP, [{"x": 1}, {"x": 2}, {"x": -1}, {"x": -2}]).close == 2


def test_never_true_in_the_wait_is_not_triggered() -> None:
    found = first_entry(DIP, [{"x": 1}, {"x": 0}])
    assert (found.close, found.reason, found.entered) == (None, NOT_TRIGGERED, False)
    assert first_entry(DIP, []).reason == NOT_TRIGGERED


def test_an_unknown_close_before_a_true_one_stops_the_wait() -> None:
    for missing in ({}, {"x": None}, {"x": float("nan")}, {"x": "low"}):
        found = first_entry(DIP, [{"x": 1}, missing, {"x": -1}])
        assert (found.close, found.reason) == (None, ENTRY_UNKNOWN)
    assert first_entry(DIP, [{"x": -1}, {}]).close == 0  # decided before the gap


def test_a_label_outside_its_domain_is_unknown_never_true() -> None:
    domains = {"s": ("calm", "stressed")}
    assert first_entry(LABEL, [{"s": "stressed"}], domains).close == 0
    assert first_entry(LABEL, [{"s": "panic"}], domains).reason == ENTRY_UNKNOWN
    assert first_entry(LABEL, [{"s": "calm"}], domains).reason == NOT_TRIGGERED


@given(st.lists(st.one_of(st.none(), st.floats(-2, 2, allow_nan=False)), max_size=8))
def test_the_decision_is_deterministic_and_reads_no_close_after_it(values: list) -> None:
    closes = [{} if v is None else {"x": v} for v in values]
    found = first_entry(DIP, closes)
    assert found == first_entry(DIP, closes)
    if found.close is not None:  # what comes after the entry close cannot change it
        assert first_entry(DIP, closes[: found.close + 1]) == found
