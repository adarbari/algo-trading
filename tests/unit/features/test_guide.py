"""The field guide page (``docs/data/field-guide.md``): fields grouped by theme in first
appearance order, each with its reading, its criterion table, caveats and sources; the
situations after; stable bytes; an empty guide renders the header alone."""

from algotrade.config.site.field_guide import (
    FieldGuideEntry,
    FieldGuideSettings,
    GuideUse,
    Situation,
)
from algotrade.features.guide import HEADER, criterion_text, render

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


def test_fields_group_by_theme_in_first_appearance_order() -> None:
    page = render(FieldGuideSettings((RSI, CAP, MOVE), (DEAL,)))
    assert page.startswith(HEADER)
    assert (
        "3 fields: [Momentum and trend](#momentum-and-trend) · [Fundamentals](#fundamentals)."
        in page
    )
    momentum, fundamentals = page.index("## Momentum and trend"), page.index("## Fundamentals")
    assert momentum < page.index("### `rollup.a@v1.rsi`") < page.index("### `feature.atr_pct`")
    assert (
        page.index("### `feature.atr_pct`") < fundamentals < page.index("### `feature.market_cap`")
    )
    assert fundamentals < page.index("## Situations that fool several thresholds")
    assert (
        "### Pending takeover" in page
        and "**Affects.** `rollup.a@v1.rsi`, `feature.atr_pct`" in page
    )
    assert page == render(FieldGuideSettings((RSI, CAP, MOVE), (DEAL,)))


def test_an_entry_renders_its_reading_table_caveats_and_sources() -> None:
    page = render(FieldGuideSettings((RSI,)))
    assert "**How to read it.** 0 to 100" in page
    assert "| oversold | `lt 30` | soft | 5.0 | with a trend \\| filter |" in page
    assert "| liquid | `gte 50000000.0` | soft | 0.2 x the threshold, LIQUIDITY_RISK | - |" in page
    assert "| known | `not_null` | hard | - | - |" in page
    assert "| mid cap | `between [2000000000.0, 10000000000.0]` | hard | - | - |" in page
    assert "- pinned by a deal" in page and "Sources: Wilder (1978); Cardwell" in page
    assert criterion_text(GuideUse("x", "eq", "HIGH")) == 'eq "HIGH"'


def test_an_empty_guide_is_the_header() -> None:
    assert render(FieldGuideSettings()) == HEADER.rstrip() + "\n"
    page = render(FieldGuideSettings((CAP,)))
    assert "**The criterion per intent**" not in page and "Sources:" not in page
