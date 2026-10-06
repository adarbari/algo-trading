"""The field guide pages: the index (header, the themes with their fields, the situations)
and one page per theme in first appearance order, each field with its reading, its criterion
table, caveats and sources; stable bytes; an empty guide renders the header alone."""

from algotrade.config.site.field_guide import (
    FieldGuideEntry,
    FieldGuideSettings,
    GuideUse,
    Situation,
)
from algotrade.features.guide import HEADER, criterion_text, pages, render, theme_path

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


def test_the_index_lists_themes_in_first_appearance_order_and_the_situations() -> None:
    index = render(GUIDE)
    assert index.startswith(HEADER)
    assert "## Themes (3 fields)" in index
    momentum = index.index(
        "- [Momentum and trend](field-guide/momentum-and-trend.md) (2): "
        "`rollup.a@v1.rsi`, `feature.atr_pct`"
    )
    assert momentum < index.index(
        "- [Fundamentals](field-guide/fundamentals.md) (1): `feature.market_cap`"
    )
    assert index.index("## Situations that fool several thresholds") > momentum
    assert "### Pending takeover" in index
    assert "**Affects.** `rollup.a@v1.rsi`, `feature.atr_pct`" in index
    assert "### `rollup.a@v1.rsi`" not in index  # the fields are on the theme pages
    assert index == render(GUIDE)


def test_one_page_per_theme_with_the_fields_in_file_order() -> None:
    out = pages(GUIDE)
    assert list(out) == [
        "docs/data/field-guide.md",
        "docs/data/field-guide/momentum-and-trend.md",
        "docs/data/field-guide/fundamentals.md",
    ]
    page = out[theme_path("momentum and trend")]
    assert page.startswith("# Field guide: momentum and trend\n")
    assert "[field-guide.md](../field-guide.md)" in page
    assert page.index("### `rollup.a@v1.rsi`") < page.index("### `feature.atr_pct`")
    assert "### `feature.market_cap`" in out["docs/data/field-guide/fundamentals.md"]


def test_an_entry_renders_its_reading_table_caveats_and_sources() -> None:
    page = pages(FieldGuideSettings((RSI,)))[theme_path("momentum and trend")]
    assert "**How to read it.** 0 to 100" in page
    assert "| oversold | `lt 30` | soft | 5.0 | with a trend \\| filter |" in page
    assert "| liquid | `gte 50000000.0` | soft | 0.2 x the threshold, LIQUIDITY_RISK | - |" in page
    assert "| known | `not_null` | hard | - | - |" in page
    assert "| mid cap | `between [2000000000.0, 10000000000.0]` | hard | - | - |" in page
    assert "- pinned by a deal" in page and "Sources: Wilder (1978); Cardwell" in page
    assert criterion_text(GuideUse("x", "eq", "HIGH")) == 'eq "HIGH"'


def test_an_empty_guide_is_the_header() -> None:
    assert render(FieldGuideSettings()) == HEADER.rstrip() + "\n"
    assert list(pages(FieldGuideSettings())) == ["docs/data/field-guide.md"]
    page = pages(FieldGuideSettings((CAP,)))[theme_path("fundamentals")]
    assert "**The criterion per intent**" not in page and "Sources:" not in page
