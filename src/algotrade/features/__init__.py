"""Feature definitions: pure computations from stored data to versioned features (ADR 0007).

Definitions never read or write storage. The ingestion pipeline feeds them data and
stores their output under ``features/<name>@<version>``.
"""

from algotrade.features.registry import FEATURES, FeatureSpec

__all__ = ["FEATURES", "FeatureSpec"]
