"""The missing-data notes: a model note that says names with no value pass is dropped, the true
note is added once per field of an exclusion, and a draft with no exclusion gets none."""

import json

from algotrade.services.drafting.contract.missing_notes import (
    exclusion_notes,
    without_false_claims,
)
from tests.conftest import REPO_ROOT

RAW = REPO_ROOT / "tests/fixtures/drafting/golden/answers/claude-cli-claude-sonnet-5-5"
DOC = {
    "criteria": {
        "a": {"field": "feature.iv_rank"},
        "b": {"field": "feature.iv_rank"},
        "c": {"field": "feature.market_cap"},
        "d": {"field": "feature.price"},
    },
    "groups": {"g1": {"none": ["a", "b", "c"]}, "g2": {"any": ["d"]}},
}


def test_a_note_saying_missing_names_pass_is_dropped() -> None:
    kept = without_false_claims(
        (
            "Names with no IV rank (null) are not excluded by the exclusion.",
            "Missing values are kept in the result.",
            "Thresholds follow the phrasebook.",
        )
    )
    assert kept == ("Thresholds follow the phrasebook.",)


def test_the_note_the_model_once_recorded_is_the_one_dropped() -> None:
    old = (
        "Names with no IV rank (null) are not excluded by the exclusion, since a null does not "
        "meet IV rank above 0.8."
    )
    assert without_false_claims((old,)) == ()
    raw = json.loads((RAW / "groups-except-a.json").read_text())["notes"]
    assert without_false_claims(raw) != tuple(raw)  # the raw recording still has such a note


def test_one_note_per_field_of_an_exclusion_never_duplicated() -> None:
    assert exclusion_notes(DOC) == (
        "Names with no iv rank are also left out (missing data never passes).",
        "Names with no market cap are also left out (missing data never passes).",
    )


def test_no_exclusion_no_note() -> None:
    assert exclusion_notes({"criteria": DOC["criteria"], "groups": {"g": {"any": ["a"]}}}) == ()
    assert exclusion_notes({"criteria": DOC["criteria"]}) == ()
