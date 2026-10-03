"""The ingestion app: the only writer of market and feature data (ADR 0005).

Pulls from vendors (through the ``algotrade_sources`` registry, ADR 0027), saves raw
responses, normalises into storage, computes features and runs the nightly screens.
"""
