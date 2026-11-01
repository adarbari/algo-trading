"""The composite label R1-R12 by hand: each label on a fixture row, the precedence, a label that
never skips an unknown rule, UNCLASSIFIED when every rule is off, and the R9 / R10 flags."""

from dataclasses import replace

import numpy as np
import pytest

from algotrade.features.rollups.market.edges import labels as lb

B = lb.Bands()
NAN = np.nan
# A session on which every rule is off: a caution-band VIX over an inverted curve that is not
# spiking, a rising market with wide breadth, options neither cheap nor rich.
OFF = lb.LabelReadings(
    vix=30.0, ratio=1.2, run=0.0, chg_5d=0.0, pct_252=50.0, vrp=3.0, drawdown=-0.01,
    sma_200=0.05, cross_50_200=0.02, breadth=0.6, breadth_falling=False, corr_ratio=0.8,
    credit_on=False, macro_high=False, cheap=False, recovery=False, rate_shock=False,
)  # fmt: skip


def label(**changes: object) -> str | None:
    return lb.classify(replace(OFF, **changes), B)


def test_every_rule_off_is_unclassified() -> None:
    assert label() == "UNCLASSIFIED"
    assert set(lb.rules(OFF, B).values()) == {False}


def test_r6_a_bear_market_with_high_inverted_volatility() -> None:
    bear = {
        "vix": 40.0,
        "sma_200": -0.1,
        "cross_50_200": -0.03,
        "run": 12.0,
        "breadth": 0.2,
        "credit_on": True,
    }
    assert label(**bear) == "R6"
    assert label(**{**bear, "run": 5.0}) != "R6"  # inverted for fewer than 10 closes
    assert label(**{**bear, "credit_on": False}) != "R6"


def test_r7_a_fresh_spike_in_backwardation() -> None:
    assert label(ratio=1.1, run=3.0, chg_5d=0.5, sma_200=0.0) == "R7"
    assert label(ratio=1.1, run=3.0, chg_5d=0.2, sma_200=0.0) != "R7"  # not up 40%
    assert label(ratio=1.1, run=3.0, chg_5d=0.5, sma_200=-0.2) != "R7"  # far below the trend


def test_r12_options_cheap_outside_a_recovery_and_r8_inside_one() -> None:
    assert label(cheap=True, ratio=0.9) == "R12"
    assert label(cheap=True, recovery=True, ratio=0.9) == "R8"
    assert label(recovery=True, ratio=0.9) == "R8"


def test_r5_a_rate_shock_grind_down() -> None:
    shock = {"sma_200": -0.08, "rate_shock": True, "vix": 30.0, "vrp": 6.0, "ratio": 0.9}
    assert label(**shock) == "R5"
    assert label(**{**shock, "vix": 20.0}) != "R5"  # not the caution band
    assert label(**{**shock, "vrp": 2.0}) != "R5"  # options not rich


def test_r4_a_correction_with_the_curve_sloping_up() -> None:
    assert label(vix=30.0, ratio=0.9, drawdown=-0.10) == "R4"
    assert label(vix=30.0, ratio=0.9, drawdown=-0.02) != "R4"  # not yet a correction
    assert label(vix=30.0, ratio=0.9, drawdown=-0.20) != "R4"  # deeper than a correction


def test_r3_a_narrow_rally_with_the_stocks_moving_apart() -> None:
    narrow = {"vix": 20.0, "ratio": 0.9, "breadth": 0.4, "breadth_falling": True, "corr_ratio": 0.2}
    assert label(**narrow) == "R3"
    assert label(**{**narrow, "corr_ratio": 0.6}) != "R3"
    assert label(**{**narrow, "breadth_falling": False}) != "R3"


def test_r2_a_low_volatility_grind() -> None:
    assert label(vix=13.0, pct_252=10.0, vrp=1.0, ratio=0.9) == "R2"
    assert label(vix=13.0, pct_252=10.0, vrp=3.0, ratio=0.9) != "R2"  # not thin


def test_r1_a_calm_uptrend_and_r11_macro_high_with_the_market_calm() -> None:
    assert label(vix=15.0, ratio=0.9, pct_252=50.0, vrp=5.0) == "R1"
    assert label(vix=15.0, ratio=0.97, macro_high=True) == "R11"
    assert label(vix=15.0, ratio=0.97, macro_high=False) == "UNCLASSIFIED"


def test_precedence_the_first_rule_that_holds_names_the_session() -> None:
    both = {
        "vix": 15.0,
        "ratio": 0.9,
        "pct_252": 10.0,
        "vrp": 1.0,
    }  # R2 holds; R1 needs vrp >= 0 too
    assert label(**both) == "R2"  # R2 before R1
    assert label(cheap=True, recovery=False, ratio=0.9, vix=15.0, pct_252=10.0, vrp=1.0) == "R12"


def test_a_label_never_skips_an_unknown_rule() -> None:
    # R1 would hold, but R6 (higher precedence) is unknown: unknown breadth with every other bear
    # condition true.
    bear_unknown = {
        "vix": 40.0,
        "sma_200": -0.1,
        "cross_50_200": -0.03,
        "run": 12.0,
        "breadth": NAN,
    }
    assert label(**bear_unknown, credit_on=True) is None
    assert label(**bear_unknown, credit_on=False) != None  # noqa: E711  one condition is off
    # an unknown rule below the one that holds does not matter
    assert label(cheap=True, ratio=0.9, corr_ratio=NAN, breadth=NAN) == "R12"


def test_unknown_inputs_with_nothing_off_make_the_label_unknown() -> None:
    unknown = lb.LabelReadings(
        NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, None, NAN, None, None, None, None, None
    )
    assert lb.classify(unknown, B) is None


def test_the_flags_are_r9_and_r10() -> None:
    assert lb.flags(0.2, 30.0, False, B) == (True, False)
    assert lb.flags(0.05, 3.0, False, B) == (False, True)
    assert lb.flags(0.05, NAN, True, B) == (False, True)  # an expiry week alone
    assert lb.flags(NAN, NAN, False, B) == (None, None)


def test_the_label_set_is_r1_to_r12_less_the_flags_and_unclassified() -> None:
    assert lb.LABELS[-1] == "UNCLASSIFIED"
    assert set(lb.PRECEDENCE) == {f"R{n}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 11, 12)}
    assert len(lb.LABELS) == len(set(lb.LABELS)) == 11
    with pytest.raises(KeyError):
        lb.rules(OFF, B)["R9"]
