"""Vendor sources (ADR 0027): what ingestion (batch) and, later, the API (live, read-only) read.

``framework`` is the non-vendor machinery, ``vendors`` has one folder per vendor and
``fixtures`` is the golden synthetic source. Only ``framework/registry.py`` builds sources.
"""
