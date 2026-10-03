"""Read-only queries over the stores for apps that show data (the API, ADR 0024).

One module per area (runs, universe, instruments, chains, features, screens, backtests,
configs); ``store`` opens the stores read-only and holds what every query shares (the
session a ``?date=`` resolves to, pages, not-found). Queries return plain dataclasses of
JSON-safe values; they never write (import-linter) and never fetch.
"""
