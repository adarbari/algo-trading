"""A folder of HistoricalOptionData zips is scanned by member names alone (ADR 0086): daily and
monthly (``L2_``) zips, the stock history zip, a corrupt zip skipped, a member streamed."""

import zipfile
from datetime import date
from pathlib import Path

from algotrade_sources.vendors.historicaloptiondata.archive import (
    open_member,
    scan,
    stock_history_zips,
)

FIXTURES = Path(__file__).parents[4] / "fixtures" / "sources" / "historicaloptiondata"


def make_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, fixture in members.items():
            archive.write(FIXTURES / fixture, name)


def test_daily_and_monthly_zips_are_both_found(tmp_path: Path) -> None:
    make_zip(
        tmp_path / "Sample_L2_20190815.zip",
        {
            "options_20190815.csv": "options_20190815.csv",
            "stockquotes_20190815.csv": "stockquotes_20190815.csv",
            "optionstats_20190815.csv": "optionstats_20190815.csv",
        },
    )
    (tmp_path / "2019").mkdir()
    make_zip(
        tmp_path / "2019" / "L2_2019_August.zip",
        {"L2_options_20190816.csv": "options_20190816.csv"},
    )
    (tmp_path / "broken.zip").write_bytes(b"not a zip")
    found = scan(tmp_path)
    assert list(found) == [date(2019, 8, 15), date(2019, 8, 16)]
    assert found[date(2019, 8, 15)].complete
    assert found[date(2019, 8, 16)].members == {"options": "L2_options_20190816.csv"}
    assert not found[date(2019, 8, 16)].complete  # no stock quotes or stats in that zip


def test_a_session_in_two_zips_takes_the_later_named_zip(tmp_path: Path) -> None:
    for name in ("a_old.zip", "b_new.zip"):
        make_zip(tmp_path / name, {"options_20190815.csv": "options_20190815.csv"})
    assert scan(tmp_path)[date(2019, 8, 15)].zip_path.name == "b_new.zip"


def test_the_stock_history_zip_is_told_apart(tmp_path: Path) -> None:
    make_zip(
        tmp_path / "stockhistory.zip",
        {"dividends.csv": "dividends.csv", "stocksplits.csv": "stocksplits.csv"},
    )
    make_zip(tmp_path / "other.zip", {"options_20190815.csv": "options_20190815.csv"})
    assert [p.name for p in stock_history_zips(tmp_path)] == ["stockhistory.zip"]


def test_a_member_streams_out_of_its_zip(tmp_path: Path) -> None:
    make_zip(tmp_path / "d.zip", {"options_20190815.csv": "options_20190815.csv"})
    stream = open_member(tmp_path / "d.zip", "options_20190815.csv")
    try:
        assert stream.readline().startswith(b"UnderlyingSymbol")
    finally:
        stream.close()
