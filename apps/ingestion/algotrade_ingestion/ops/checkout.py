"""Refuse to run the nightly on code from a git worktree instead of the main checkout.

Worktrees link ``.venv`` to the main checkout's, so ``uv sync`` / ``make install`` inside one
rewrites that venv's editable installs to the worktree's ``src/`` and ``apps/``: launchd's
nightly (``ops/schedule.py``) would then run an unmerged branch against the real store. A
worktree marks its root with a ``.git`` *file*; the main checkout has a ``.git`` directory.
"""

from pathlib import Path

import algotrade
import algotrade_ingestion
from algotrade.core.model.errors import AlgoTradeError

# The library and this app: the code a nightly runs (the sources package follows the library).
PACKAGES = (Path(algotrade.__file__), Path(algotrade_ingestion.__file__))


def worktree_of(path: Path) -> Path | None:
    """The root of the git worktree holding ``path``; ``None`` in a main checkout (or none)."""
    for d in path.resolve().parents:
        marker = d / ".git"
        if marker.is_dir():
            return None
        if marker.is_file():
            return d
    return None


def ensure_main_checkout(packages: tuple[Path, ...] = PACKAGES) -> None:
    """Raise when any of ``packages`` is imported from a git worktree."""
    for package in packages:
        worktree = worktree_of(package)
        if worktree is not None:
            raise AlgoTradeError(
                f"refusing to run the nightly: {package.parent.name} is imported from the "
                f"worktree {worktree}, not the main checkout. Fix: run `make doctor` in the main "
                "checkout and run the fix it prints (the shared venv was synced from a "
                "worktree), or unset PYTHONPATH."
            )
