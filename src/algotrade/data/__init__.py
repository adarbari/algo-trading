"""The domain read API: the only way services, engines and apps read market data (ADR 0019 R1).

Every function takes the generic ``StoreReader`` (partitions, ranges, run records) and adds
the domain rules on top:

- ``reference``  one snapshot rule (``snapshot``), instruments and contract terms,
                 ``InstrumentView``, the universe and the ``SymbolResolver``
- ``prices``     bars plus split / dividend adjustment
- ``events``     event tables read by EVENT date (not by the partition they were stored in)
- ``chains``     option quotes, underlying quotes and chain status
- ``rates``      the Treasury curve a date sees (risk-free rates for option pricing)
- ``rollups``    stored rollup rows over a range of sessions (a rollup reading another)
- ``shares``     share counts from SEC company facts, point in time by filing date
- ``macro``      macro series and index levels (``macro/series``), point in time by vintage
                 (ADR 0048): ``macro.series``, and the ``pit = "lag"`` rule (``macro.vintages``)
- ``volatility`` IBKR's implied and historical vol per underlying and session (ADR 0028;
                 the IBKR contracts snapshot is a ``reference`` read)
- ``feature_inputs``  what a feature group reads, by table name (``load_input``): each
                 table's point-in-time read for features, from the owners above

``StoreReader`` is re-exported here because consumers hold one and hand it to these
functions; they never import ``algotrade.storage.tables.readers`` (import-linter contract R1).
"""

from algotrade.storage.tables.readers import StoreReader

__all__ = ["StoreReader"]
