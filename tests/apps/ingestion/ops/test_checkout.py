"""The nightly refuses to run on code imported from a git worktree."""

from pathlib import Path

import pytest

from algotrade.core.model.errors import AlgoTradeError
from algotrade_ingestion.ops.checkout import ensure_main_checkout, worktree_of


def _package(root: Path, *, worktree: bool) -> Path:
    """``root/src/algotrade/__init__.py`` in a main checkout (``.git`` dir) or a worktree."""
    if worktree:
        root.mkdir(parents=True)
        (root / ".git").write_text("gitdir: /main/.git/worktrees/x\n")
    else:
        (root / ".git").mkdir(parents=True)
    init = root / "src" / "algotrade" / "__init__.py"
    init.parent.mkdir(parents=True)
    init.touch()
    return init


def test_main_checkout_code_runs(tmp_path: Path) -> None:
    init = _package(tmp_path / "algo-trading", worktree=False)
    assert worktree_of(init) is None
    ensure_main_checkout((init,))


def test_code_outside_any_checkout_runs(tmp_path: Path) -> None:
    init = tmp_path / "site-packages" / "algotrade" / "__init__.py"
    init.parent.mkdir(parents=True)
    init.touch()
    ensure_main_checkout((init,))


@pytest.mark.parametrize("where", ["algo-trading-feat-x", "algo-trading/.claude/worktrees/agent-a"])
def test_worktree_code_is_refused_with_the_fix(tmp_path: Path, where: str) -> None:
    (tmp_path / "algo-trading" / ".git").mkdir(parents=True)
    main_init = tmp_path / "algo-trading" / "src" / "algotrade" / "__init__.py"
    main_init.parent.mkdir(parents=True)
    main_init.touch()
    wt_init = _package(tmp_path / where, worktree=True)
    assert worktree_of(wt_init) == (tmp_path / where).resolve()
    with pytest.raises(AlgoTradeError, match="make doctor") as exc:
        ensure_main_checkout((main_init, wt_init))
    assert str((tmp_path / where).resolve()) in str(exc.value)
