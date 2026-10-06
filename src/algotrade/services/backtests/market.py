"""Use case step: a backtest's market features on its bar timeline (ADR 0049).

``load_market_features`` reads the market feature fields a run needs (``[regime] label``) for
every session of the bars' timeline from the market-entity feature groups (``MKT:US``'s row,
ADR 0047) through ``data.rollups.group_rows``, read ``as_of`` the launch (ADR 0007), and puts
them on that timeline as ``MarketFeatures``: index ``t`` holds session ``t``'s stored value. A
stored null is ``None`` (unknown: the overlay fails closed); a session with no stored row is a
``MissingDataError`` naming the sessions (ADR 0008), never an earlier session's value.
"""

from collections.abc import Sequence
from datetime import date, datetime

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.fields import field_source
from algotrade.core.model.instruments import market_id
from algotrade.core.views.feature_view import FeatureValue
from algotrade.core.views.market_features import MarketFeatures
from algotrade.core.views.series import TimeArray
from algotrade.data import StoreReader
from algotrade.data.rollups import group_rows
from algotrade.services.views import to_value

MARKET = market_id("US")  # the market whose row a run reads (ADR 0047)
HINT = "algotrade-ingest run market-rollups --from <start> --to <end>"
SHOWN = 5  # sessions named in a missing-rows error


def _column(
    reader: StoreReader, name: str, days: list[date], as_of: datetime | None
) -> list[FeatureValue]:
    """``name``'s stored value for each of ``days``; every day must have a stored row."""
    frame, missing = group_rows(reader, days[0], days[-1], [name], [MARKET], as_of)
    table = field_source(name)[0]
    if missing:
        raise MissingDataError(table, f"no {MARKET} rows for {days[0]}..{days[-1]}", HINT)
    stored = dict(zip(frame["session_date"], frame[name], strict=True))
    absent = [d for d in days if d not in stored]
    if absent:
        shown = ", ".join(str(d) for d in absent[:SHOWN])
        more = f" and {len(absent) - SHOWN} more" if len(absent) > SHOWN else ""
        raise MissingDataError(
            table, f"no {MARKET} row for {len(absent)} session(s): {shown}{more}", HINT
        )
    return [to_value(stored[d]) for d in days]


def load_market_features(
    reader: StoreReader,
    names: Sequence[str],
    timestamps: TimeArray,
    as_of: datetime | None = None,
) -> MarketFeatures:
    """``names`` for every session of ``timestamps`` (daily bars: a bar's date is its session)."""
    days = [d.item() for d in timestamps.astype("datetime64[D]")]
    if not days:
        return MarketFeatures(timestamps, {name: [] for name in names})
    return MarketFeatures(
        timestamps, {n: _column(reader, n, days, as_of) for n in sorted(set(names))}
    )
