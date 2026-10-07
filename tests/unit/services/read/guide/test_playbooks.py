"""The site playbooks the Guide reads: Guide order (families first, then the rest by id), the
latest version, a non-rule-screen preset left out; each rule as text."""

from typing import Any

import pytest

from algotrade.config.strategy.screen_spec import parse_criterion
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.playbooks import rule_text, site_playbooks
from tests.unit.services.read.guide.conftest import ADV, stores


def test_presets_in_guide_order_latest_version_rule_screens_only(ctx: StoreContext) -> None:
    found = site_playbooks(ctx)
    assert [(p.id, p.name, p.family) for p in found] == [
        ("alpha", "Alpha", "trend"),  # v2 (the latest) names it
        ("zeta", "Zeta", None),  # in no family: after the families
    ]  # "missing" is listed but not stored; "broken" is not a rule screen
    assert [c.id for c in found[0].spec.criteria] == ["adv", "band", "listed"]


def test_without_sections_every_preset_is_by_id() -> None:
    found = site_playbooks(
        stores({("site", "screeners", "b@1"): _doc("b"), ("site", "screeners", "a@1"): _doc("a")})
    )
    assert [(p.id, p.family) for p in found] == [("a", None), ("b", None)]


def test_a_preset_that_does_not_parse_is_left_out() -> None:
    bad = {**_doc("a"), "criteria": {}}
    assert site_playbooks(stores({("site", "screeners", "a@1"): bad})) == ()


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        ({"op": "gte", "value": 50_000_000, "mode": "soft", "tolerance": {"relative": 0.2}},
         "gte 50000000 soft tolerance relative 0.2"),
        ({"op": "between", "value": [-0.5, 0.5], "mode": "soft", "tolerance": 0.25},
         "between [-0.5, 0.5] soft tolerance 0.25"),
        ({"op": "in", "value": ["ETF", "ADR"]}, "in [ETF, ADR] hard"),
        ({"op": "eq", "value": True, "mode": "score"}, "eq true score"),
        ({"op": "not_null"}, "not_null hard"),
        ({"op": "gt", "value": 2.0, "mode": "soft", "tolerance": 1.0}, "gt 2 soft tolerance 1"),
    ],
)  # fmt: skip
def test_a_rule_reads_in_the_grammars_words(raw: dict[str, Any], text: str) -> None:
    criterion = parse_criterion("c", {"field": ADV, **raw}, "c")
    assert criterion is not None and rule_text(criterion) == text


def _doc(config_id: str) -> dict[str, Any]:
    return {
        "id": config_id,
        "kind": "screener",
        "impl": "rules",
        "criteria": {"c": {"field": ADV, "op": "gt", "value": 1}},
    }
