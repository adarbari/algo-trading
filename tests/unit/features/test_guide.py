"""The field guide pages: the index (header, the themes with their fields, the situations)
and the theme pages in first appearance order under their theme group's folder, each field
with its reading, its criterion table, caveats and sources; a long theme split into parts at
entry boundaries; a theme in no group an error; stable bytes; an empty guide renders the
header alone."""

import pytest

from algotrade.config.site.field_guide import (
    FieldGuideEntry,
    FieldGuideSettings,
    GuideUse,
    Situation,
)
from algotrade.config.site.guide.sections import GuideSections, ThemeGroup
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.guide import (
    HEADER,
    PAGE_LINES,
    criterion_text,
    pages,
    render,
    theme_path,
)

RSI = FieldGuideEntry(
    name="rollup.a@v1.rsi",
    theme="momentum and trend",
    reads="0 to 100",
    uses=(
        GuideUse("oversold", "lt", 30, "soft", 5.0, "", "with a trend | filter"),
        GuideUse("liquid", "gte", 5e7, "soft", {"relative": 0.2}, "LIQUIDITY_RISK"),
        GuideUse("known", "not_null"),
        GuideUse("mid cap", "between", [2e9, 1e10]),
    ),
    caveats=("pinned by a deal",),
    sources=("Wilder (1978)", "Cardwell"),
)
CAP = FieldGuideEntry(name="feature.market_cap", theme="fundamentals", reads="dollars")
MOVE = FieldGuideEntry(name="feature.atr_pct", theme="momentum and trend", reads="range")
DEAL = Situation("pending takeover", "flat tape", ("rollup.a@v1.rsi", "feature.atr_pct"), "drop it")
GUIDE = FieldGuideSettings((RSI, CAP, MOVE), (DEAL,))
SECTIONS = GuideSections(
    theme_groups=(
        ThemeGroup("chart", "The chart", ("momentum and trend",)),
        ThemeGroup("company", "The company", ("fundamentals",)),
    )
)


def test_the_index_lists_themes_in_first_appearance_order_and_the_situations() -> None:
    index = render(GUIDE, SECTIONS)
    assert index.startswith(HEADER)
    assert "## Themes (3 fields)" in index
    momentum = index.index(
        "- [Momentum and trend](field-guide/chart/momentum-and-trend.md) (2): "
        "`rollup.a@v1.rsi`, `feature.atr_pct`"
    )
    assert momentum < index.index(
        "- [Fundamentals](field-guide/company/fundamentals.md) (1): `feature.market_cap`"
    )
    assert index.index("## Situations that fool several thresholds") > momentum
    assert "### Pending takeover" in index
    assert "**Affects.** `rollup.a@v1.rsi`, `feature.atr_pct`" in index
    assert "### `rollup.a@v1.rsi`" not in index  # the fields are on the theme pages
    assert index == render(GUIDE, SECTIONS)


def test_one_page_per_theme_with_the_fields_in_file_order() -> None:
    out = pages(GUIDE, SECTIONS)
    assert list(out) == [
        "docs/data/field-guide.md",
        "docs/data/field-guide/chart/momentum-and-trend.md",
        "docs/data/field-guide/company/fundamentals.md",
    ]
    page = out[theme_path("chart", "momentum and trend")]
    assert page.startswith("# Field guide: momentum and trend\n")
    assert "[field-guide.md](../../field-guide.md)" in page
    assert page.index("### `rollup.a@v1.rsi`") < page.index("### `feature.atr_pct`")
    assert "### `feature.market_cap`" in out["docs/data/field-guide/company/fundamentals.md"]


def test_an_entry_renders_its_reading_table_caveats_and_sources() -> None:
    page = pages(FieldGuideSettings((RSI,)), SECTIONS)[theme_path("chart", "momentum and trend")]
    assert "**How to read it.** 0 to 100" in page
    assert "| oversold | `lt 30` | soft | 5.0 | with a trend \\| filter |" in page
    assert "| liquid | `gte 50000000.0` | soft | 0.2 x the threshold, LIQUIDITY_RISK | - |" in page
    assert "| known | `not_null` | hard | - | - |" in page
    assert "| mid cap | `between [2000000000.0, 10000000000.0]` | hard | - | - |" in page
    assert "- pinned by a deal" in page and "Sources: Wilder (1978); Cardwell" in page
    assert criterion_text(GuideUse("x", "eq", "HIGH")) == 'eq "HIGH"'


def test_an_empty_guide_is_the_header() -> None:
    assert render(FieldGuideSettings(), SECTIONS) == HEADER.rstrip() + "\n"
    assert list(pages(FieldGuideSettings(), SECTIONS)) == ["docs/data/field-guide.md"]
    page = pages(FieldGuideSettings((CAP,)), SECTIONS)[theme_path("company", "fundamentals")]
    assert "**The criterion per intent**" not in page and "Sources:" not in page


def test_a_long_theme_is_split_at_entry_boundaries_into_numbered_parts() -> None:
    many = tuple(
        FieldGuideEntry(name=f"feature.f{i}", theme="momentum and trend", reads="r", caveats=("c",))
        for i in range(200)
    )
    guide = FieldGuideSettings(many)
    out = pages(guide, SECTIONS)
    first, second = (theme_path("chart", "momentum and trend", n) for n in (1, 2))
    assert list(out) == ["docs/data/field-guide.md", first, second]
    assert all(len(t.splitlines()) <= PAGE_LINES for p, t in out.items() if p != next(iter(out)))
    assert out[second].startswith("# Field guide: momentum and trend (part 2)\n")
    assert second.endswith("momentum-and-trend-2.md")
    on_first = out[first].count("### `")
    assert "### `feature.f0`" in out[first] and f"### `feature.f{on_first}`" in out[second]
    assert on_first + out[second].count("### `") == 200  # no entry lost or repeated
    index = render(guide, SECTIONS)
    assert "(field-guide/chart/momentum-and-trend.md), [part 2](field-guide/chart/" in index


def test_a_theme_in_no_group_is_an_error() -> None:
    with pytest.raises(ConfigurationError, match=r"no theme group.*'fundamentals'"):
        pages(GUIDE, GuideSections(theme_groups=SECTIONS.theme_groups[:1]))
