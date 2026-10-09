"""The API process caps Arrow's decode thread pools (memory bound under concurrent reads)."""

import pyarrow as pa
from fastapi.testclient import TestClient

from algotrade_api.main import ARROW_CPU_THREADS, ARROW_IO_THREADS


def test_creating_the_app_bounds_arrow_threads(client: TestClient) -> None:
    assert (ARROW_CPU_THREADS, ARROW_IO_THREADS) == (2, 4)
    assert pa.cpu_count() == ARROW_CPU_THREADS
    assert pa.io_thread_count() == ARROW_IO_THREADS
