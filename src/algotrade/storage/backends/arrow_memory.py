"""Arrow's process-wide memory knobs: how many threads its decoders may spawn and handing
freed pool memory back to the OS. The one place outside the Parquet backends that touches
``pyarrow`` for memory, so the API process and the result cache never import it themselves."""

import pyarrow as pa


def limit_threads(cpu: int, io: int) -> None:
    """Cap Arrow's CPU and IO thread pools (each read thread otherwise decodes with one thread
    per core plus an IO pool, each holding arena memory)."""
    pa.set_cpu_count(cpu)
    pa.set_io_thread_count(io)


def release_unused() -> None:
    """Return the Arrow memory pool's unused (freed but retained) memory to the OS."""
    pa.default_memory_pool().release_unused()
