"""Yahoo Finance (unofficial): analyst price targets, consensus estimates and recommendation
counts for the names FMP's free plan refuses (ADR 0080).

Fetch + normalise for the ``quoteSummary`` endpoint, read through the ``yfinance`` package's
cookie / crumb session (``client.py``, imported lazily). Yahoo publishes no API terms for this
and its terms forbid scraping, so everything stored from here carries the owner-only licence
``yahoo``; no key is held.
"""
