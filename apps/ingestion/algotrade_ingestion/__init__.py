"""The ingestion app: the only writer of market and feature data (ADR 0005).

Pulls from vendors, saves raw responses, normalises into storage, computes features and
runs the nightly screens. Vendor code and credentials never leave this package.
"""
