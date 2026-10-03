"""One folder per data vendor (ADR 0012).

Each vendor folder contributes at least one source to ``sources/framework/registry.py``, and
only that registry imports it (ADR 0019 R3). Vendors never import each other.
"""
