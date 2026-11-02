"""``Query.edgeOptionSetup`` serves the read model's option setup as it is (ADR 0088, plan O1):
every figure null with its reason, never a zero, one resolver for one loader, and no
catalogue-named field on ``Edge``."""

from datetime import date

from algotrade.services.read.evaluation.positions import option_evidence, option_setup
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade_api.graphql.schema import schema
from algotrade_api.graphql.types.evaluation.positions.option_setup import OptionSetup


def test_a_setup_is_served_with_its_rules_and_evidence_as_the_read_model_has_them() -> None:
    leg = option_setup.LegRule("option", -1, "P", "delta", 0.25, None, None)
    rules = option_setup.OptionRules(
        "short_put", (leg,), "cash_secured", "every_session", 1, 30, "monthly", True,
        0.5, 2.0, 21, ("rollup.x",), (), (20,),
    )  # fmt: skip
    year = option_evidence.OptionYear(2025, 2, -0.15, 0)
    stress = option_evidence.StressWindow(
        "fall", "Fall", date(2025, 11, 1), date(2025, 11, 20), 0, None
    )
    evidence = option_evidence.OptionEvidence(
        None, "momo", 20, 20, 0.085, 0.0375, 0.1325, -0.2, 1, 18, None, (year,), (stress,)
    )
    served = OptionSetup.of(option_setup.OptionSetup("drift", "options", rules, None, evidence))
    assert served.position_kind == "options" and served.rules_unknown is None
    assert served.rules is not None and served.rules.legs[0].delta == 0.25
    assert (served.rules.take_profit, served.rules.exit_condition_fields) == (0.5, ["rollup.x"])
    assert served.evidence is not None and served.evidence.costs is None
    assert (served.evidence.typical, served.evidence.bad_trades) == (0.085, 1)
    assert served.evidence.stress[0].worst is None and served.evidence.stress[0].trades == 0


def test_a_share_setup_has_no_sections_and_says_why() -> None:
    why = Unknown(UnknownCode.NOT_APPLICABLE, None)  # type: ignore[arg-type]
    served = OptionSetup.of(option_setup.OptionSetup("drift", "shares", None, why, None))
    assert served.position_kind == "shares" and served.rules is None and served.evidence is None
    assert served.rules_unknown is not None


def test_the_field_is_on_the_root_and_the_edge_gains_no_option_fields() -> None:
    sdl = schema.as_str()
    query = sdl[sdl.index("type Query {") :].split("\n}")[0]
    assert "edgeOptionSetup(" in query
    edge = sdl[sdl.index("type Edge {") :].split("\n}")[0]
    assert "optionSetup" not in edge and "typical" not in edge
