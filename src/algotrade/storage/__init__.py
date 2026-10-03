"""Storage: the data contract between apps (ADR 0006).

Storage is generic (ADR 0019 R2): partitions, backends, run records, schemas. Consumers read
market data through ``algotrade.data``; only ``apps/ingestion`` writes (import-linter).
Only ``storage/backends/`` knows how data is laid out.
"""

from algotrade.storage.factory import open_backend
from algotrade.storage.runs import RunRecord, RunStatus

__all__ = ["RunRecord", "RunStatus", "open_backend"]
