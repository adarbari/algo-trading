"""The bought history's chains as the option-structure engine reads them (ADR 0088, E5):
``HistoryChainLoader`` is E4's ``ChainLoader`` with its two reads, a session's labels, spots and
partition stamps and its option quotes, pointed at the option-history store. Everything the engine
does with a ``DayChain`` is the writer's own; only where the rows come from differs.

A name has an ``OK`` label on a session when the history holds option quotes for it there (the
history has no feed to go stale: an underlying with no quotes is ``NO_CHAIN``, a name that left the
chain is a missing chain, never a filled one) and its spot is the vendor's close, else the spot the
option rows carry (an index has no stock quote). Names with no ``underlying_id`` are not in a chain.
``knowledge_ts`` is each partition's own write instant (ADR 0084 decision 3).

Until the survivorship-free listing history reaches the single names (PR #968, F7), the chain holds
only the index underlyings (``IDX:``) and the listed ``symbols`` (the index ETFs a setup names): a
single name whose id the listings cannot give for a past session would otherwise drop out silently.
"""

from collections.abc import Collection
from datetime import date

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.instruments import is_index_id
from algotrade.data import StoreReader
from algotrade.data.option_history import reading
from algotrade.data.option_history.chain_frames import chain_underlying_quotes
from algotrade.features.rollups.positioning.chain_inputs import closing_spots
from algotrade_ingestion.tasks.derived.paths.option_outcomes import QUOTE_COLUMNS, ChainLoader

OK = "OK"
DAY_COLUMNS = ("underlying_id", "symbol", "underlying_price", "ts", "knowledge_ts")


class HistoryChainLoader(ChainLoader):
    """``ChainLoader`` over the option-history store (``reader`` is the history's), restricted to
    the index underlyings and ``symbols``."""

    def __init__(self, reader: StoreReader, sources: SourcesSettings, symbols: Collection[str]):
        super().__init__(reader, sources)
        self.symbols = frozenset(s.upper() for s in symbols)

    def _day(self, day: date) -> tuple[dict[str, str], dict[str, float], list[pd.Timestamp]]:
        if day in self._days:
            return self._days[day]
        quotes = reading.option_quote_rows(self.reader, day, None, DAY_COLUMNS)
        labels: dict[str, str] = {}
        spots: dict[str, float] = {}
        stamps: list[pd.Timestamp] = []
        if quotes is not None and not quotes.empty:
            is_index = quotes["underlying_id"].map(lambda i: isinstance(i, str) and is_index_id(i))
            named = quotes[
                quotes["underlying_id"].notna()
                & (is_index | quotes["symbol"].str.upper().isin(self.symbols))
            ]
            labels = dict.fromkeys(named["underlying_id"].astype(str).unique(), OK)
            stamps.append(pd.Timestamp(quotes["knowledge_ts"].max()))
            under = reading.underlying_quotes(self.reader, day)
            if under is not None and not under.empty:
                stamps.append(pd.Timestamp(under["knowledge_ts"].max()))
            frame = chain_underlying_quotes(under, named)
            spots = {str(i): float(v) for i, v in closing_spots(frame).items()}
        self._days[day] = labels, spots, stamps
        return self._days[day]

    def _quotes(self, day: date, ids: Collection[str] | None) -> pd.DataFrame | None:
        rows = reading.option_quote_rows(self.reader, day, ids, (*QUOTE_COLUMNS, "knowledge_ts"))
        if rows is None:
            return None
        labels = self._day(day)[0]
        return rows[rows["underlying_id"].isin(labels)].reset_index(drop=True)
