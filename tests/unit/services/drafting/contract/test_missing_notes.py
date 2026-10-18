"""The missing-data notes: a model note that says names with no value pass is dropped, the true
note is added once per field of an exclusion and worded for its mode, and a draft with no
exclusion gets none."""

import json
from types import SimpleNamespace

import pytest

from algotrade.services.drafting.contract.missing_notes import (
    exclusion_notes,
    field_labels,
    without_false_claims,
)
from tests.conftest import REPO_ROOT

RAW = REPO_ROOT / "tests/fixtures/drafting/golden/answers/claude-cli-claude-sonnet-5-5"
TAIL = "(missing data never passes)."


def doc(*members: tuple[str, str], groups: dict | None = None) -> dict:
    criteria = {f"c{i}": {"field": f, "mode": m} for i, (f, m) in enumerate(members)}
    return {"criteria": criteria, "groups": groups or {"g": {"none": list(criteria)}}}


@pytest.mark.parametrize(
    ("note", "kept"),
    [
        ("Names with no IV rank (null) are not excluded by the exclusion.", False),
        ("Missing values pass the exclusion.", False),
        ("Names with no value for market cap are included.", False),
        ("Names with no IV rank are kept out of the result.", True),
        ("Names with no IV rank still appear in the funnel as rejected.", True),
        ("Thresholds follow the phrasebook.", True),
    ],
)
def test_a_note_saying_missing_names_pass_is_dropped(note: str, kept: bool) -> None:
    assert (without_false_claims((note,)) == (note,)) is kept


def test_the_note_the_model_once_recorded_is_the_one_dropped() -> None:
    raw = json.loads((RAW / "groups-except-a.json").read_text())["notes"]
    assert without_false_claims(raw) != tuple(raw)  # the raw recording still has such a note


@pytest.mark.parametrize(
    ("mode", "note"),
    [
        ("hard", f"Names with no iv rank are also left out {TAIL}"),
        ("soft", f"Names with no iv rank stay in but are marked down {TAIL}"),
        ("score", f"Names with no iv rank score lower {TAIL}"),
    ],
)
def test_the_note_matches_the_mode_of_the_member(mode: str, note: str) -> None:
    assert exclusion_notes(doc(("feature.iv_rank", mode))) == (note,)


def test_one_note_per_field_and_mode_never_duplicated() -> None:
    notes = exclusion_notes(
        doc(("feature.iv_rank", "hard"), ("feature.iv_rank", "hard"), ("feature.price", "hard"))
    )
    assert len(notes) == 2 and "iv rank" in notes[0] and "price" in notes[1]


def test_no_exclusion_no_note() -> None:
    assert exclusion_notes(doc(("feature.a", "hard"), groups={"g": {"any": ["c0"]}})) == ()
    assert exclusion_notes({"criteria": {"c": {"field": "feature.a"}}}) == ()


def test_a_member_that_is_a_group_is_skipped_on_purpose() -> None:
    """A ``none`` over an ``all`` passes on one known negated member: no field decides it."""
    document = doc(
        ("feature.a", "hard"), groups={"n": {"none": ["inner"]}, "inner": {"all": ["c0"]}}
    )
    assert exclusion_notes(document) == ()


def test_a_field_is_named_by_its_catalogue_words() -> None:
    infos = {
        "feature.pct_vs_sma_50": SimpleNamespace(
            description="Close vs its 50-day SMA, in percent."
        ),
        "feature.iv_rank": SimpleNamespace(description="IV rank, 0 to 1."),
    }
    document = doc(("feature.pct_vs_sma_50", "hard"), ("feature.iv_rank", "hard"))
    assert exclusion_notes(document, field_labels(infos, document)) == (
        f"Names with no close vs its 50-day SMA are also left out {TAIL}",
        f"Names with no IV rank are also left out {TAIL}",
    )
