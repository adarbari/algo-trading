"""Coverage acceptance (ADR 0043): per feature and tier, the share of the names it applies to
that have a value; applicability, drops, a stored row counting for earnings, a missing value
never counted as zero, and the limits' severity."""

from dataclasses import replace
from datetime import date, timedelta

from algotrade.config.site.coverage import CoverageRule
from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.coverage import check_coverage
from tests.helpers.stored_frames import stamped

D = date(2026, 10, 2)
BEFORE = D - timedelta(days=1)
PRICES = "rollups/instrument/price_stats@v2"
IV30 = "rollups/instrument/iv30@v1"
EARNINGS = "rollups/instrument/earnings@v1"

# (symbol, security type, optionable, in the S&P 500)
NAMES = [
    ("C1", "COMMON_STOCK", True, True),
    ("C2", "COMMON_STOCK", True, True),
    ("R1", "COMMON_STOCK", True, False),
    ("R2", "COMMON_STOCK", True, False),
    ("N1", "COMMON_STOCK", False, False),  # not optionable: no iv30 expected
    ("E1", "ETF", True, False),  # an ETF: no earnings expected
]


def rules(*specs: CoverageRule) -> SourcesSettings:
    return replace(SourcesSettings(), coverage=tuple(specs))


def store() -> tuple[StoreWriter, StoreReader]:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    ref = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "EQ", "multiplier": 1.0,
         "security_type": t, "status": "ACTIVE", "optionable": o, "in_sp500": m}
        for s, t, o, m in NAMES
    ]  # fmt: skip
    uni = [
        {k: r[k] for k in ("instrument_id", "symbol", "security_type", "optionable", "status")}
        | {"universe_version": "v1"}
        for r in ref
    ]
    for day in (BEFORE, D):
        writer.write_table("instruments/reference", day, "ref", stamped(ref, day, "ref"))
        writer.write_table("universe", day, "uni", stamped(uni, day, "uni"))
    return writer, StoreReader(backend)


def put(writer: StoreWriter, table: str, day: date, rows: dict[str, dict[str, object]]) -> None:
    frame = [{"instrument_id": f"EQ:{s}", **cols} for s, cols in rows.items()]
    writer.write_table(table, day, "r", stamped(frame, day, "r"))


def only(checks: list, feature: str):  # type: ignore[no-untyped-def]
    return next(c for c in checks if c.name == f"coverage_{feature}")


def cell(check, tier: str) -> dict:  # type: ignore[no-untyped-def]
    return next(c for c in check.data["cells"] if c["tier"] == tier)


CLOSE = CoverageRule("price_stats.close", core_min=0.9, rest_min=0.9)


def test_coverage_is_counted_by_tier() -> None:
    writer, reader = store()
    closes = {s: {"close": 10.0} for s in ("C1", "R1", "R2", "N1", "E1")}  # C2 has none
    put(writer, PRICES, D, closes)
    check = only(check_coverage(reader, D, rules(CLOSE)), "price_stats.close")
    core, rest = cell(check, "core"), cell(check, "rest")
    assert (core["covered"], core["applicable"], core["missing"]) == (1, 2, ["C2"])
    assert (rest["covered"], rest["applicable"]) == (4, 4)
    assert check.status == "WARN" and "core 50.0%" in check.detail


def test_a_name_the_feature_does_not_apply_to_is_not_counted() -> None:
    writer, reader = store()
    put(writer, IV30, D, {s: {"iv30": 0.3, "iv30_status": "OK"} for s in ("C1", "C2", "R1")})
    check = only(check_coverage(reader, D, rules(CoverageRule("iv30.iv30", 0.9, 0.9))), "iv30.iv30")
    # N1 is not optionable: out of the population; R2 and E1 (optionable) are the gaps
    assert cell(check, "rest")["applicable"] == 3
    assert sorted(cell(check, "rest")["missing"]) == ["E1", "R2"]
    assert cell(check, "core")["covered"] == 2


def test_an_illiquid_null_is_not_a_gap_but_another_null_is() -> None:
    writer, reader = store()
    rows = {
        "C1": {"iv30": 0.3, "iv30_status": "OK"},
        "C2": {"iv30": None, "iv30_status": "WIDE_SPREADS"},
        "R1": {"iv30": None, "iv30_status": "IV_FAILED"},
    }
    put(writer, IV30, D, rows)
    check = only(check_coverage(reader, D, rules(CoverageRule("iv30.iv30", 0.9, 0.9))), "iv30.iv30")
    assert cell(check, "core")["covered"] == 2
    assert "R1" in cell(check, "rest")["missing"]


def test_earnings_counts_a_stored_row_even_without_a_next_date() -> None:
    writer, reader = store()
    rows = {s: {"next_earnings_date": None} for s in ("C1", "C2", "R1")}  # just reported
    put(writer, EARNINGS, D, rows)
    rule = CoverageRule("earnings.next_earnings_date", 1.0, 0.5, covered_by="row")
    check = only(check_coverage(reader, D, rules(rule)), "earnings.next_earnings_date")
    assert cell(check, "core")["covered"] == 2  # the null date is not a gap
    assert cell(check, "rest")["missing"] == [
        "N1",
        "R2",
    ]  # no row at all is; E1 (ETF) is not expected
    by_value = replace(rule, covered_by="value")
    again = only(check_coverage(reader, D, rules(by_value)), "earnings.next_earnings_date")
    assert cell(again, "core")["covered"] == 0


def test_a_missing_value_or_table_is_missing_never_zero() -> None:
    writer, reader = store()
    check = only(check_coverage(reader, D, rules(CLOSE)), "price_stats.close")  # no partition
    assert cell(check, "core")["share"] == 0.0 and cell(check, "core")["covered"] == 0
    put(writer, PRICES, D, {"C1": {"close": 0.0}, "C2": {"close": None}})
    check = only(check_coverage(reader, D, rules(CLOSE)), "price_stats.close")
    assert cell(check, "core")["covered"] == 1  # a stored 0.0 is a value, a null is not


def test_a_drop_against_the_previous_session_is_flagged() -> None:
    writer, reader = store()
    names = ("C1", "C2", "R1", "R2", "N1", "E1")
    put(writer, PRICES, BEFORE, {s: {"close": 1.0} for s in names})
    put(writer, PRICES, D, {s: {"close": 1.0} for s in names if s != "R2"})
    rule = CoverageRule("price_stats.close", core_min=0.5, rest_min=0.5, max_drop=0.1)
    check = only(check_coverage(reader, D, rules(rule)), "price_stats.close")
    rest = cell(check, "rest")
    assert (rest["share"], rest["previous"], rest["ok"]) == (0.75, 1.0, False)
    assert check.status == "WARN" and "fell 25.0%" in check.detail
    assert check.data["previous_session"] == BEFORE.isoformat()
    steady = replace(rule, max_drop=0.3)
    assert only(check_coverage(reader, D, rules(steady)), "price_stats.close").status == "PASS"


def test_the_rule_level_decides_whether_a_breach_fails() -> None:
    writer, reader = store()
    put(writer, PRICES, D, {"C1": {"close": 1.0}, "R1": {"close": 1.0}})
    warn = CoverageRule("price_stats.close", core_min=0.9, rest_min=0.9, level="WARN")
    fail_core = replace(warn, core_level="FAIL")
    assert only(check_coverage(reader, D, rules(warn)), "price_stats.close").status == "WARN"
    assert only(check_coverage(reader, D, rules(fail_core)), "price_stats.close").status == "FAIL"
    # a breach in the rest tier only is the rule's level, not the core one
    writer2, reader2 = store()
    put(writer2, PRICES, D, {s: {"close": 1.0} for s in ("C1", "C2", "R1")})
    assert only(check_coverage(reader2, D, rules(fail_core)), "price_stats.close").status == "WARN"


def test_no_universe_fails_loudly() -> None:
    checks = check_coverage(StoreReader(MemoryBackend()), D, rules(CLOSE))
    assert [(c.name, c.status) for c in checks] == [("coverage", "FAIL")]


def test_the_previous_session_is_found_per_feature_table() -> None:
    writer, reader = store()
    names = ("C1", "C2", "R1", "R2", "N1", "E1")
    put(writer, PRICES, BEFORE, {s: {"close": 1.0} for s in names})
    put(writer, PRICES, D, {s: {"close": 1.0} for s in names})
    put(writer, IV30, D, {s: {"iv30": 0.3, "iv30_status": "OK"} for s in ("C1", "C2", "R1", "R2")})
    iv = CoverageRule("iv30.iv30", 0.5, 0.5, max_drop=0.1)
    checks = check_coverage(reader, D, rules(CLOSE, iv))
    # iv30 has no earlier partition (prices do): its drop is skipped, not read as 0 -> fine
    got = only(checks, "iv30.iv30")
    assert got.status == "PASS" and "drop not checked" in got.detail
    assert got.data["previous_session"] == ""
    assert only(checks, "price_stats.close").data["previous_session"] == BEFORE.isoformat()
    put(
        writer,
        IV30,
        BEFORE,
        {s: {"iv30": 0.3, "iv30_status": "OK"} for s in ("C1", "C2", "R1", "R2", "E1")},
    )
    again = only(check_coverage(reader, D, rules(iv)), "iv30.iv30")
    assert again.data["previous_session"] == BEFORE.isoformat()
    assert cell(again, "rest")["previous"] == 1.0


OVERDUE = CoverageRule(
    "earnings.last_earnings_date",
    core_min=1.0,
    rest_min=0.0,
    max_drop=1.0,
    covered_by="recent",
    max_age_days=100,
    or_value="next_earnings_date",
)


def test_an_overdue_core_company_is_flagged_with_its_last_date() -> None:
    # FDX on 2026-10-02: last report 2026-06-23 (101 days), no next date (dropped by Nasdaq)
    writer, reader = store()
    rows = {
        "C1": {"last_earnings_date": date(2026, 6, 23), "next_earnings_date": None},
        "C2": {"last_earnings_date": date(2026, 6, 24), "next_earnings_date": None},  # 100 days
        "R1": {"last_earnings_date": date(2026, 5, 1), "next_earnings_date": None},
        "R2": {"last_earnings_date": date(2026, 5, 1), "next_earnings_date": date(2026, 10, 9)},
        "E1": {"last_earnings_date": date(2026, 1, 1), "next_earnings_date": None},  # an ETF
    }
    put(writer, EARNINGS, D, rows)
    check = only(check_coverage(reader, D, rules(OVERDUE)), "earnings.last_earnings_date")
    core, rest = cell(check, "core"), cell(check, "rest")
    assert (core["covered"], core["applicable"], core["ok"]) == (1, 2, False)
    assert core["missing"] == ["C1 (last 2026-06-23)"]
    # rest is measured, never flagged; N1 (no row) is the row rule's gap; E1 is not expected
    assert (rest["covered"], rest["applicable"], rest["ok"]) == (1, 2, True)
    assert check.status == "WARN" and "overdue: over 100 days" in check.detail


def test_a_next_date_or_a_recent_report_is_not_overdue() -> None:
    writer, reader = store()
    rows = {
        "C1": {"last_earnings_date": date(2026, 9, 1), "next_earnings_date": None},
        "C2": {"last_earnings_date": None, "next_earnings_date": date(2026, 10, 20)},
    }
    put(writer, EARNINGS, D, rows)
    check = only(check_coverage(reader, D, rules(OVERDUE)), "earnings.last_earnings_date")
    assert check.status == "PASS" and cell(check, "core")["covered"] == 2


def test_overdue_grades_only_names_with_a_row() -> None:
    writer, reader = store()
    check = only(check_coverage(reader, D, rules(OVERDUE)), "earnings.last_earnings_date")
    assert check.status == "PASS"  # no partition: the row rule reports that gap, not this one
    assert cell(check, "core")["share"] is None
    put(writer, EARNINGS, D, {"C1": {"last_earnings_date": None, "next_earnings_date": None}})
    check = only(check_coverage(reader, D, rules(OVERDUE)), "earnings.last_earnings_date")
    assert cell(check, "core")["missing"] == ["C1"]  # a row with neither date is overdue too
