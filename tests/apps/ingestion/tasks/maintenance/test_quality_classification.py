"""The acceptance check ``reference_classification`` (ADR 0045): FAIL when the vendor's
security types and our name rules disagree on more ACTIVE rows than ``max_type_disagreement``."""

from datetime import date

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.quality import check_reference_classification
from tests.helpers.stored_frames import stamped

D = date(2026, 10, 2)
OPERATING = ("Acme Corp. - Common Stock", "COMMON_STOCK", "vendor")
PREFERRED = ("Adamas Trust, Inc. - Series F Preferred Stock", "PREFERRED", "name_over_vendor")
CEF = ("Pimco Income Opportunity Fund", "CEF", "vendor")  # the vendor's type stands


def reader_with(rows: list[tuple[str, str, str]]) -> StoreReader:
    frame = pd.DataFrame(
        [
            {
                "instrument_id": f"EQ:S{i}",
                "symbol": f"S{i}",
                "name": name,
                "is_etf": False,
                "asset_class": "EQUITY",
                "multiplier": 1.0,
                "status": "ACTIVE",
                "security_type": kind,
                "security_type_source": source,
            }
            for i, (name, kind, source) in enumerate(rows)
        ]
    )
    backend = MemoryBackend()
    StoreWriter(backend).write_table("instruments/reference", D, "r", stamped(frame, D, "r"))
    return StoreReader(backend)


def check(rows: list[tuple[str, str, str]], **quality: float) -> tuple[str, dict[str, int]]:
    settings = SourcesSettings.from_document({"quality": quality})
    [result] = check_reference_classification(reader_with(rows), D, settings)
    return result.status, result.data


def test_few_disagreements_pass() -> None:
    status, data = check([OPERATING] * 95 + [PREFERRED] * 2 + [CEF] * 3)
    assert status == "PASS"
    assert (data["name_over_vendor"], data["disagreements"]) == (2, 5)


def test_too_many_disagreements_fail() -> None:
    assert check([OPERATING] * 80 + [PREFERRED] * 20)[0] == "FAIL"  # 20% > 10%
    assert check([OPERATING] * 90 + [CEF] * 10, max_type_disagreement=0.05)[0] == "FAIL"


def test_a_vendor_type_that_the_name_rules_agree_with_is_no_disagreement() -> None:
    agreed = ("Acme Corp. Warrants", "WARRANT", "vendor")
    assert check([OPERATING] * 9 + [agreed])[1]["disagreements"] == 0


def test_no_reference_snapshot_fails() -> None:
    [result] = check_reference_classification(
        StoreReader(MemoryBackend()), D, SourcesSettings.from_document({})
    )
    assert result.status == "FAIL"
