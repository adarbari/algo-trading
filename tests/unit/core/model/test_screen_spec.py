"""The rule-screen spec values: modes, tolerance widths, the fields a screen reads."""

from algotrade.core.model.predicates import Group, Rule
from algotrade.core.model.screen_spec import Criterion, Mode, ScreenSpec, Tolerance


def test_tolerance_width_absolute_and_relative() -> None:
    assert Tolerance(0.02).width(0.5) == 0.02
    assert Tolerance(0.1, relative=True).width(-50.0) == 5.0


def test_only_score_mode_never_gates() -> None:
    assert Mode.HARD.gating and Mode.SOFT.gating and not Mode.SCORE.gating


def test_fields_cover_criteria_groups_columns_classify_and_tie_break() -> None:
    spec = ScreenSpec(
        id="s",
        criteria=(Criterion("a", Rule("f.a", "gt", 1)),),
        tiers=(("T", Group("all", (Rule("f.t", "eq", 1),))),),
        flags=(("x", Group("not", (Rule("f.a", "eq", 2),))),),
        classify="f.c",
        columns=(("col", "f.col"),),
        tie_break="f.tb",
    )
    assert spec.fields() == ("f.a", "f.c", "f.col", "f.t", "f.tb")
    assert spec.criteria[0].field == "f.a" and spec.criteria[0].on_miss == "WATCH"
