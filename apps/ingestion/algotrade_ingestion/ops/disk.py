"""Refuse to start the nightly when the data volume is nearly full.

A full disk stops every agent and fails writes half way (2026-10-06); the floor
(``[resources] min_free_gb`` in ``config/site/nightly.toml``) turns that into one clear message
before the run starts. ``make doctor`` (``scripts/doctor.py``) warns against the same value.
"""

import shutil
from collections.abc import Callable
from pathlib import Path

from algotrade.core.model.errors import AlgoTradeError

GB = 1e9


def require_free_disk(
    path: Path,
    min_free_gb: float,
    free_bytes: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free,
) -> None:
    """Raise when the volume holding ``path`` has less than ``min_free_gb`` free."""
    free = free_bytes(path) / GB
    if free < min_free_gb:
        raise AlgoTradeError(
            f"only {free:.1f} GB free on the data volume, under the {min_free_gb:g} GB floor "
            "([resources] min_free_gb in config/site/nightly.toml): free space "
            "(scripts/worktree.sh --prune-merged, var/ caches) and the next start catches up"
        )
