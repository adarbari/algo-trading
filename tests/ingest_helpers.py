"""Helpers for ingestion task tests: a ``TaskContext`` over a store with a fixed clock."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from algotrade.data import StoreReader
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.settings import SourcesSettings
from algotrade_ingestion.sources.base import Source
from algotrade_ingestion.tasks.framework import TaskContext

FIXED = datetime(2026, 10, 2, 22, tzinfo=UTC)


def task_ctx(
    writer: StoreWriter,
    reader: StoreReader | None = None,
    clock: Callable[[], datetime] = lambda: FIXED,
    sources: Mapping[str, Source] | None = None,
    settings: SourcesSettings | None = None,
) -> TaskContext:
    """A context over ``writer``'s backend (``reader`` defaults to the same store)."""
    reader = reader or StoreReader(writer._backend)
    return TaskContext(reader, writer, sources or {}, settings or SourcesSettings(), clock=clock)
