"""Every feature group the pipeline computes, by key (``<name>@v<N>``) in dependency order,
and every feature they declare.

Add a group by declaring ``GROUP`` (with its ``FEATURES``) in
``features/rollups/<name>.py`` and listing it here; the ``rollups`` ingestion task, the
selection catalogue (``catalogue_columns``), the feature catalogue (``features.catalogue``)
and the fitness tests pick it up from this registry. The order is computed
(``framework.graph.dependency_order``): a group that reads another group's table comes
after it, and an unknown dependency or a cycle fails at import.

Lookups for readers of metadata (UI, email, reports): ``feature(name)`` by feature key
(``price_stats.hv30@v1``) or selection field (``rollup.price_stats@v1.hv30``).
"""

from collections.abc import Mapping

from algotrade.features.framework.declaration import FeatureGroup
from algotrade.features.framework.feature import Feature
from algotrade.features.framework.graph import dependency_order
from algotrade.features.rollups import (
    dividends,
    earnings,
    fundamentals,
    iv30,
    iv_history,
    liquidity_class,
    option_liquidity,
    price_stats,
)

GROUPS: dict[str, FeatureGroup] = {
    g.key: g
    for g in dependency_order(
        (
            option_liquidity.GROUP,
            price_stats.GROUP,
            earnings.GROUP,
            dividends.GROUP,
            iv30.GROUP,
            iv_history.GROUP,
            liquidity_class.GROUP,
            fundamentals.GROUP,
        )
    )
}
# Every feature by key (``<group>.<column>@v<N>``), in group (dependency) then column order.
FEATURES: dict[str, Feature] = {f.key: f for g in GROUPS.values() for f in g.features}
_BY_FIELD: dict[str, Feature] = {f.field: f for f in FEATURES.values()}


def feature(name: str) -> Feature | None:
    """The feature named by its key (``price_stats.hv30@v1``) or its selection field
    (``rollup.price_stats@v1.hv30``); ``None`` when there is none (e.g. ``instrument.*``)."""
    return FEATURES.get(name) or _BY_FIELD.get(name)


def catalogue_columns() -> dict[str, Mapping[str, str]]:
    """``{"price_stats@v1": {"hv30": "float", ...}}``: the selectable group fields."""
    return {key: g.columns for key, g in GROUPS.items()}
