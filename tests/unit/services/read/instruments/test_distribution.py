"""A feature across instruments for exactly the session: instruments with no row are not
counted, stored nulls are, and a table with no partition for the session makes the whole
distribution UNKNOWN (never the older partition's values)."""

from dataclasses import replace

import pytest

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from algotrade.services.read.instruments.distribution import load_distribution
from algotrade.services.read.values import UnknownCode
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.read.instruments.conftest import D1

CLOSE = "rollup.price_stats@v2.close"
HV20 = "rollup.price_stats@v2.hv20"
NEXT = "rollup.earnings@v1.next_earnings_date"


def test_a_number_on_the_session_only(ctx: ReadContext) -> None:
    found = load_distribution(ctx, CLOSE)
    assert (found.session, found.count, found.nulls, found.unknown) == (D1, 1, 0, None)
    assert {q.q: q.value for q in found.quantiles}[0.5] == 51.0  # D1's close, not D0's
    assert sum(b.count for b in found.histogram) == 1 and found.categories == ()
    assert found.info.dtype.startswith("float")


def test_a_stored_null_is_counted_as_a_null(ctx: ReadContext) -> None:
    found = load_distribution(ctx, HV20)
    assert (found.count, found.nulls, found.quantiles, found.histogram) == (1, 1, (), ())


def test_other_features_count_their_values(ctx: ReadContext) -> None:
    found = load_distribution(ctx, "instrument.security_type")
    assert {c.value: c.count for c in found.categories} == {"COMMON_STOCK": 2, "ETF": 1}
    assert found.quantiles == ()


def test_no_partition_for_the_session_is_unknown(ctx: ReadContext) -> None:
    found = load_distribution(ctx, NEXT)  # earnings@v1 is stored for D0 only
    assert found.unknown is not None and found.unknown.code is UnknownCode.NO_PARTITION
    assert "earnings@v1" in found.unknown.detail
    assert (found.count, found.categories, found.histogram) == (0, (), ())


def test_a_name_outside_the_catalogue_is_an_error(ctx: ReadContext) -> None:
    with pytest.raises(UnknownFeatureError):
        load_distribution(ctx, "rollup.nope@v1.x")


def _guided(ctx: ReadContext, *uses: dict[str, object]) -> ReadContext:
    entry = {"name": CLOSE, "theme": "Price levels", "reads": "The close.", "use": list(uses)}
    docs = {("site", "field_guide", "price"): {"field": [entry]}}
    return replace(ctx, configs=MemoryConfigStore(docs))


def test_each_guide_use_counts_the_names_passing_it(ctx: ReadContext) -> None:
    uses = (
        {"for": "above fifty", "op": "gte", "value": 50.0},
        {"for": "a penny stock", "op": "lt", "value": 5.0},
        {
            "for": "mid priced",
            "op": "between",
            "value": [40.0, 60.0],
            "mode": "soft",
            "tolerance": 5.0,
        },
    )
    found = load_distribution(_guided(ctx, *uses), CLOSE)
    assert [(p.intent, p.count) for p in found.passing] == [
        ("above fifty", 1),
        ("a penny stock", 0),
        ("mid priced", 1),
    ]
    assert all(len(p.bins) == len(found.histogram) for p in found.passing)
    assert [sum(p.bins) for p in found.passing] == [1, 0, 1]  # the bins add up to the count


def test_an_unguided_field_has_nothing_passing(ctx: ReadContext) -> None:
    assert load_distribution(ctx, CLOSE).passing == ()
    assert load_distribution(_guided(ctx), CLOSE).passing == ()


def test_a_category_use_counts_without_bins(ctx: ReadContext) -> None:
    entry = {"name": "instrument.security_type", "theme": "Instrument gates", "reads": "Kind.",
             "use": [{"for": "an ETF", "op": "eq", "value": "ETF"}]}  # fmt: skip
    docs = {("site", "field_guide", "gates"): {"field": [entry]}}
    found = load_distribution(
        replace(ctx, configs=MemoryConfigStore(docs)), "instrument.security_type"
    )
    assert [(p.intent, p.count, p.bins) for p in found.passing] == [("an ETF", 1, ())]
