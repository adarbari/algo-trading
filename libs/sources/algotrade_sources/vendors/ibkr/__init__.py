"""Interactive Brokers through a local IB Gateway: READ-ONLY market data for live verification
and enrichment (contract ids, IB's IV / HV history and snapshots; ADR 0026, 0028).

``gateway.py`` is the only module that imports ``ib_async`` and exposes market data only
(ADR 0026); ``market_data.py`` is the session source tasks receive as ``ctx.sources["ibkr"]``.
"""
