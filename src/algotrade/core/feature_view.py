"""Read-only, point-in-time view of features for screeners and strategies.

Like ``MarketView`` for prices, this is the only window a screener has onto data. It is
built by the services layer from stores read with ``as_of``, so a screener cannot see
anything that was not known at that time.
"""

from collections.abc import Iterator, Mapping
from datetime import date
from types import MappingProxyType

type FeatureValue = float | int | str | bool | None


class FeatureView:
    __slots__ = ("_as_of", "_rows")

    def __init__(self, as_of: date, rows: Mapping[str, Mapping[str, FeatureValue]]) -> None:
        self._as_of = as_of
        self._rows = MappingProxyType({k: MappingProxyType(dict(v)) for k, v in rows.items()})

    @property
    def as_of(self) -> date:
        return self._as_of

    @property
    def instruments(self) -> tuple[str, ...]:
        return tuple(sorted(self._rows))

    def __contains__(self, instrument: object) -> bool:
        return instrument in self._rows

    def __iter__(self) -> Iterator[str]:
        return iter(self.instruments)

    def row(self, instrument: str) -> Mapping[str, FeatureValue]:
        return self._rows[instrument]

    def get(self, instrument: str, feature: str) -> FeatureValue:
        row = self._rows.get(instrument)
        return None if row is None else row.get(feature)
