"""A market's feature values by catalogue name (ADR 0047, ADR 0038): the market-entity groups'
``market.<group>@v<N>.<column>`` fields (and expression features over them) of the market's
one row (``market_id("US")``) for exactly ``ctx.session``, each a ``FeatureValue`` with its
``FeatureInfo`` or an ``Unknown`` saying why it is missing (ADR 0036).

The read is ``services.read.instruments.features.load_feature_values`` with
``entity="market"``: the same UNKNOWN rules (``NO_PARTITION`` for a table with no partition
for the session, never an older one; ``NO_ROW``; ``NULL``), the same catalogue lookup."""

from collections.abc import Sequence

from algotrade.core.model.instruments import market_id
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.features import FeatureValue, load_feature_values

US = "US"


def load_market_feature_values(
    ctx: ReadContext, names: Sequence[str], market: str = US
) -> tuple[FeatureValue, ...]:
    """``names`` (market catalogue fields, in the order asked; repeats dropped) of ``market``
    for ``ctx.session``. ``UnknownFeatureError`` when a name is not a market feature."""
    mid = market_id(market)
    return load_feature_values(ctx, [mid], names, entity="market")[mid]
