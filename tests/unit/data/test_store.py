from pathlib import Path

import pytest

from algotrade.core.errors import ConfigurationError, DataValidationError
from algotrade.data.store import DatasetStore
from tests.factories import series_from_closes


@pytest.fixture
def store(tmp_path: Path) -> DatasetStore:
    s = DatasetStore(tmp_path)
    s.write("demo", "a demo", {"A": series_from_closes([1, 2, 3], "A")}, ("tag",))
    return s


def test_write_then_load(store: DatasetStore) -> None:
    data = store.load("demo")
    assert list(data["A"].close) == [1, 2, 3]
    info = store.manifest()["demo"]
    assert info.tags == ("tag",)
    assert store.names() == ["demo"]


def test_verify_detects_tampering(store: DatasetStore, tmp_path: Path) -> None:
    assert store.verify() == []
    path = tmp_path / "demo" / "A.csv"
    path.write_text(path.read_text().replace("3.000000", "4.000000"))
    assert any("checksum" in p for p in store.verify())
    path.unlink()
    assert any("missing" in p for p in store.verify())


def test_unknown_dataset(store: DatasetStore) -> None:
    with pytest.raises(DataValidationError, match="unknown dataset"):
        store.load("nope")


def test_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        DatasetStore(tmp_path / "empty").manifest()
