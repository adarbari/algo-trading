"""``HodFiles`` (ADR 0084): a folder of synthetic vendor zips as a source: the sessions with their
checksums, one session's frames with the index ids, the ``Source`` contract's fetch / normalize and
the stock history; a session whose options file is for another day is refused."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade_sources.framework.base import FetchRequest, HistoryFileSource
from algotrade_sources.framework.registry import FILE_SOURCES
from algotrade_sources.vendors.historicaloptiondata.files_source import HodFiles, hod_files
from tests.helpers.option_history.files import FIXTURES, folder, make_zip


def test_the_registry_builds_it_from_a_folder_and_it_is_a_history_source(tmp_path: Path) -> None:
    source = FILE_SOURCES["hod_files"](folder(tmp_path))
    assert isinstance(source, HodFiles) and isinstance(source, HistoryFileSource)
    assert hod_files().directory is None


def test_sessions_carry_the_member_checksum_and_whether_every_file_is_there(
    tmp_path: Path,
) -> None:
    sessions = HodFiles(folder(tmp_path)).sessions()
    assert [s.session for s in sessions] == [date(2019, 8, 15), date(2019, 8, 16)]
    assert [s.complete for s in sessions] == [True, True]
    assert all(len(s.checksum.split(":")[0]) == 8 for s in sessions)
    assert sessions[0].location == "Sample_L2_20190815.zip"
    assert sessions[0].checksum != sessions[1].checksum


def test_a_session_reads_into_its_three_tables_with_index_ids(tmp_path: Path) -> None:
    bundle = HodFiles(folder(tmp_path)).read(date(2019, 8, 16))
    assert set(bundle.tables) == {
        "option_history/quotes",
        "option_history/underlying",
        "option_history/stats",
    }
    quotes = bundle.tables["option_history/quotes"]
    ids = quotes.groupby("symbol")["underlying_id"].first().to_dict()
    assert ids["SPX"] == "IDX:SPX" and ids["SPXW"] == "IDX:SPX"
    assert pd.isna(ids["SPY"])  # a listing id is the task's to give
    assert bundle.notes["rows"] == len(quotes)


def test_fetch_and_normalize_are_the_source_contract_over_the_options_file(
    tmp_path: Path,
) -> None:
    source = HodFiles(folder(tmp_path))
    request = FetchRequest("2019-08-15")
    payload = source.fetch(request)
    assert payload is not None and payload.startswith(b"UnderlyingSymbol")
    normalized = source.normalize(request, payload)
    assert normalized is not None and normalized.session_date == date(2019, 8, 15)
    assert source.fetch(FetchRequest("2001-01-02")) is None


def test_the_stock_history_is_none_without_its_zip_and_two_tables_with_it(tmp_path: Path) -> None:
    make_zip(tmp_path / "d.zip", {"options_20190815.csv": "options_20190815.csv"})
    assert HodFiles(tmp_path).stock_history() is None
    history = (
        HodFiles(folder(tmp_path / "x")).stock_history()
        if (tmp_path / "x").mkdir() is None
        else None
    )
    assert history is not None
    assert set(history.tables) == {"option_history/dividends", "option_history/splits"}


def test_an_options_file_for_another_day_is_refused(tmp_path: Path) -> None:
    make_zip(tmp_path / "d.zip", {"options_20190815.csv": "options_20190816.csv"})
    with pytest.raises(ValueError, match="is for 2019-08-16"):
        HodFiles(tmp_path).read(date(2019, 8, 15))
    assert FIXTURES.is_dir()


def test_the_checksum_covers_every_member_of_a_session(tmp_path: Path) -> None:
    make_zip(tmp_path / "a.zip", {"options_20190815.csv": "options_20190815.csv"})
    before = HodFiles(tmp_path).sessions()[0]
    make_zip(
        tmp_path / "a.zip",
        {
            "options_20190815.csv": "options_20190815.csv",
            "stockquotes_20190815.csv": "stockquotes_20190815.csv",
        },
    )
    after = HodFiles(tmp_path).sessions()[0]
    assert before.checksum != after.checksum  # a file added later re-imports the session


def test_an_options_file_with_no_row_we_keep_is_refused(tmp_path: Path) -> None:
    lines = (FIXTURES / "options_20190815.csv").read_text().splitlines()
    adjusted = [lines[0], *(line for line in lines[1:] if "AAPL1190816" in line)]
    make_zip(
        tmp_path / "d.zip",
        {
            "options_20190815.csv": "\n".join(adjusted).encode(),
            "stockquotes_20190815.csv": "stockquotes_20190815.csv",
        },
    )
    with pytest.raises(ValueError, match="no rows we keep"):
        HodFiles(tmp_path).read(date(2019, 8, 15))


def test_without_a_source_folder_the_source_says_so() -> None:
    with pytest.raises(ConfigurationError, match="--source-dir"):
        hod_files().sessions()
