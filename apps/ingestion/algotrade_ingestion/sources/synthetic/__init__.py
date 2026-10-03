"""Synthetic data source: deterministic market regimes for the golden test datasets.

``generators`` builds price paths, ``catalog`` defines the golden datasets, and ``files``
reads and writes the committed CSV files (the reviewable source of truth). The ``golden``
ingestion job loads them into a fixture store through the normal storage writers.
"""
