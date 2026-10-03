from datetime import UTC, datetime
from pathlib import Path

import pytest

from algotrade.core.errors import ConfigurationError, DataValidationError
from algotrade.data import StoreReader
from algotrade.services.datasets import list_datasets, load_dataset
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.golden import load_golden
from algotrade_ingestion.sources.synthetic.files import GoldenFiles
from tests.factories import series_from_closes

CLOCK = lambda: datetime(2026, 10, 3, tzinfo=UTC)  # noqa: E731


@pytest.fixture
def files(tmp_path: Path) -> GoldenFiles:
    f = GoldenFiles(tmp_path)
    f.write(
        "demo",
        "a demo",
        {"A": series_from_closes([1, 2, 3], "A"), "B": series_from_closes([5, 6, 7], "B")},
        ("tag",),
    )
    return f


def test_write_read_and_manifest(files: GoldenFiles) -> None:
    frame = files.read("demo", "A")
    assert list(frame["close"]) == [1, 2, 3]
    assert str(frame["ts"].dt.tz) == "UTC"
    info = files.manifest()["demo"]
    assert (info.tags, info.symbols) == (("tag",), ("A", "B"))


def test_verify_detects_tampering(files: GoldenFiles, tmp_path: Path) -> None:
    assert files.verify() == []
    path = tmp_path / "demo" / "A.csv"
    path.write_text(path.read_text().replace("3.000000", "4.000000"))
    assert any("checksum" in p for p in files.verify())
    backend = MemoryBackend()
    with pytest.raises(ValueError, match="verification"):
        load_golden(StoreWriter(backend), files, CLOCK)
    path.unlink()
    assert any("missing" in p for p in files.verify())


def test_read_rejects_bad_bars(files: GoldenFiles, tmp_path: Path) -> None:
    path = tmp_path / "demo" / "A.csv"
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2], lines[1], lines[3]]) + "\n")
    with pytest.raises(DataValidationError, match="increasing"):
        files.read("demo", "A")
    with pytest.raises(DataValidationError, match=r"NaN|non-positive|high"):
        files.write("bad", "bad", {"X": series_from_closes([-1, 2], "X")}, ())


def test_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        GoldenFiles(tmp_path / "empty").manifest()


def test_load_into_store_and_read_back(files: GoldenFiles) -> None:
    backend = MemoryBackend()
    record = load_golden(StoreWriter(backend), files, CLOCK)
    assert record.stats == {"datasets": 1, "instruments": 2, "sessions": 3, "bars": 6}
    reader = StoreReader(backend)
    info = list_datasets(reader)["demo"]
    assert info.instruments == ("EQ:A", "EQ:B")
    series, terms = load_dataset(reader, "demo")
    assert list(series["EQ:B"].close) == [5, 6, 7]
    assert terms["EQ:A"].multiplier == 1.0
