"""The ids of a named sleeve's position baselines (ADR 0088 G19): one per (template, symbol)."""

from algotrade.config.edges.positions.templates import paired_symbol, sleeve_baseline_id


def test_a_sleeve_baseline_id_round_trips_and_a_cross_section_one_pairs_with_every_pick() -> None:
    assert sleeve_baseline_id("long_shares", "SPY") == "position:long_shares:SPY"
    assert paired_symbol("position:long_shares:SPY") == "SPY"
    assert paired_symbol("position:long_shares") is None  # the cross-section's (E16)
    assert paired_symbol("momentum_12_1") is None  # a screener baseline
