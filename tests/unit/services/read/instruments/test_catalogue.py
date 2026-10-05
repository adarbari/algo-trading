"""The caller's catalogue with the server-derived display format (ADR 0038 decision 4)."""

import pytest

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import (
    FeatureFormat,
    UnknownFeatureError,
    feature_infos,
    format_of,
    load_catalogue,
)


@pytest.mark.parametrize(
    ("dtype", "unit", "expected"),
    [
        ("date", "date", FeatureFormat.DATE),
        ("date", None, FeatureFormat.DATE),
        ("bool", "flag", FeatureFormat.FLAG),
        ("bool", None, FeatureFormat.FLAG),
        ("str", "category", FeatureFormat.CATEGORY),
        ("str", "text", FeatureFormat.TEXT),
        ("str", None, FeatureFormat.TEXT),
        ("float", "decimal", FeatureFormat.PERCENT),
        ("float32", "usd_per_share", FeatureFormat.CURRENCY),
        ("float", "usd", FeatureFormat.COMPACT),
        ("float", "shares", FeatureFormat.COMPACT),
        ("float", "pct_points", FeatureFormat.NUMBER),  # 25 is 25%: not a fraction
        ("int", "sessions", FeatureFormat.NUMBER),
        ("float", "ratio", FeatureFormat.NUMBER),
        ("int", None, FeatureFormat.NUMBER),
    ],
)
def test_format_from_unit_and_dtype(dtype: str, unit: str | None, expected: FeatureFormat) -> None:
    assert format_of(dtype, unit) is expected


def test_the_catalogue_in_order_with_metadata(ctx: ReadContext) -> None:
    infos = load_catalogue(ctx)
    names = [i.name for i in infos]
    assert names[0].startswith("instrument.")
    assert names.index("rollup.price_stats@v2.close") < names.index("feature.pct_from_high_52w")
    by_name = {i.name: i for i in infos}
    close = by_name["rollup.price_stats@v2.close"]
    assert (close.kind, close.source, close.group, close.unit) == (
        "window", "rollups/instrument/price_stats@v2", "price_stats@v2", "usd_per_share",
    )  # fmt: skip
    expression = by_name["feature.pct_from_high_52w"]
    assert (expression.source, expression.scope, expression.format) == (
        "expression", "site", FeatureFormat.PERCENT,
    )  # fmt: skip
    sector = by_name["instrument.sector"]
    assert (sector.kind, sector.source, sector.description) == (
        "instrument", "instruments/company", "company detail (SEC EDGAR)",
    )  # fmt: skip
    assert by_name["instrument.symbol"].description == "reference fact"


def test_an_unknown_or_moved_name_is_an_error_naming_it(ctx: ReadContext) -> None:
    with pytest.raises(UnknownFeatureError, match=r"unknown field 'instrument\.nope'"):
        feature_infos(ctx.features, ["instrument.nope"])
    with pytest.raises(UnknownFeatureError, match=r"superseded.*rollup\.price_stats@v2\.close"):
        feature_infos(ctx.features, ["rollup.price_stats@v1.close"])
