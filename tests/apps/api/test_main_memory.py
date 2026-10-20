"""The API process's Arrow memory setting (docs/perf/api-memory.md)."""

import subprocess
import sys

CODE = (
    "import algotrade_api.main\n"
    "from algotrade.storage.backends.arrow_memory import pool_backend\n"
    "print(pool_backend())"
)


def test_the_api_process_serves_on_the_system_pool() -> None:
    """Freed Arrow memory must go back to the OS: the API's footprint reached 15-36 GB on the
    default mimalloc pool, which keeps every read's peak."""
    out = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == "system"
