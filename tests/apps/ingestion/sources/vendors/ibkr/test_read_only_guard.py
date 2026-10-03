"""Fitness: broker access is READ-ONLY by construction (ADR 0026).

- No module in ``src/`` or ``apps/`` references an order or account API of ``ib_async``
  (``ORDER_AND_ACCOUNT``): not as a name, an attribute, an imported name, a keyword or a
  string (``getattr(ib, "placeOrder")``).
- A module that imports ``ib_async`` also avoids the generic names of those APIs
  (``GENERIC``: ``Order``, ``Trade``, ``portfolio``, ``positions``...), imports only
  ``ALLOWED_IMPORTS`` from it, and is the facade (``FACADE``): no other module imports it.
- The checker itself is proven: a planted ``placeOrder`` reference is caught.

The import-linter contract "Broker API: only the read-only IBKR facade imports ib_async"
guards the import rule too; the facade's runtime guard is tested with the vendor
(``tests/apps/ingestion/sources/vendors/ibkr/test_gateway.py``).
"""

import ast
from collections.abc import Iterable
from pathlib import Path

from tests.conftest import REPO_ROOT

FACADE = "apps/ingestion/algotrade_ingestion/sources/vendors/ibkr/gateway.py"
BROKER_PACKAGES = ("ib_async", "ib_insync", "ibapi")
ORDER_AND_ACCOUNT = frozenset(
    {
        # orders
        "placeOrder", "cancelOrder", "reqGlobalCancel", "bracketOrder", "oneCancelsAll",
        "whatIfOrder", "whatIfOrderAsync", "MarketOrder", "LimitOrder", "StopOrder",
        "StopLimitOrder", "BracketOrder", "exerciseOptions", "reqOpenOrders",
        "reqAllOpenOrders", "reqAutoOpenOrders", "reqCompletedOrders", "openOrders",
        "openTrades",
        # accounts, positions, executions, P&L
        "reqAccountUpdates", "reqAccountUpdatesMulti", "reqAccountSummary", "accountSummary",
        "accountValues", "reqPositions", "reqPositionsMulti", "reqExecutions",
        "reqPnL", "reqPnLSingle", "managedAccounts", "reqManagedAccts", "requestFA",
        "replaceFA", "StartupFetchALL",
    }
)  # fmt: skip
GENERIC = frozenset(
    {"Order", "Trade", "Fill", "Execution", "portfolio", "positions", "executions", "fills",
     "trades", "orders", "pnl", "PortfolioItem", "Position", "AccountValue"}
)  # fmt: skip
ALLOWED_IMPORTS = frozenset({"IB", "Stock", "Option"})


def code_files() -> list[Path]:
    return sorted(
        p
        for top in ("src", "apps")
        for p in (REPO_ROOT / top).rglob("*.py")
        if ".venv" not in p.parts
    )


def _imports_broker(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            a.name.split(".")[0] in BROKER_PACKAGES for a in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").split(".")[0] in BROKER_PACKAGES
        ):
            return True
    return False


def _names(node: ast.AST) -> Iterable[str]:
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, ast.Attribute):
        yield node.attr
    elif isinstance(node, ast.alias):
        yield node.name.rsplit(".", 1)[-1]
        if node.asname:
            yield node.asname
    elif isinstance(node, ast.keyword) and node.arg:
        yield node.arg
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        yield node.name


def violations(path: Path, root: Path = REPO_ROOT) -> list[str]:
    """Every forbidden reference in one module, as ``path:line name (why)``."""
    tree = ast.parse(path.read_text())
    broker = _imports_broker(tree)
    where = path.relative_to(root).as_posix()
    found = []
    if broker and where != FACADE:
        found.append(f"{where}: imports a broker API; only {FACADE} may")
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        for name in _names(node):
            if name in ORDER_AND_ACCOUNT:
                found.append(f"{where}:{line} {name} (order / account API)")
            elif broker and name in GENERIC:
                found.append(f"{where}:{line} {name} (order / account name near ib_async)")
        if (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").split(".")[0] in BROKER_PACKAGES
        ):
            extra = {a.name for a in node.names} - ALLOWED_IMPORTS
            if extra:
                found.append(f"{where}:{line} imports {sorted(extra)} from ib_async")
    return found


def test_no_order_or_account_api_anywhere() -> None:
    found = [v for path in code_files() for v in violations(path)]
    assert not found, "broker access is read-only (ADR 0026):\n" + "\n".join(found)


def test_only_the_facade_imports_the_broker_api() -> None:
    importers = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in code_files()
        if _imports_broker(ast.parse(p.read_text()))
    ]
    assert importers == [FACADE]


def test_the_checker_catches_a_planted_order(tmp_path: Path) -> None:
    planted = {
        "call.py": "def go(ib):\n    ib.placeOrder(None, None)\n",
        "string.py": "def go(ib):\n    return getattr(ib, 'cancelOrder')\n",
        "account.py": "def go(ib):\n    return ib.accountValues()\n",
        "facade_like.py": "from ib_async import IB, MarketOrder\n",
        "generic.py": "import ib_async\n\ndef go(ib):\n    return ib.positions()\n",
    }
    for name, source in planted.items():
        path = tmp_path / name
        path.write_text(source)
        assert violations(path, tmp_path), f"{name} was not caught"
    clean = tmp_path / "clean.py"
    clean.write_text("def go(portfolio):\n    return portfolio.value\n")  # no ib_async here
    assert violations(clean, tmp_path) == []
