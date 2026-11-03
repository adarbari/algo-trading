"""The ``dossier-import`` task: a reviewed dossier lands in its three tables stamped ``known_from``
= the import session, a bad file stores nothing, and a rerun stores the same rows."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.services.attributing.dossier import DossierError
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.events.dossier import run as dossier
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import write_reference
from tests.unit.services.attributing.test_dossier import GOOD

SESSION = date(2026, 11, 3)


def _store() -> StoreWriter:
    writer = StoreWriter(MemoryBackend())
    write_reference(writer, SESSION, {"MU": "EQ:MU"})
    return writer


def _file(tmp_path: Path, text: str = GOOD) -> Path:
    path = tmp_path / "MU.toml"
    path.write_text(text)
    return path


def _table(writer: StoreWriter, name: str) -> pd.DataFrame | None:
    return StoreReader(writer._backend).table(name, SESSION)


def test_a_dossier_is_stored_known_from_the_import_session(tmp_path: Path) -> None:
    writer = _store()
    dossier.ingest_dossiers(task_ctx(writer), SESSION, _file(tmp_path))
    factors = _table(writer, dossier.FACTORS)
    assert factors is not None and set(factors["factor_id"]) == {"hbm-pricing", "old-capex"}
    assert set(factors["known_from"]) == {SESSION}
    occurrences = _table(writer, dossier.OCCURRENCES)
    assert occurrences is not None and len(occurrences) == 2
    attribution = StoreReader(writer._backend).table(dossier.ATTRIBUTIONS, date(2026, 10, 26))
    assert attribution is not None
    row = attribution.iloc[0]
    assert row["source"] == "analyst_review" and row["known_from"] == SESSION


def test_a_folder_of_dossiers_is_one_import_and_a_bad_file_stores_nothing(tmp_path: Path) -> None:
    writer = _store()
    _file(tmp_path)
    (tmp_path / "bad.toml").write_text(GOOD.replace('"MU"', '"ZZZZ"'))
    with pytest.raises(DossierError, match="ZZZZ"):
        dossier.ingest_dossiers(task_ctx(writer), SESSION, tmp_path)
    assert _table(writer, dossier.FACTORS) is None


def test_two_files_for_one_name_are_refused(tmp_path: Path) -> None:
    writer = _store()
    _file(tmp_path)
    (tmp_path / "again.toml").write_text(GOOD)
    with pytest.raises(DossierError, match="is also in"):
        dossier.ingest_dossiers(task_ctx(writer), SESSION, tmp_path)


def test_a_rerun_stores_the_same_rows(tmp_path: Path) -> None:
    writer = _store()
    path = _file(tmp_path)
    dossier.ingest_dossiers(task_ctx(writer), SESSION, path)
    dossier.ingest_dossiers(task_ctx(writer), SESSION, path)
    factors = _table(writer, dossier.FACTORS)
    assert factors is not None and len(factors) == 2


def test_a_missing_path_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        dossier.ingest_dossiers(task_ctx(_store()), SESSION, tmp_path / "none")
