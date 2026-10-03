"""Storage: the data contract between apps (ADR 0006).

Callers use ``open_reader`` (everyone) or ``open_writer`` (``apps/ingestion`` only,
enforced by import-linter). Only ``storage/backends/`` knows how data is laid out.
"""

from algotrade.storage.factory import open_backend
from algotrade.storage.readers import StoreReader
from algotrade.storage.runs import RunRecord, RunStatus

__all__ = ["RunRecord", "RunStatus", "StoreReader", "open_backend"]
