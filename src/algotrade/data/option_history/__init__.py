"""The bought option history's reader (ADR 0084): one store root (``ALGOTRADE_OPTION_HISTORY_URL``,
a sentinel-marked directory on the external drive) and the reads of its tables. Importable only by
the ingestion app (the import, its verification checks and, later, the derivation of a main-store
outcome table): never by evaluation, a feature, a screener or the API."""
