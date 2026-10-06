"""A run's market-wide feature values on its bar timeline (ADR 0049).

``MarketFeatures`` holds one column per market feature name (``market.<group>@v<N>.<column>``,
ADR 0047), each aligned to the bars' timestamps: the value at index ``t`` is session ``t``'s
stored value (``None`` when that session has none: unknown, never an older session's value).
``at(t)`` is what the engine hands overlays at the close of bar ``t``, so session t's features
feed orders that fill at the open of ``t + 1``; ``MarketView.market_feature`` slices it at the
view's cursor. Built by the services layer (``services.backtests.market``) from the market
feature store.
"""

from collections.abc import Mapping, Sequence
from types import MappingProxyType

import numpy as np

from algotrade.core.model.errors import MissingDataError
from algotrade.core.views.feature_view import FeatureValue
from algotrade.core.views.series import TimeArray

MARKET_FEATURES = "market features"  # the dataset a missing name is reported against
HINT = "load it for the run ([regime] label, services.backtests.market)"


class MarketFeatures:
    __slots__ = ("_columns", "_timestamps")

    def __init__(
        self, timestamps: TimeArray, columns: Mapping[str, Sequence[FeatureValue]]
    ) -> None:
        n = len(timestamps)
        wrong = sorted(name for name, values in columns.items() if len(values) != n)
        if wrong:
            raise ValueError(f"market feature columns {wrong} are not aligned to {n} bars")
        self._timestamps = timestamps
        self._columns = {name: np.array(values, dtype=object) for name, values in columns.items()}

    def __len__(self) -> int:
        return len(self._timestamps)

    def __contains__(self, name: object) -> bool:
        return name in self._columns

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._columns))

    @property
    def timestamps(self) -> TimeArray:
        return self._timestamps

    def value(self, name: str, cursor: int) -> FeatureValue:
        """``name``'s value for session ``cursor``; ``MissingDataError`` when the run did not
        load ``name`` (ADR 0008), ``None`` when the session has no value (unknown)."""
        if name not in self._columns:
            raise MissingDataError(MARKET_FEATURES, f"{name} is not loaded for this run", HINT)
        if not 0 <= cursor < len(self):
            raise IndexError(f"cursor {cursor} out of range for {len(self)} bars")
        found: FeatureValue = self._columns[name][cursor]
        return found

    def at(self, cursor: int) -> Mapping[str, FeatureValue]:
        """Every loaded name's value for session ``cursor`` (read-only)."""
        return MappingProxyType({name: self.value(name, cursor) for name in self._columns})
