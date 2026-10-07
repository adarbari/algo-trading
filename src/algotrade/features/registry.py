"""Every feature group the code computes, by key (``<name>@v<N>``) in dependency order, every
feature they declare, and the group versions they superseded.

Add a group by declaring ``GROUP`` (with its ``FEATURES``) in
``features/rollups/<kind>/<name>.py`` and listing it here; the ``rollups`` ingestion task, the
selection catalogue, the feature catalogue (``features.catalogue``) and the fitness tests pick
it up from this registry. The order is computed (``framework.graph.dependency_order``): a
group that reads another group's table comes after it. A group may read a materialised
expression feature (``iv30@v1`` reads ``div_yield@v1``); the full order, with those groups and
the site's expression features, is ``features.site.site_features`` (``FeatureSet``).

``SUPERSEDED``: group versions replaced by ADR 0023 step 3 (32-bit floats, columns computed
from other columns moved to expression features). Their tables stay readable until
``algotrade-ingest retire-features`` deletes them; their selection fields fail with the field
that replaced them (``FeatureSet.moved_field``).

Lookups for readers of metadata (UI, email, reports): ``feature(name)`` by feature key
(``price_stats.hv30@v2``) or selection field (``rollup.price_stats@v2.hv30``); expression
features: ``FeatureSet.feature``.
"""

from collections.abc import Mapping

from algotrade.features.framework.declaration import FeatureGroup, Superseded
from algotrade.features.framework.feature import Feature
from algotrade.features.framework.graph import dependency_order
from algotrade.features.rollups.activity import vol_stats, volume_profile
from algotrade.features.rollups.corporate import (
    dividends,
    earnings,
    earnings_schedule,
    financials,
    fundamentals,
)
from algotrade.features.rollups.levels import gaps, pivot_strength, retest, swing_levels
from algotrade.features.rollups.market import (
    breadth,
    cross_asset,
    indicators,
    macro,
    regime,
    trend,
)
from algotrade.features.rollups.options import (
    ibkr_iv,
    iv30,
    iv_history,
    nearest_expiry,
    oi_walls,
    option_liquidity,
    put_wing,
)
from algotrade.features.rollups.price import (
    anchored_vwap,
    bands,
    episodes,
    momentum,
    price_history,
    price_moves,
    price_stats,
    trend_stats,
    volume,
)
from algotrade.features.rollups.reference import fund_reference

GROUPS: dict[str, FeatureGroup] = {
    g.key: g
    for g in dependency_order(
        (
            option_liquidity.GROUP,
            price_stats.GROUP,
            price_history.GROUP,
            earnings.GROUP,
            earnings_schedule.GROUP,
            dividends.GROUP,
            iv30.GROUP,
            iv_history.GROUP,
            ibkr_iv.GROUP,
            fundamentals.GROUP,
            financials.GROUP,
            put_wing.GROUP,
            price_moves.GROUP,
            momentum.GROUP,
            volume.GROUP,
            bands.GROUP,
            trend_stats.GROUP,
            vol_stats.GROUP,
            volume_profile.GROUP,
            swing_levels.GROUP,
            pivot_strength.GROUP,
            retest.GROUP,
            gaps.GROUP,
            anchored_vwap.GROUP,
            episodes.GROUP,
            oi_walls.GROUP,
            nearest_expiry.GROUP,
            trend.GROUP,
            breadth.GROUP,
            cross_asset.GROUP,
            macro.GROUP,
            indicators.GROUP,
            regime.GROUP,
            fund_reference.GROUP,
        ),
        # iv30@v1 and put_wing@v1 read the materialised div_yield@v1 (FeatureSet orders it)
        stored_ok=True,
    )
}
# Every feature by key (``<group>.<column>@v<N>``), in group (dependency) then column order.
FEATURES: dict[str, Feature] = {f.key: f for g in GROUPS.values() for f in g.features}
_BY_FIELD: dict[str, Feature] = {f.field: f for f in FEATURES.values()}

SUPERSEDED: dict[str, Superseded] = {
    "price_stats@v1": Superseded("price_stats@v2"),
    "dividends@v1": Superseded("dividends@v2"),
    "fundamentals@v1": Superseded("fundamentals@v2"),
    "iv_history@v1": Superseded("iv_history@v2"),
    "anchored_vwap@v1": Superseded("anchored_vwap@v2"),
    # v2 adds sma_150 and the regression trend quality (one nightly of v1 rows at most)
    "bands@v1": Superseded("bands@v2"),
    "trend_stats@v1": Superseded("trend_stats@v2"),
    # Its rows were price_stats rows; the class and option tier are expression features now.
    "liquidity_class@v1": Superseded(
        "price_stats@v2", {"chain_oi": "feature.option_chain_oi", "rule_hash": ""}
    ),
}


def feature(name: str) -> Feature | None:
    """The feature named by its key (``price_stats.hv30@v2``) or its selection field
    (``rollup.price_stats@v2.hv30``); ``None`` when there is none (e.g. ``instrument.*``)."""
    return FEATURES.get(name) or _BY_FIELD.get(name)


def catalogue_columns() -> dict[str, Mapping[str, str]]:
    """``{"price_stats@v2": {"hv30": "float32", ...}}``: the instrument groups' selectable
    fields (a market-entity group is read as ``market.<group>@v<N>.<column>``, never selected
    per instrument: ADR 0047)."""
    return {key: g.columns for key, g in GROUPS.items() if g.entity == "instrument"}
