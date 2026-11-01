"""``french_zip`` (Kenneth French's data library, ADR 0089) against the seven daily US files
recorded 2026-11-01 (vintage 202609 CRSP; trimmed to the preamble, the first and last ten rows of
each section and the footer) and every series of ``config/site/macro/french.toml`` against its
file; plus the parser's rules on small synthetic zips. CI never calls the network."""

import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from algotrade.config.site.settings import load_macro
from algotrade.storage.configs.files import FileConfigStore
from algotrade_sources.framework.series import SERIES_COLUMNS, SeriesRequest
from algotrade_sources.vendors.published.csv_series import parse_series
from algotrade_sources.vendors.published.parsers import PARSERS

REPO = Path(__file__).resolve().parents[5]
RECORDED = REPO / "tests" / "fixtures" / "sources" / "published"
FIXTURE = {  # the library's zip -> its trimmed recording
    "F-F_Research_Data_Factors_daily_CSV.zip": "french_ff3_daily.zip",
    "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip": "french_ff5_daily.zip",
    "F-F_Momentum_Factor_daily_CSV.zip": "french_mom_daily.zip",
    "F-F_ST_Reversal_Factor_daily_CSV.zip": "french_st_rev_daily.zip",
    "F-F_LT_Reversal_Factor_daily_CSV.zip": "french_lt_rev_daily.zip",
    "12_Industry_Portfolios_daily_CSV.zip": "french_ind12_daily.zip",
    "49_Industry_Portfolios_daily_CSV.zip": "french_ind49_daily.zip",
}
french = PARSERS["french_zip"]


def zipped(text: str, name: str = "x.csv") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, text.replace("\n", "\r\n"))
    return buffer.getvalue()


def test_every_recorded_file_reads_its_columns_and_dates() -> None:
    shape = {  # file -> (columns, first date, last date), 10 + 10 rows per section
        "french_ff3_daily.zip": (["Mkt-RF", "SMB", "HML", "RF"], "1926-07-01", "2026-09-30"),
        "french_ff5_daily.zip": (
            ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"], "1963-07-01", "2026-09-30",
        ),
        "french_mom_daily.zip": (["Mom"], "1926-11-03", "2026-09-30"),
        "french_st_rev_daily.zip": (["ST_Rev"], "1926-01-26", "2026-09-30"),
        "french_lt_rev_daily.zip": (["LT_Rev"], "1930-03-20", "2026-09-30"),
    }  # fmt: skip
    for name, (columns, first, last) in shape.items():
        frame = french((RECORDED / name).read_bytes())
        assert list(frame.columns) == ["date", *columns], name
        assert len(frame) == 20 and frame["date"].notna().all(), name
        assert (frame["date"].iloc[0], frame["date"].iloc[-1]) == (first, last), name
        assert frame["date"].is_monotonic_increasing, name


def test_the_industry_files_hold_a_value_and_an_equal_weighted_section() -> None:
    payload = (RECORDED / "french_ind12_daily.zip").read_bytes()
    value, equal = french(payload, 1), french(payload, 2)
    assert value["NoDur"].iloc[0] == "0.02" and equal["NoDur"].iloc[0] == "0.37"  # as published
    assert value["date"].iloc[0] == equal["date"].iloc[0] == "1926-07-01"
    wide = french((RECORDED / "french_ind49_daily.zip").read_bytes(), 2)
    assert wide.shape[1] == 50 and wide.columns[1] == "Agric" and wide.columns[-1] == "Other"
    with pytest.raises(ValueError, match="no section 3"):
        french(payload, 3)
    with pytest.raises(ValueError, match="no section 0"):
        french(payload, 0)


def test_the_header_cells_lose_their_padding_and_the_first_is_the_date() -> None:
    rows = "20260102,  1.5,  2\n20260105, -99.99, -999\n"
    text = f"preamble\n\nmore\n,Mom   ,Other \n{rows}\nCopyright\n"
    frame = french(zipped(text))
    assert list(frame.columns) == ["date", "Mom", "Other"]
    assert frame["date"].tolist() == ["2026-01-02", "2026-01-05"]
    assert frame["Mom"].iloc[0] == "1.5" and frame["Mom"].isna().tolist() == [False, True]
    assert frame["Other"].isna().tolist() == [False, True]  # -99.99 and -999: no value


def test_a_preamble_with_blank_lines_and_a_footer_are_never_read() -> None:
    text = "a\n\nb\n\n\n  Title\n,X\n20260102,1\n\n  Second\n,X\n20260102,9\n\nCopyright 2026\n"
    assert french(zipped(text), 1)["X"].tolist() == ["1"]
    assert french(zipped(text), 2)["X"].tolist() == ["9"]
    assert french(zipped(",X\n20260102,1")).shape == (1, 2)  # no trailing blank line


def test_a_bad_date_is_no_date_and_a_non_zip_or_odd_zip_is_refused() -> None:
    frame = french(zipped(",X\n20261340,1\n20260102,2\n"))
    assert frame["date"].isna().tolist() == [True, False] and frame["date"].iloc[1] == "2026-01-02"
    with pytest.raises(ValueError, match="not a zip"):
        french(b"PK not really a zip")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.csv", ",X\n")
        archive.writestr("b.csv", ",X\n")
    with pytest.raises(ValueError, match="one CSV"):
        french(buffer.getvalue())
    with pytest.raises(ValueError, match="no section 1"):
        french(zipped("nothing but text\n"))


def test_the_request_names_the_section_and_the_column() -> None:
    payload = (RECORDED / "french_ind12_daily.zip").read_bytes()
    base = {"url": "https://example.org/f.zip", "date_column": "date", "parser": "french_zip"}
    first = parse_series(SeriesRequest("A", value_column="Durbl", **base), payload)
    second = parse_series(SeriesRequest("B", value_column="Durbl", section=2, **base), payload)
    assert tuple(first.columns) == SERIES_COLUMNS
    assert first["value"].iloc[0] == pytest.approx(-0.28)
    assert second["value"].iloc[0] == pytest.approx(-0.19)
    assert first["obs_date"].dt.date.iloc[0] == date(1926, 7, 1)
    assert first["vintage_date"].isna().all() and set(first["code"]) == {"Durbl"}


def test_the_shipped_registry_reads_every_series_from_its_recorded_file() -> None:
    registry = [
        s for s in load_macro(FileConfigStore(REPO / "config")).series
        if s.parser == "french_zip"
    ]  # fmt: skip
    keys = {s.key for s in registry}
    assert len(registry) == len(keys) == 4 + 6 + 3 + 24 + 98
    assert {"FF3_MKT_RF", "FF5_CMA", "FF_MOM", "FF_ST_REV", "FF_LT_REV", "IND12_NODUR",
            "IND12EW_NODUR", "IND49_HLTH", "IND49EW_OTHER"} <= keys  # fmt: skip
    for spec in registry:
        name = FIXTURE[spec.url.rsplit("/", 1)[-1]]
        assert spec.source == "published" and spec.pit == "lag" and spec.revised, spec.key
        assert spec.licence == "personal" and spec.release_lag_days == 70, spec.key
        assert spec.refetch_days == 28 and spec.cadence == "monthly", spec.key
        assert spec.instrument_id == f"MACRO:{spec.key}"
        request = SeriesRequest(
            spec.key, code=spec.vendor_code, url=spec.url, date_column=spec.date_column,
            value_column=spec.value_column, parser=spec.parser, section=spec.section,
        )  # fmt: skip
        frame = parse_series(request, (RECORDED / name).read_bytes())
        assert len(frame) == 20 and frame["obs_date"].is_monotonic_increasing, spec.key
        assert pd.api.types.is_float_dtype(frame["value"]), spec.key
    # one request per zip per run: the industry zips serve two blocks
    assert len({s.url for s in registry}) == 7
    assert {s.section for s in registry if s.key.startswith(("IND12EW", "IND49EW"))} == {2}


def test_a_caller_changing_the_table_never_changes_the_next_read() -> None:
    payload = zipped(",X\n20260102,1\n")
    table = french(payload)
    table["X"] = "changed"
    assert french(payload)["X"].tolist() == ["1"]  # the cached table is not shared
