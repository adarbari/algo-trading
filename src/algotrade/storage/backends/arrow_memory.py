"""Arrow's process-wide memory knobs: how many threads its decoders may spawn and handing
freed pool memory back to the OS. The one place outside the Parquet backends that touches
``pyarrow`` for memory, so the API process and the result cache never import it themselves."""

import pyarrow as pa


def limit_threads(cpu: int, io: int) -> None:
    """Cap Arrow's CPU and IO thread pools (each read thread otherwise decodes with one thread
    per core plus an IO pool, each holding arena memory)."""
    pa.set_cpu_count(cpu)
    pa.set_io_thread_count(io)


def use_system_pool() -> None:
    """Make the OS allocator the default of Python-level Arrow calls, a fallback only: Arrow's own
    C++ code (Parquet decode) keeps allocating from its default pool, which only
    ``ARROW_DEFAULT_MEMORY_POOL=system`` set before ``pyarrow`` is imported switches (the API does
    it in ``algotrade_api/__init__.py``; a pool a user sets there applies to the C++ side only).
    The bundled mimalloc keeps freed pages: a read's peak
    stayed resident (811 MB of 811 MB on a sample) where the system pool hands them back (399 MB,
    183 after ``release_unused``; ``docs/perf/api-memory.md``)."""
    pa.set_memory_pool(pa.system_memory_pool())


def pool_backend() -> str:
    """The name of Arrow's default memory pool's allocator (``system``, ``mimalloc``)."""
    return str(pa.default_memory_pool().backend_name)


def release_unused() -> None:
    """Return the Arrow memory pool's unused (freed but retained) memory to the OS."""
    pa.default_memory_pool().release_unused()
