"""``accepted_payload``: the saved feature's formula, fingerprint, unit and description join the
subject; a feature that is not there, or does not parse, leaves the subject only."""

from algotrade.config.site.features.definitions import FeatureDefinition, feature_definitions
from algotrade.features.expressions.fingerprint import fingerprint
from algotrade.services.feedback.formulas.payload import MAX_DESCRIPTION, accepted_payload

SECTION = {
    "expr": "price_stats.hv20 *   100",
    "dtype": "float",
    "unit": "pct_points",
    "description": "hv20 in percent",
    "null_meaning": "hv20 is null",
}


def saved(**sections: dict[str, str]) -> list[FeatureDefinition]:
    return list(feature_definitions({"builder": sections}, "alice"))


DOCS = saved(hv_pct=SECTION)


def test_the_saved_feature_is_in_the_payload_under_its_own_name() -> None:
    (definition,) = DOCS
    found = fingerprint(definition)
    got = accepted_payload("draft_hv", "hv_pct", DOCS, found.hash)  # the trader renamed it
    assert got == {
        "subject": "draft_hv",
        "picked": None,
        "feature": "hv_pct",
        "expression": "price_stats.hv20 * 100",  # whitespace collapsed
        "fingerprint": found.hash,
        "canonical": found.text,
        "unit": "pct_points",
        "description": "hv20 in percent",
    }


def test_the_same_formula_written_differently_has_one_fingerprint() -> None:
    other = saved(b=SECTION | {"expr": "100 * price_stats.hv20"})
    one = fingerprint(DOCS[0]).hash
    two = accepted_payload("draft_a", "b", other, one)["fingerprint"]
    assert one == two


def test_no_feature_name_a_missing_feature_or_a_broken_formula_is_subject_only() -> None:
    only = {"subject": "draft_hv", "picked": None}
    assert accepted_payload("draft_hv", None, DOCS) == only
    assert accepted_payload("draft_hv", "", DOCS) == only
    assert accepted_payload("draft_hv", "absent", DOCS) == only
    assert accepted_payload("draft_hv", "hv_pct", []) == only


def test_a_feature_that_is_not_the_proposed_formula_is_subject_only() -> None:
    only = {"subject": "draft_hv", "picked": None}
    other = saved(hv_pct=SECTION, rsi=SECTION | {"expr": "price_stats.hv20 * 7"})
    one = accepted_payload(
        "draft_hv", "hv_pct", DOCS
    )  # no proposal known: name rule, a rename fails
    assert one == only
    assert (
        accepted_payload("draft_hv", "rsi", other, "0" * 12) == only
    )  # stale: another fingerprint
    assert (
        accepted_payload("draft_hv", "draft_hv", saved(draft_hv=SECTION))["feature"] == "draft_hv"
    )
    assert accepted_payload("draft_hv", "draft_other", saved(draft_other=SECTION))["feature"]


def test_the_description_is_bounded() -> None:
    long = saved(draft_x=SECTION | {"description": "d" * 5000})
    assert len(accepted_payload("a", "draft_x", long)["description"]) == MAX_DESCRIPTION
