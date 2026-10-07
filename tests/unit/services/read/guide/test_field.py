"""``load_guide_field``: the field's info with its guide entry, the related fields (first
mention first across reads, caveats and use notes, then the formula's inputs; catalogue names
only, never itself), the playbooks that name it in a criterion, a column or the rank, and the
situations that fool it; a name outside the catalogue is an error."""

import pytest

from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.field import GuidePlaybookUse, load_guide_field
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from tests.unit.services.read.guide.conftest import ADV, CLOSE, PULLBACK, REL_VOLUME

LIQUIDITY_RULE = "gte 50000000 soft tolerance relative 0.2 on_miss LIQUIDITY_RISK"


def test_related_fields_in_first_mention_order(ctx: StoreContext) -> None:
    page = load_guide_field(ctx, ADV)
    assert page.info.name == ADV and page.info.guide is not None
    assert page.info.guide.theme == "liquidity"
    # reads (rel_volume, atr_pct; itself and an unknown name dropped), caveats (atr_pct again,
    # instrument.symbol), use notes (close); a stored rollup's inputs are tables, not fields.
    assert page.related == (REL_VOLUME, "feature.atr_pct", "instrument.symbol", CLOSE)


def test_an_expressions_inputs_follow_its_mentions(ctx: StoreContext) -> None:
    page = load_guide_field(ctx, PULLBACK)
    assert page.related == (CLOSE, "rollup.momentum@v1.atr_14", "rollup.momentum@v1.high_20d")


def test_a_field_without_a_guide_entry_relates_only_its_inputs(ctx: StoreContext) -> None:
    page = load_guide_field(ctx, "feature.atr_pct")
    assert page.info.guide is None and page.situations == ()
    assert all(name != "feature.atr_pct" for name in page.related) and page.related


def test_playbooks_that_use_the_field(ctx: StoreContext) -> None:
    assert load_guide_field(ctx, ADV).playbooks == (
        GuidePlaybookUse("alpha", "Alpha", "trend", (LIQUIDITY_RULE,), column=True, rank=False),
        GuidePlaybookUse("zeta", "Zeta", None, (), column=True, rank=False),
    )  # fmt: skip
    (alpha,) = load_guide_field(ctx, PULLBACK).playbooks
    assert (alpha.rules, alpha.column, alpha.rank) == (
        ("between [-0.5, 0.5] soft tolerance 0.25",), False, True,
    )  # fmt: skip
    assert load_guide_field(ctx, "rollup.momentum@v1.rsi_14").playbooks == ()
    assert load_guide_field(ctx, REL_VOLUME).playbooks == (
        GuidePlaybookUse("zeta", "Zeta", None, (), column=False, rank=False, flag=True),
    )  # a field read only by a flag


def test_situations_that_fool_the_field(ctx: StoreContext) -> None:
    (thin,) = load_guide_field(ctx, CLOSE).situations
    assert (thin.name, thin.signs, thin.do, thin.affects) == ("thin name", "Few trades.", "Gate.",
                                                              (ADV, CLOSE))  # fmt: skip
    assert [s.name for s in load_guide_field(ctx, REL_VOLUME).situations] == ["takeover"]


def test_a_name_outside_the_catalogue_is_an_error(ctx: StoreContext) -> None:
    with pytest.raises(UnknownFeatureError):
        load_guide_field(ctx, "rollup.nope@v1.x")
