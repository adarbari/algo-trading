"""``macro.toml`` (ADR 0048): the shipped registry loads (tier-1 FRED series, the four index
levels, third-party and Stooq series personal), ids come from kind and key, and every rule
names the entry."""

from typing import Any

import pytest

from algotrade.config.site.macro import MacroSeries, MacroSettings
from algotrade.config.site.settings import load_macro
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.config.site.test_settings import site

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


def load(*series: dict[str, Any]) -> MacroSettings:
    return MacroSettings.from_document({"series": list(series)})


def test_the_shipped_registry() -> None:
    macro = MacroSettings.from_document(site("macro"))
    assert {"T10Y3M", "BAMLH0A0HYM2", "UNRATE", "NFCI", "RRPONTSYD"} <= macro.keys
    indices = {s.instrument_id: s.vendor_code for s in macro.series if s.kind == "index"}
    assert indices == {
        "IDX:SPX": "^SPX",
        "IDX:COMP": "NASDAQCOM",
        "IDX:VIX": "VIXCLS",
        "IDX:VIX3M": "VXVCLS",
    }
    personal = {s.key for s in macro.series if s.licence == "personal"}
    third_party = {"BAMLH0A0HYM2", "BAMLC0A0CM", "BAA10Y", "COMP", "VIX", "VIX3M"}
    assert personal == {*third_party, "SPX"}  # third-party series on FRED, and Stooq
    revised_late = {
        s.key: s.release_lag_days for s in macro.series if s.key in ("GDPNOW", "RECPROUSM156N")
    }
    assert min(revised_late.values()) >= 125  # a final value before ALFRED's first vintage
    assert all(s.terms for s in macro.series)
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
