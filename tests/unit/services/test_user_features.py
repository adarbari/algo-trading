"""User expression features through the services (ADR 0023 step 4): a user's selection and
config may name them, they join the config hash, another user never sees them, and
``check_user_features`` reports each one with a sample evaluation."""

from datetime import date
from pathlib import Path

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.configs import field_catalog, resolve_config
from algotrade.services.features import catalogue, check_user_features, config_features
from algotrade.services.selection import select
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.golden import load_golden
from algotrade_sources.framework.registry import fixture_source
from tests.conftest import GOLDEN_DIR, REPO_ROOT
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import write_rows

D1 = date(2020, 3, 2)
PS = "rollups/instrument/price_stats@v2"
FEATURES = """[drawdown_pct]
expr = "pct_from_high_52w * scale"
params = { scale = 100 }
dtype = "float"
unit = "pct_points"
description = "How far below the 52-week high, in percent"
null_meaning = "pct_from_high_52w is null"

[shallow]
expr = "drawdown_pct > -10"
dtype = "bool"
unit = "flag"
description = "Within 10% of the 52-week high"
null_meaning = "drawdown_pct is null"
"""
SELECTION = """name = "near_high"
[where]
all = [{field = "feature.shallow", op = "eq", value = true}]
"""
STRATEGY = """id = "mine"
kind = "strategy"
impl = "buy_and_hold"
selection = "near_high"
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "site").symlink_to(REPO_ROOT / "config" / "site")
    alice = tmp_path / "users" / "alice"
    for kind in ("features", "selections", "strategies"):
        (alice / kind).mkdir(parents=True)
    (alice / "features" / "mine.toml").write_text(FEATURES)
    (alice / "selections" / "near_high.toml").write_text(SELECTION)
    (alice / "strategies" / "mine.toml").write_text(STRATEGY)
    (tmp_path / "users" / "bob" / "strategies").mkdir(parents=True)
    (tmp_path / "users" / "bob" / "strategies" / "mine.toml").write_text(STRATEGY)
    (tmp_path / "users" / "bob" / "selections").mkdir()
    (tmp_path / "users" / "bob" / "selections" / "near_high.toml").write_text(SELECTION)
    return tmp_path


@pytest.fixture(scope="module")
def reader() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    load_golden(task_ctx(writer), fixture_source("synthetic", GOLDEN_DIR))
    rows = [{"instrument_id": i, "close": c, "high_52w": 100.0, "low_52w": 50.0}
            for i, c in (("EQ:BULL", 95.0), ("EQ:BEAR", 52.0))]  # fmt: skip
    write_rows(writer, PS, D1, rows)
    return StoreReader(backend)


def test_a_user_selection_names_user_features(root: Path, reader: StoreReader) -> None:
    store = FileConfigStore(root)
    resolved = resolve_config(store, "mine", UserContext("alice"))
    assert [d.name for d in resolved.features] == ["drawdown_pct", "shallow"]  # + what it reads
    assert resolved.canonical()["features"]["drawdown_pct"]["params"] == {"scale": 100}
    assert resolved.selection is not None
    picked = select(reader, resolved.selection, D1, features=config_features(resolved))
    assert picked.instruments == ("EQ:BULL",)


def test_editing_a_user_feature_changes_the_config_hash(root: Path) -> None:
    store = FileConfigStore(root)
    before = resolve_config(store, "mine", UserContext("alice")).hash
    path = root / "users" / "alice" / "features" / "mine.toml"
    path.write_text(FEATURES.replace("scale = 100", "scale = 50"))
    after = resolve_config(store, "mine", UserContext("alice"))
    assert after.hash != before
    assert config_features(after).expressions["drawdown_pct"].definition.params == {"scale": 50}
    unrelated = '\n[other]\nexpr = "1.0"\ndtype = "float"\nunit = "decimal"\n'
    path.write_text(path.read_text() + unrelated + 'description = "d"\nnull_meaning = "n"\n')
    assert resolve_config(store, "mine", UserContext("alice")).hash == after.hash  # not read


def test_another_user_never_sees_them(root: Path) -> None:
    store = FileConfigStore(root)
    assert "feature.shallow" in field_catalog(store, "alice").fields
    assert "feature.shallow" not in field_catalog(store, "bob").fields
    assert "feature.shallow" not in field_catalog(store, SITE_USER).fields
    assert "shallow" not in catalogue(store).expressions  # the site's catalogue
    with pytest.raises(ConfigurationError, match=r"unknown field 'feature\.shallow'"):
        resolve_config(store, "mine", UserContext("bob"))


def test_check_user_features_types_inputs_and_a_sample(root: Path, reader: StoreReader) -> None:
    checks = {c.name: c for c in check_user_features(reader, FileConfigStore(root), "alice")}
    drawdown = checks["drawdown_pct"]
    assert (drawdown.dtype, drawdown.kind, drawdown.inputs) == (
        "float", "expression", ("pct_from_high_52w@v1",)
    )  # fmt: skip
    assert (drawdown.session, drawdown.rows, drawdown.non_null) == (D1, 2, 2)
    assert dict(drawdown.sample)["EQ:BULL"] == pytest.approx(-5.0)
    assert dict(checks["shallow"].sample) == {"EQ:BULL": True, "EQ:BEAR": False}
    offline = check_user_features(None, FileConfigStore(root), "alice")
    assert [c.session for c in offline] == [None, None]
    assert check_user_features(reader, FileConfigStore(root), "bob") == []
