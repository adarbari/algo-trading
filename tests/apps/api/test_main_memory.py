"""The API process's Arrow memory setting (docs/perf/api-memory.md)."""

import os
import subprocess
import sys

# a developer's or CI's own pool choice must not decide the test
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "ARROW_DEFAULT_MEMORY_POOL"}
CODE = (
    "import algotrade_api.main\n"
    "from algotrade.storage.backends.arrow_memory import pool_backend\n"
    "print(pool_backend())"
)


def test_the_api_process_serves_on_the_system_pool() -> None:
    """Freed Arrow memory must go back to the OS: the API's footprint reached 15-36 GB on the
    default mimalloc pool, which keeps every read's peak."""
    out = subprocess.run(
        [sys.executable, "-c", CODE], capture_output=True, text=True, check=True, env=CLEAN_ENV
    )
    assert out.stdout.strip().splitlines()[-1] == "system"


CPP_CODE = (
    "import tempfile, pathlib\n"
    "import algotrade_api\n"
    "import pyarrow as pa, pyarrow.parquet as pq\n"
    "path = pathlib.Path(tempfile.mkdtemp()) / 'f.parquet'\n"
    "pq.write_table(pa.table({'x': list(range(500000)), 's': ['a' * 20] * 500000}), path)\n"
    "with pq.ParquetFile(path) as f: f.read()\n"
    "print(pa.mimalloc_memory_pool().max_memory())"
)


def test_arrow_cpp_decoding_does_not_allocate_from_mimalloc() -> None:
    """Parquet decode runs in Arrow's C++ default pool, which a runtime ``set_memory_pool`` does
    not change: only the variable set before pyarrow is imported keeps it off mimalloc."""
    out = subprocess.run(
        [sys.executable, "-c", CPP_CODE], capture_output=True, text=True, check=True, env=CLEAN_ENV
    )
    assert out.stdout.strip().splitlines()[-1] == "0"
