"""Feature groups (today's rollups), one folder per kind of input: ``price`` (daily bars),
``options`` (option chains and implied volatility) and ``corporate`` (earnings, dividends,
filings). Each group is one module: its ``FEATURES`` (one documented ``Feature`` per stored
column), a pure ``compute`` and its ``GROUP`` declaration (core, quant, numpy and pandas only;
no storage, data, config or services)."""
