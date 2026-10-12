"""``accepted_payload``: the saved feature's formula, fingerprint, unit and description join the
subject; a feature that is not there, or does not parse, leaves the subject only."""

from typing import Any

from algotrade.config.site.features.definitions import feature_definitions
from algotrade.features.expressions.fingerprint import fingerprint
from algotrade.services.feedback.formulas.payload import MAX_DESCRIPTION, accepted_payload

SECTION = {
    "expr": "price_stats.hv20 *   100",
    "dtype": "float",
    "unit": "pct_points",
    "description": "hv20 in percent",
    "null_meaning": "hv20 is null",
}
DOCS: dict[str, dict[str, Any]] = {"builder": {"hv_pct": SECTION}}


def test_the_saved_feature_is_in_the_payload_under_its_own_name() -> None:
    got = accepted_payload("draft_hv", "alice", "hv_pct", DOCS)  # the trader renamed it
    (definition,) = feature_definitions(DOCS, "alice")
    found = fingerprint(definition)
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
    other = {"b": SECTION | {"expr": "100 * price_stats.hv20"}}
    one = accepted_payload("a", "alice", "hv_pct", DOCS)["fingerprint"]
    two = accepted_payload("a", "alice", "b", {"t": other})["fingerprint"]
    assert one == two


def test_no_feature_name_a_missing_feature_or_a_broken_formula_is_subject_only() -> None:
    only = {"subject": "draft_hv", "picked": None}
    assert accepted_payload("draft_hv", "alice", None, DOCS) == only
    assert accepted_payload("draft_hv", "alice", "", DOCS) == only
    assert accepted_payload("draft_hv", "alice", "absent", DOCS) == only
    assert accepted_payload("draft_hv", "alice", "hv_pct", {}) == only
    assert accepted_payload("draft_hv", "alice", "hv_pct", {"t": None}) == only
    broken = {"t": {"hv_pct": SECTION | {"expr": "nope ("}}}
    assert accepted_payload("draft_hv", "alice", "hv_pct", broken) == only
    assert accepted_payload("draft_hv", "alice", "hv_pct", {"t": {"hv_pct": "junk"}}) == only
    assert accepted_payload("draft_hv", "alice", "hv_pct", {"t": {"hv_pct": {}}}) == only


def test_the_description_is_bounded() -> None:
    long = {"t": {"x": SECTION | {"description": "d" * 5000}}}
    assert len(accepted_payload("a", "alice", "x", long)["description"]) == MAX_DESCRIPTION
