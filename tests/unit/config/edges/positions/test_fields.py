"""``POSITION_FIELDS``: each field names a Guide term that exists, applies to the legs it says,
and the catalogue offers a template only the fields that apply to its legs (design 2.4a, G12)."""

import pytest

from algotrade.config.edges.positions.fields import (
    POSITION_FIELDS,
    fields_for,
    is_credit,
)
from algotrade.config.edges.positions.templates import load_templates
from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
TEMPLATES = load_templates(SHIPPED)


def test_every_position_field_has_its_guide_term_and_each_term_a_field() -> None:
    terms = {t.id for t in load_guide_glossary(SHIPPED).terms if t.id.startswith("position_")}
    assert {f.guide for f in POSITION_FIELDS} == terms
    assert len({f.name for f in POSITION_FIELDS}) == len(POSITION_FIELDS) == 7


@pytest.mark.parametrize(
    ("template", "credit"),
    [("short_put", True), ("put_spread", True), ("covered_call", True), ("short_straddle", True),
     ("iron_fly", True), ("long_shares", False), ("short_shares", False)],
)  # fmt: skip
def test_which_templates_are_net_credit_positions(template: str, credit: bool) -> None:
    assert is_credit(TEMPLATES[template]) is credit


def test_a_field_applies_only_to_the_legs_it_is_for() -> None:
    shares = set(fields_for(TEMPLATES["long_shares"]))
    assert shares == {"position.days_held", "position.move_since_entry_pct"}
    put = set(fields_for(TEMPLATES["short_put"]))
    assert put == {f"position.{f.name}" for f in POSITION_FIELDS}
    assert fields_for(TEMPLATES["short_put"])["position.dte"] == "int"
