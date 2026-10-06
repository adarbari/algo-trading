"""Use case step: a backtest's market features on its bar timeline (ADR 0049).

``load_market_features`` reads the market feature fields a run needs (``[regime] label``) for
every session of the bars' timeline from the market-entity feature groups (``MKT:US``'s row,
ADR 0047) through ``data.rollups.feature_rows``, read ``as_of`` the launch (ADR 0007), and puts
them on that timeline as ``MarketFeatures``: index ``t`` holds session ``t``'s stored value, a
session with no row holds ``None`` (unknown: the overlay fails closed), never an earlier
session's value. A table with no rows in the whole range is a ``MissingDataError`` (ADR 0008).
"""

from collections.abc import Sequence
from datetime import datetime

from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.model.fields import field_source, group_of_table
from algotrade.core.model.instruments import market_id
from algotrade.core.views.feature_view import FeatureValue
from algotrade.core.views.market_features import MarketFeatures
from algotrade.core.views.series import TimeArray
from algotrade.data import StoreReader
from algotrade.data.rollups import feature_rows
from algotrade.services.views import to_value

MARKET = market_id("US")  # the market whose row a run reads (ADR 0047)
HINT = "algotrade-ingest run market-rollups --from <start> --to <end>"


def _tables(names: Sequence[str]) -> dict[str, list[tuple[str, str]]]:
    """``{table: [(name, column)]}`` of market feature fields; anything else fails."""
    out: dict[str, list[tuple[str, str]]] = {}
    for name in sorted(set(names)):
        table, column = field_source(name)
        group = group_of_table(table)
        if group is None or group[0] != "market":
            raise ConfigurationError(f"{name}: not a market feature field")
        out.setdefault(table, []).append((name, column))
    return out


def load_market_features(
    reader: StoreReader,
    names: Sequence[str],
    timestamps: TimeArray,
    as_of: datetime | None = None,
) -> MarketFeatures:
    """``names`` for every session of ``timestamps`` (daily bars: a bar's date is its session)."""
    days = [d.item() for d in timestamps.astype("datetime64[D]")]
    columns: dict[str, list[FeatureValue]] = {}
    if not days:
        return MarketFeatures(timestamps, {name: [] for name in names})
    start, end = days[0], days[-1]
    for table, wanted in _tables(names).items():
        frame = feature_rows(reader, table, [c for _, c in wanted], start, end, as_of, [MARKET])
        if frame is None:
            raise MissingDataError(table, f"no {MARKET} rows for {start}..{end}", HINT)
        for name, column in wanted:
            stored = dict(zip(frame["session_date"], frame[column], strict=True))
            columns[name] = [to_value(stored.get(day)) for day in days]
    return MarketFeatures(timestamps, columns)
