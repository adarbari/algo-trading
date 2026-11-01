"""``macro.toml`` (ADR 0048): the shipped registry loads (tier-1 FRED series, the four index
levels, third-party and Stooq series personal), ids come from kind and key, and every rule
names the entry."""

from pathlib import Path
from typing import Any

import pytest

from algotrade.config.site.macro import MacroSeries, MacroSettings
from algotrade.config.site.settings import load_macro
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

REPO = Path(__file__).resolve().parents[4]

FRED = {
    "key": "UNRATE",
    "source": "fred",
    "kind": "macro",
    "cadence": "monthly",
    "release_lag_days": 35,
    "pit": "alfred",
    "terms": "FRED terms of use",
}
FILE = {
    "key": "SPX",
    "code": "^SPX",
    "source": "published",
    "kind": "index",
    "cadence": "daily",
    "pit": "lag",
    "terms": "Stooq",
    "url": "https://stooq.com/q/d/l/?s=^spx&i=d",
    "date_column": "Date",
    "value_column": "Close",
}


CBOE_STRATEGY_INDEXES = ("PUT", "WPUT", "BXM", "BXMD", "CNDR")
CBOE_SETUP_INPUTS = ("SKEW", "COR1M", "COR3M", "DSPX")  # EB D4: skew, correlation, dispersion


def load(*series: dict[str, Any]) -> MacroSettings:
    return MacroSettings.from_document({"series": list(series)})


def test_the_shipped_registry() -> None:
    macro = load_macro(FileConfigStore(REPO / "config", local=False))  # macro.toml + series/
    assert {"T10Y3M", "BAMLH0A0HYM2", "UNRATE", "NFCI", "RRPONTSYD"} <= macro.keys
    indices = {s.instrument_id: s.vendor_code for s in macro.series if s.kind == "index"}
    assert indices == {
        "IDX:SPX": "SP500",
        "IDX:COMP": "NASDAQCOM",
        "IDX:VIX": "VIXCLS",
        "IDX:VIX3M": "VXVCLS",
        "IDX:VIX9D": "VIX9D",  # Cboe's own files (EB D3): the code is the key
        "IDX:VIX6M": "VIX6M",
        "IDX:VVIX": "VVIX",
        **{f"IDX:{k}": k for k in CBOE_STRATEGY_INDEXES},  # ADR 0084: the replication targets
        **{f"IDX:{k}": k for k in CBOE_SETUP_INPUTS},
    }
    personal = {s.key for s in macro.series if s.licence == "personal"}
    third_party = {"BAMLH0A0HYM2", "BAMLC0A0CM", "BAA10Y", "COMP", "VIX", "VIX3M", "SPX"}
    third_party |= {
        "VIX9D",
        "VIX6M",
        "VVIX",
        *CBOE_STRATEGY_INDEXES,
        *CBOE_SETUP_INPUTS,
    }  # Cboe's files: personal use, no redistribution
    cape = {k for k in macro.keys if k.startswith("CAPE_")}  # Barclays' file: personal use
    french = {s.key for s in macro.series if s.research}  # French's library: personal, ADR 0089
    assert len(cape) == 26 and len(french) == 135
    assert personal == third_party | cape | french
    unrevised = {  # FRED's daily market series: never revised, so one plain request each
        "T10Y3M", "T10Y2Y", "BAMLH0A0HYM2", "BAMLC0A0CM", "BAA10Y", "DFII10", "RRPONTSYD",
        "SPX", "COMP", "VIX", "VIX3M",
    }  # fmt: skip
    for key in unrevised:
        spec = macro.by_key(key)
        assert (spec.source, spec.pit, spec.release_lag_days) == ("fred", "lag", 1), key
    assert all(macro.by_key(k).pit == "alfred" for k in ("UNRATE", "PAYEMS", "CPIAUCSL", "NFCI"))
    revised_late = {
        s.key: s.release_lag_days for s in macro.series if s.key in ("GDPNOW", "RECPROUSM156N")
    }
    assert min(revised_late.values()) >= 125  # a final value before ALFRED's first vintage
    assert all(s.terms for s in macro.series)
    files = {"EBP", "EBP_RECESSION_PROB", "OFR_FSI", "EPU_DAILY"}  # re-estimated in place
    assert {s.key for s in macro.series if s.revised} == files | cape | french
    assert all(macro.by_key(k).pit == "lag" and macro.by_key(k).is_revised for k in files)
    assert macro.by_key("UNRATE").is_revised and not macro.by_key("T10Y3M").is_revised
    assert macro.by_key("EBP").release_lag_days == 45  # the Fed posts irregularly
    assert load_macro(MemoryConfigStore({})).series == ()


def test_a_fred_and_a_published_series() -> None:
    macro = load(FRED, FILE)
    unrate, spx = macro.by_key("UNRATE"), macro.by_key("SPX")
    assert (unrate.instrument_id, unrate.vendor_code, unrate.parser) == (
        "MACRO:UNRATE",
        "UNRATE",
        "",
    )
    assert (unrate.transform, unrate.licence, unrate.release_lag_days) == ("level", "open", 35)
    assert (spx.instrument_id, spx.vendor_code, spx.parser) == ("IDX:SPX", "^SPX", "csv")
    assert isinstance(spx, MacroSeries)
    with pytest.raises(KeyError, match="NOPE"):
        macro.by_key("NOPE")


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ([FRED, FRED], r"more than once: \['UNRATE'\]"),
        ([{**FRED, "url": "https://x.org/a.csv"}], r"fred series takes no \['url'\]"),
        ([{**FILE, "pit": "alfred"}], "needs source"),
        ([{k: v for k, v in FILE.items() if k != "value_column"}], r"needs \['value_column'\]"),
        ([{**FILE, "url": "http://stooq.com/x"}], "https URL"),
        ([{**FRED, "key": "unrate"}], "key: expected"),
        ([{k: v for k, v in FRED.items() if k != "terms"}], "UNRATE terms: required"),
        ([{**FRED, "pit": "guess"}], "pit: expected one of"),
        ([{**FRED, "release_lag_days": -1}], "release_lag_days"),
        ([{**FRED, "colour": "red"}], "unknown keys"),
        ([{**FRED, "api_key": "x"}], "looks like a secret"),
    ],
)
def test_invalid_entries_fail_with_their_path(entries: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        load(*entries)


def test_the_document_shape_is_checked() -> None:
    with pytest.raises(ConfigurationError, match="unknown keys"):
        MacroSettings.from_document({"indices": []})
    with pytest.raises(ConfigurationError, match=r"\[\[series\]\]"):
        MacroSettings.from_document({"series": {"key": "X"}})


# --- config/site/series/<family>.toml: a file expanded into a series per column (ADR 0089)

BLOCK = {
    "defaults": {
        "source": "published", "kind": "macro", "cadence": "monthly", "pit": "lag",
        "release_lag_days": 70, "revised": True, "licence": "personal", "terms": "t",
        "parser": "french_zip", "date_column": "date",
    },
    "file": [
        {"prefix": "FF3", "url": "https://x.test/ff3.zip", "columns": ["Mkt-RF", "SMB"]},
        {"prefix": "IND12EW", "url": "https://x.test/i.zip", "section": 2, "columns": ["NoDur"]},
        {"prefix": "FF", "url": "https://x.test/m.zip", "columns": ["Mom   ", "LT_Rev"]},
    ],
}  # fmt: skip


def expand(files: dict[str, Any], *series: dict[str, Any]) -> MacroSettings:
    return MacroSettings.from_documents({"series": list(series)}, list(files.values()))


def test_a_file_block_expands_into_one_ordinary_series_per_column() -> None:
    macro = expand({"french": BLOCK}, FRED)
    assert [s.key for s in macro.series] == [
        "UNRATE", "FF3_MKT_RF", "FF3_SMB", "IND12EW_NODUR", "FF_MOM", "FF_LT_REV",
    ]  # fmt: skip
    smb, ew, mom = macro.by_key("FF3_SMB"), macro.by_key("IND12EW_NODUR"), macro.by_key("FF_MOM")
    assert (smb.value_column, smb.date_column, smb.parser, smb.section) == (
        "SMB", "date", "french_zip", 1,
    )  # fmt: skip
    assert (ew.section, ew.url) == (2, "https://x.test/i.zip")
    assert (mom.value_column, mom.instrument_id) == ("Mom   ", "MACRO:FF_MOM")
    assert all(
        s.licence == "personal" and s.revised and s.release_lag_days == 70 for s in macro.series[1:]
    )
    assert macro.by_key("FF3_MKT_RF").stale_after_days == 31 + 70 + 2  # monthly, not a daily margin


def test_a_block_overrides_the_defaults_and_a_key_clash_fails_across_both_places() -> None:
    block = {**BLOCK, "file": [{**BLOCK["file"][0], "release_lag_days": 10}]}
    assert expand({"f": block}).by_key("FF3_SMB").release_lag_days == 10
    with pytest.raises(ConfigurationError, match=r"more than once: \['FF3_SMB'\]"):
        expand({"f": BLOCK}, {**FILE, "key": "FF3_SMB"})
    with pytest.raises(ConfigurationError, match=r"more than once"):
        expand({"a": BLOCK, "b": BLOCK})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"columns": "*"}, r"list the file's columns"),
        ({"columns": []}, r"list the file's columns"),
        ({"prefix": ""}, "prefix: required"),
        ({"prefix": "ff3"}, "key: expected"),
        ({"section": 0}, "section"),
        ({"url": "http://x.test/a.zip"}, "https URL"),
        ({"colour": "red"}, "unknown keys"),
    ],
)
def test_an_invalid_file_block_fails_with_its_path(change: dict[str, Any], message: str) -> None:
    block = {**BLOCK, "file": [{**BLOCK["file"][0], **change}]}
    with pytest.raises(ConfigurationError, match=message) as raised:
        expand({"french": block})
    assert "series/*.toml" in str(raised.value)


def test_the_shape_of_a_files_document_is_checked() -> None:
    with pytest.raises(ConfigurationError, match="unknown keys"):
        expand({"f": {"colour": []}})
    with pytest.raises(ConfigurationError, match="defaults: expected a table"):
        expand({"f": {"defaults": 1}})
    with pytest.raises(ConfigurationError, match=r"\[\[file\]\]"):
        expand({"f": {"file": {"prefix": "X"}}})
    with pytest.raises(ConfigurationError, match="unknown keys"):
        expand({"f": {**BLOCK, "defaults": {**BLOCK["defaults"], "colour": "red"}}})
    assert expand({"f": {}}).series == ()


def test_a_fred_series_takes_no_section() -> None:
    with pytest.raises(ConfigurationError, match=r"takes no \['section'\]"):
        load({**FRED, "section": 2})


def test_the_shipped_french_file_loads_through_the_store() -> None:
    store = FileConfigStore(REPO_ROOT / "config", local=False)
    assert store.names("site", "series") == ["cboe", "french"]
    assert store.load("u", "series", "french") is None  # site-only
    macro = load_macro(store)
    french = [s for s in macro.series if s.parser == "french_zip"]
    assert len(french) == 135 and len(macro.series) == len(macro.keys)
    assert macro.by_key("UNRATE").parser == ""  # macro.toml's own series are still there


def test_the_family_files_of_series_join_the_one_registry() -> None:
    store = MemoryConfigStore(
        {
            ("site", "settings", "macro"): {"series": [FRED]},
            ("site", "series", "cboe"): {"series": [FILE]},
        }
    )
    assert [s.key for s in load_macro(store).series] == ["UNRATE", "SPX"]
    twice = MemoryConfigStore(
        {
            ("site", "settings", "macro"): {"series": [FILE]},
            ("site", "series", "cboe"): {"series": [FILE]},
        }
    )
    with pytest.raises(ConfigurationError, match=r"more than once: \['SPX'\]"):
        load_macro(twice)


def test_a_family_file_holds_only_series() -> None:
    for doc in ({"serie": [FILE]}, {"series": [FILE], "macro": {"run_budget_s": 5}}):
        store = MemoryConfigStore({("site", "series", "cboe"): doc})
        with pytest.raises(ConfigurationError):
            load_macro(store)
    odd = MemoryConfigStore({("site", "series", "cboe"): {"series": {"key": "X"}}})
    with pytest.raises(ConfigurationError, match="list of tables"):
        load_macro(odd)
