"""Screeners: pure, point-in-time filters that rank instruments from a ``FeatureView``.

A screener returns one ``ScreenRow`` per instrument it was given, including the ones that
fail, so every run can be audited for coverage.
"""

from algotrade.strategies.screeners.base import Decision, Screener, ScreenRow
from algotrade.strategies.screeners.registry import SCREENERS, create_screener

__all__ = ["SCREENERS", "Decision", "ScreenRow", "Screener", "create_screener"]
