"""Every rollup the pipeline computes, by key (``<name>@v<N>``), in dependency order.

Add a rollup by declaring ``ROLLUP`` in ``features/rollups/<name>.py`` and listing it here;
the ``rollups`` ingestion task, the selection catalogue (``catalogue_columns``) and the
fitness tests pick it up from this registry. The order is computed
(``framework.graph.dependency_order``): a rollup that reads another rollup's table comes
after it, and an unknown dependency or a cycle fails at import.
"""

from collections.abc import Mapping

from algotrade.features.framework.declaration import Rollup
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

ROLLUPS: dict[str, Rollup] = {
    r.key: r
    for r in dependency_order(
        (
            option_liquidity.ROLLUP,
            price_stats.ROLLUP,
            earnings.ROLLUP,
            dividends.ROLLUP,
            iv30.ROLLUP,
            iv_history.ROLLUP,
            liquidity_class.ROLLUP,
            fundamentals.ROLLUP,
        )
    )
}


def catalogue_columns() -> dict[str, Mapping[str, str]]:
    """``{"price_stats@v1": {"hv30": "float", ...}}``: the selectable rollup fields."""
    return {key: r.columns for key, r in ROLLUPS.items()}
