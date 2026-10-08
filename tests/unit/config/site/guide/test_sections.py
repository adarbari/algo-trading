"""``config/site/guide/sections.toml`` (ADR 0051): the fitness tests over the shipped file
(every field-guide theme in exactly one group; every site rule-screen preset in exactly one
family, and every listed preset exists; the sections in the spec's order), then the loader's
shape checks."""

from typing import Any

import pytest

from algotrade.config.site.guide.sections import SECTIONS, GuideSections, load_guide_sections
from algotrade.config.site.settings import load_field_guide
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import SCREENERS, FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")


def test_every_field_guide_theme_is_in_exactly_one_group() -> None:
    groups = load_guide_sections(SHIPPED).theme_groups
    listed = [t for g in groups for t in g.themes]
    used = {f.theme for f in load_field_guide(SHIPPED).fields}
    assert sorted(listed) == sorted(set(listed)), "a theme in two groups"
    assert set(listed) == used, (
        f"group every field-guide theme once in config/site/guide/sections.toml: missing "
        f"{sorted(used - set(listed))}, not a theme {sorted(set(listed) - used)}"
    )


def test_every_site_preset_is_in_exactly_one_family_and_every_listed_one_exists() -> None:
    listed = load_guide_sections(SHIPPED).presets
    presets = SHIPPED.names("site", SCREENERS)
    assert len(listed) == len(set(listed)), "a preset in two families"
    assert sorted(listed) == presets, (
        f"put every site rule-screen preset in one family of config/site/guide/sections.toml: "
        f"missing {sorted(set(presets) - set(listed))}, no such preset "
        f"{sorted(set(listed) - set(presets))}"
    )


def test_the_shipped_sections_follow_the_spec() -> None:
    shipped = load_guide_sections(SHIPPED)
    assert tuple(s.id for s in shipped.sections) == SECTIONS
    assert [s.title for s in shipped.sections][:2] == ["Start here", "Market regime"]
    assert [f.id for f in shipped.families] == [
        "trend",
        "breakouts",
        "reversals",
        "income",
        "events",
    ]
    assert shipped.families[1].presets == ("range_breakout", "breakout", "failed_breakout")
    assert shipped.theme_groups[0].themes == ("instrument gates", "liquidity")


SECTION = {"id": "fields", "title": "Fields", "purpose": "Every field."}
GROUP = {"id": "chart", "title": "The chart", "themes": ["volume", "volatility"]}
FAMILY = {"id": "trend", "title": "Trend", "presets": ["pullback"]}


def test_a_document_is_typed_in_order_and_a_missing_file_has_nothing() -> None:
    doc = {"section": [SECTION], "theme_group": [GROUP], "family": [FAMILY]}
    found = load_guide_sections(MemoryConfigStore({("site", "guide", "sections"): doc}))
    assert found.sections[0].purpose == "Every field."
    assert found.theme_groups[0].themes == ("volume", "volatility")
    assert found.presets == ("pullback",)
    assert load_guide_sections(MemoryConfigStore({})) == GuideSections()


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"section": [{**SECTION, "id": "faq"}]}, "got 'faq'"),
        ({"section": [{"title": "x", "purpose": "y"}]}, "id: expected one of"),
        ({"section": [SECTION, SECTION]}, "section ids listed more than once"),
        ({"section": [{**SECTION, "purpose": "  "}]}, "purpose: expected a non-empty string"),
        ({"theme_group": [{**GROUP, "themes": []}]}, "themes: expected one or more"),
        ({"theme_group": [GROUP, {**GROUP, "id": "b"}]}, r"themes listed more than once: \['vol"),
        ({"family": [FAMILY, {**FAMILY, "id": "b"}]}, "presets listed more than once"),
        ({"family": [{**FAMILY, "colour": "red"}]}, "unknown keys"),
        ({"family": {"id": "x"}}, r"expected a list of tables \(\[\[family\]\]\)"),
        ({"chapter": []}, "unknown keys"),
        ({"section": [SECTION], "api_key": "x"}, "looks like a secret"),
    ],
)
def test_bad_documents_fail_naming_the_file(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        GuideSections.from_document(doc)
