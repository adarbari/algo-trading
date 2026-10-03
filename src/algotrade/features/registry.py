"""Every rollup the pipeline computes, by key (``<name>@v<N>``), in computation order.

Add a rollup by declaring ``ROLLUP`` in ``features/rollups/<name>.py`` and listing it here;
the ``rollups`` ingestion task, the selection catalogue (``catalogue_columns``) and the
fitness tests pick it up from this registry.
"""

from collections.abc import Mapping

from algotrade.features.framework.declaration import Rollup
from algotrade.features.rollups import earnings, option_liquidity, price_stats

ROLLUPS: dict[str, Rollup] = {
    r.key: r for r in (option_liquidity.ROLLUP, price_stats.ROLLUP, earnings.ROLLUP)
}


def catalogue_columns() -> dict[str, Mapping[str, str]]:
    """``{"price_stats@v1": {"hv30": "float", ...}}``: the selectable rollup fields."""
    return {key: r.columns for key, r in ROLLUPS.items()}
