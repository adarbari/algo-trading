"""The no-ML guard (EB D9): FINRA's website terms bar machine learning over its data, so the
tables that hold it are ``no_ml = true`` in ``architecture/tables.toml``, the same set the code
refuses (``schemas.NO_ML_TABLES``), and no learned scorer may read them:

- the flags in ``tables.toml`` and ``NO_ML_TABLES`` are one set, and every flagged table exists;
- no edge document's ``[scorer] features`` reads a no_ml table through the site catalogue
  (``training.no_ml``: the same check the training frame runs before it reads anything);
- the training frame is the only door of a fit: ``training_frame`` itself calls ``refuse_no_ml``
  (so no caller can skip the check), and nothing else under ``services/evaluation/training``
  reads stored values.
"""

import ast
import tomllib

from algotrade.config.edges.loading import load_edges
from algotrade.features.site import site_features
from algotrade.services.evaluation.training.no_ml import no_ml_reads
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.schemas import KNOWN, NO_ML_TABLES
from tests.conftest import REPO_ROOT

TABLES = tomllib.loads((REPO_ROOT / "architecture" / "tables.toml").read_text())["table"]
TRAINING = REPO_ROOT / "src" / "algotrade" / "services" / "evaluation" / "training"


def test_tables_toml_and_the_code_flag_the_same_tables() -> None:
    flagged = {t["name"] for t in TABLES if t.get("no_ml")}
    assert flagged == set(NO_ML_TABLES)
    assert flagged <= set(KNOWN), "a no_ml table without a schema"


def test_no_edge_scorer_reads_a_no_ml_table() -> None:
    configs = FileConfigStore(REPO_ROOT / "config", local=False)
    features = site_features(configs)
    edges = load_edges(configs)
    assert any(e.scorer_features for e in edges), "no scorer to check: the test would be empty"
    for edge in edges:
        assert not no_ml_reads(features, edge.scorer_features), edge.id


def test_the_training_frame_runs_the_guard() -> None:
    tree = ast.parse((TRAINING / "frame.py").read_text())
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    frame = functions["training_frame"]
    called = {
        n.func.id
        for n in ast.walk(frame)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "refuse_no_ml" in called


def test_nothing_else_in_training_reads_a_stored_table() -> None:
    allowed = {"frame.py", "no_ml.py"}
    for path in TRAINING.glob("*.py"):
        text = path.read_text()
        if path.name not in allowed:
            assert "read_outcomes" not in text and "fields_view" not in text, path.name
