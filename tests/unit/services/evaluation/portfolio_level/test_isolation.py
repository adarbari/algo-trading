"""The portfolio provider reads only the setup's own trades (ADR 0088 G15, design item 26): its
folder imports no user store, no other setup's picks and no market data; the one store it reaches
is the paper record's reader, in ``paper.py`` alone."""

import ast
from pathlib import Path

from tests.conftest import REPO_ROOT

FOLDER = REPO_ROOT / "src/algotrade/services/evaluation/portfolio_level"
ALLOWED = (
    "algotrade.core",
    "algotrade.config.strategy.portfolio_fields",
    "algotrade.config.edges.positions",
    "algotrade.services.licences",
    "algotrade.services.evaluation.portfolio_level",
)
PAPER_ONLY = ("algotrade.data",)  # data.paper.reading and the StoreReader type


def _imports(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(a.name for a in node.names)
    return [m for m in found if m.startswith("algotrade")]


def test_the_folder_imports_only_the_setups_own_trades_machinery() -> None:
    for path in sorted(FOLDER.glob("*.py")):
        allowed = ALLOWED + (PAPER_ONLY if path.name == "paper.py" else ())
        for module in _imports(path):
            assert module.startswith(allowed), f"{path.name} imports {module}"


def test_it_names_no_user_store_and_no_picks_table() -> None:
    text = "\n".join(p.read_text() for p in FOLDER.glob("*.py"))
    for banned in ("EDGE_PICKS", "edge_picks", "config.user", "UserContext", "ConfigStore"):
        assert banned not in text
    assert "read_paper" in (FOLDER / "paper.py").read_text()
