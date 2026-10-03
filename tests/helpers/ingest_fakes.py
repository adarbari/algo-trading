"""Helpers for ingestion tests: a ``TaskContext`` over a store with a fixed clock, and an
``Http`` client around a fake transport (no network, no real sleeps, no shared limiter)."""

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.sources.framework import registry
from algotrade_ingestion.sources.framework.base import Source
from algotrade_ingestion.sources.framework.http import Http, Pacer, RetryPolicy, Transport
from algotrade_ingestion.tasks.framework.run import TaskContext

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


def http_for(
    transport: Transport, policy: RetryPolicy | None = None, limiter: Pacer | None = None
) -> Http:
    """What the registry would hand a source, around a fake transport."""
    return Http(transport, policy or RetryPolicy(), limiter, sleep=lambda s: None)


class CountingLimiter:
    """A ``Pacer`` that only counts: proves sources wait on the limiter they were given."""

    def __init__(self) -> None:
        self.waits, self.held = 0, 0.0

    def wait(self) -> float:
        self.waits += 1
        return 0.0

    def hold(self, seconds: float) -> None:
        self.held += seconds


def use_source(monkeypatch: pytest.MonkeyPatch, name: str, source: Source) -> None:
    """Make the source registry hand out ``source`` as ``name`` (its availability rules —
    section enabled, credential set — still apply)."""
    spec = registry.SOURCES[name]
    monkeypatch.setitem(registry.SOURCES, name, replace(spec, build=lambda http: source))
