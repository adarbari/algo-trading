"""Read-only queries over the stores for apps that show data (the API, ADR 0024).

What is left of it until read-model PR 10: the admin reads (runs, ingestion, review) and
the Builder's dry runs (``preview``); ``store`` opens the stores read-only and holds what
every query shares (the session a ``?date=`` resolves to, pages, not-found). Queries return
plain dataclasses of JSON-safe values; they never write (import-linter) and never fetch.
"""
