"""etf-holdings second review: one global due list, rejected reads that can succeed, layout
changes that fail loudly."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.data.resolver import SymbolResolver
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.market.etf_holdings import (
    HARD,
    SOFT,
    Event,
    HoldingsSources,
    Previous,
    confirmed,
    failing_streak,
    fund_frame,
    hold_until,
    nightly_cap,
    plan_due,
    sanity_problem,
)
from algotrade_sources.framework.holdings import holdings_frame
from tests.apps.ingestion.tasks.market.test_etf_holdings import (
    DAY,
    holdings,
    ishares,
    nport,
    run,
    ssga,
    world,
)
from tests.apps.ingestion.tasks.market.test_etf_holdings_checks import LATER, Rows, xlk_file
from tests.helpers.stored_frames import holdings_rows, stamped


@dataclass(frozen=True)
class Fake:
    name: str
    cadence_days: int


STATE_STREET, ISHARES, N_PORT = Fake("ssga", 1), Fake("ishares", 1), Fake("nport", 90)
ISSUERS = [STATE_STREET, ISHARES, N_PORT]
UNIVERSE = {
    **{f"S{i:03d}": STATE_STREET for i in range(181)},
    **{f"I{i:03d}": ISHARES for i in range(480)},
    **{f"N{i:03d}": N_PORT for i in range(480)},
}


def simulate(
    cap: int, weekdays: int = 252
) -> tuple[dict[str, date], dict[str, int], dict[str, int]]:
    """Read ``cap`` funds a weekday for a year -> (first read, longest gap, reads) per fund."""
    read: dict[str, date] = {}
    first: dict[str, date] = {}
    gaps: dict[str, int] = {}
    reads = dict.fromkeys(UNIVERSE, 0)
    day, done = date(2026, 1, 5), 0
    while done < weekdays:
        if day.weekday() < 5:
            done += 1
            for fund in plan_due(UNIVERSE, ISSUERS, read, day, 7)[:cap]:
                if fund in read:
                    gaps[fund] = max(gaps.get(fund, 0), (day - read[fund]).days)
                first.setdefault(fund, day)
                read[fund] = day
                reads[fund] += 1
        day += timedelta(days=1)
    return first, gaps, reads


@pytest.mark.parametrize("cap", [100, 200])
def test_the_nightly_cap_never_starves_the_n_port_funds(cap: int) -> None:
    """Capping each issuer's list before merging read State Street and iShares first, every night,
    and never reached N-PORT (a year of due_keys simulated)."""
    first, _, reads = simulate(cap)
    n_port = [f for f in UNIVERSE if f.startswith("N")]
    assert set(first) == set(UNIVERSE)  # every fund was read
    assert all(reads[f] >= 3 for f in n_port)  # quarterly, about 4 a year
    assert max(first[f] for f in UNIVERSE) <= date(2026, 1, 5) + timedelta(days=21)


def test_two_hundred_a_night_reads_weekly_funds_every_week_or_so() -> None:
    _, gaps, reads = simulate(200)
    daily = [f for f in UNIVERSE if not f.startswith("N")]
    assert max(gaps[f] for f in daily) <= 8
    assert min(reads[f] for f in daily) >= 50
    assert max(gaps[f] for f in UNIVERSE if f.startswith("N")) <= 95


def test_the_list_is_new_funds_first_then_the_oldest_with_issuer_priority_on_ties() -> None:
    covered = {"S1": STATE_STREET, "I1": ISHARES, "N1": N_PORT, "I2": ISHARES, "S2": STATE_STREET}
    read = {"I2": date(2026, 1, 1), "S2": date(2026, 1, 3)}
    order = plan_due(covered, ISSUERS, read, date(2026, 2, 1), 7)
    assert order == ["S1", "I1", "N1", "I2", "S2"]  # new by issuer priority, then oldest first
    held = plan_due(covered, ISSUERS, read, date(2026, 2, 1), 7, hold={"S1": date(2026, 2, 3)})
    assert "S1" not in held and "I1" in held  # a rejected fund waits
    forced = plan_due(covered, ISSUERS, read, date(2026, 2, 1), 7, True, {"S1": date(2026, 2, 3)})
    assert "S1" in forced


def soft(as_of: date, count: int = 3, session: date | None = None) -> Event:
    return Event(session or as_of, SOFT, as_of, count)


def at(days: int) -> date:
    return DAY + timedelta(days=days)


def test_three_distinct_increasing_dates_with_agreeing_counts_confirm() -> None:
    stored = 12
    earlier = [soft(at(0), 3), soft(at(2), 3)]
    assert confirmed(earlier, soft(at(4), 3), stored)
    assert confirmed([soft(at(0), 10), soft(at(2), 11)], soft(at(4), 10), 100)  # within 10%
    assert not confirmed([], soft(at(0)), stored)
    assert not confirmed([soft(at(0))], soft(at(2)), stored)  # one earlier read is not enough
    assert not confirmed(earlier, soft(at(1)), stored)  # an older file does not count
    assert not confirmed([soft(at(0)), soft(at(0))], soft(at(2)), stored)  # a date repeated


def test_counts_that_disagree_do_not_confirm_however_many_reads() -> None:
    """12 positions stored, then 5, 1 and 3 were accepted: the counts are not 'consistent'."""
    assert not confirmed([soft(at(0), 5), soft(at(2), 1)], soft(at(4), 3), 12)
    assert not confirmed([soft(at(0), 3), soft(at(2), 3)], soft(at(4), 5), 12)
    assert not confirmed([soft(at(0), 3), soft(at(2), 3)], soft(at(4), 12), 12)  # not below stored


def test_a_date_repeated_is_one_reading_unless_it_holds_for_three_run_days() -> None:
    """Oct 8, 9, 9 is two distinct dates, not three. A monthly file keeps one as-of date for
    weeks: the same date and count on three different run days is accepted."""
    assert not confirmed(
        [soft(at(0), 3, at(8)), soft(at(1), 3, at(10))], soft(at(1), 3, at(12)), 12
    )
    monthly = [soft(at(0), 3, at(8)), soft(at(0), 3, at(10))]
    assert confirmed(monthly, soft(at(0), 3, at(14)), 12)
    assert not confirmed(monthly, soft(at(0), 3, at(10)), 12)  # the same run day twice
    assert not confirmed(monthly, soft(at(0), 4, at(14)), 12)  # a different count


def test_anything_else_in_between_starts_the_count_over() -> None:
    hard = Event(at(3), HARD, at(3), 3)
    gone = Event(at(3), "missing")
    broke = Event(at(3), "error")
    for between in (hard, gone, broke):
        assert not confirmed([soft(at(0)), between], soft(at(4)), 12)
        assert not confirmed([soft(at(0)), soft(at(2)), between], soft(at(4)), 12)


def test_a_failure_holds_a_fund_back_longer_each_time_in_a_row() -> None:
    def error(day: int) -> Event:
        return Event(at(day), "error")

    assert hold_until([], STATE_STREET) is None
    assert hold_until([error(0)], STATE_STREET) == at(1)  # a failed read: tomorrow again
    assert hold_until([error(0), error(1)], STATE_STREET) == at(3)  # then 2, 4, 8 ... days
    assert hold_until([error(0), error(1), error(3)], STATE_STREET) == at(7)
    many = [error(i) for i in range(12)]
    assert hold_until(many, STATE_STREET) == at(11 + 30)  # capped at a month
    assert hold_until([soft(at(0))], STATE_STREET) == at(2)  # a rejection: 2 days
    assert hold_until([soft(at(0)), Event(at(2), HARD, at(2), 3)], STATE_STREET) == at(6)
    assert hold_until([error(0)], N_PORT) == at(30)  # a quarterly source: 30 from the first
    assert hold_until([error(0), error(30)], N_PORT) == at(60)
    assert hold_until([error(0), Event(at(1), "missing")], STATE_STREET) is None  # a missing file


def test_a_failed_fund_goes_after_healthy_ones_and_an_issuer_keeps_its_share() -> None:
    covered = {"S1": STATE_STREET, "I1": ISHARES, "I2": ISHARES, "N1": N_PORT}
    order = plan_due(covered, ISSUERS, {}, date(2026, 2, 1), 7, failing={"I1", "S1"})
    assert order == ["I2", "N1", "S1", "I1"]  # healthy first, then those that failed last time
    due = [f"I{i:03d}" for i in range(300)] + ["S001", "S002", "N001", "N002"]
    covered = {f: ISHARES if f.startswith("I") else STATE_STREET for f in due}
    covered |= {"N001": N_PORT, "N002": N_PORT}
    tonight = nightly_cap(due, covered, 20)  # 20% of 20 = 4 slots each; State Street has 2 due
    assert len(tonight) == 20
    assert {"S001", "S002", "N001", "N002"} <= set(tonight)
    assert sum(1 for f in tonight if f.startswith("I")) == 16
    assert nightly_cap(due, covered, None) == due and nightly_cap(due, covered, 0) == []


def simulate_with_a_broken_issuer(
    broken: str, count: int, cap: int = 200, weekdays: int = 252
) -> tuple[dict[str, int], dict[str, int], int]:
    """A year of nights with ``count`` funds of issuer ``broken`` failing every read ->
    (longest gap, reads) of the healthy funds and the number of failed attempts."""
    bad = {f for f in UNIVERSE if f.startswith(broken)}
    bad = set(sorted(bad)[:count])
    read: dict[str, date] = {}
    events: dict[str, list[Event]] = {}
    gaps: dict[str, int] = {}
    reads = dict.fromkeys(UNIVERSE, 0)
    attempts, day, done = 0, date(2026, 1, 5), 0
    while done < weekdays:
        if day.weekday() < 5:
            done += 1
            hold = {
                f: until
                for f, past in events.items()
                if (until := hold_until(past, UNIVERSE[f])) is not None
            }
            failing = {f for f, past in events.items() if failing_streak(past)}
            due = plan_due(UNIVERSE, ISSUERS, read, day, 7, hold=hold, failing=failing)
            for fund in nightly_cap(due, UNIVERSE, cap):
                if fund in bad:
                    events.setdefault(fund, []).append(Event(day, "error"))
                    attempts += 1
                    continue
                if fund in read:
                    gaps[fund] = max(gaps.get(fund, 0), (day - read[fund]).days)
                read[fund] = day
                events.pop(fund, None)
                reads[fund] += 1
        day += timedelta(days=1)
    return gaps, reads, attempts


@pytest.mark.parametrize(("broken", "count"), [("I", 480), ("S", 181), ("N", 480)])
def test_one_issuer_failing_for_a_year_does_not_starve_the_others(broken: str, count: int) -> None:
    """If iShares answers 403 (or changes its layout) all 480 of its funds were 'never read',
    headed the list every night and took all 200 slots: State Street was not read for 275 days
    and N-PORT about once a year. Failed funds now back off and sort after healthy ones."""
    gaps, reads, attempts = simulate_with_a_broken_issuer(broken, count)
    healthy = [f for f in UNIVERSE if not f.startswith(broken)]
    daily = [f for f in healthy if not f.startswith("N")]
    assert not daily or max(gaps[f] for f in daily) <= 14
    assert all(reads[f] >= 3 for f in healthy if f.startswith("N"))
    assert attempts <= count * 20  # ~16 tries a year per fund (monthly once backed off), not 252


def test_a_hundred_and_twenty_lasting_errors_cost_the_healthy_funds_almost_nothing() -> None:
    gaps, _, _ = simulate_with_a_broken_issuer("I", 120)
    healthy = [f for f in UNIVERSE if f not in {f"I{i:03d}" for i in range(120)}]
    daily = [f for f in healthy if not f.startswith("N")]
    assert max(gaps[f] for f in daily) <= 10  # was 19 days at 120 and 69 at 180


def cut(rows: Rows) -> Rows:
    header = next(i for i, r in enumerate(rows) if r[0] == "Name")
    return [*rows[: header + 4], rows[-1]]  # three holdings and the disclaimer


def dated(rows: Rows, as_of: str) -> Rows:
    return [
        tuple(v.replace("01-Oct-2026", as_of) if isinstance(v, str) else v for v in r) for r in rows
    ]


def reread(writer: Any, sources: HoldingsSources, day: date, **kwargs: Any) -> Any:
    return run(writer, sources, day, **kwargs)


def cut_on(as_of: str) -> bytes:
    return xlk_file(lambda rows: dated(cut(rows), as_of))


def sources_with(files: dict[str, bytes]) -> HoldingsSources:
    return HoldingsSources([ssga(files=files), ishares(), nport()], 7, 100, "optionable", False)


def test_a_real_rebalance_wins_after_three_consistent_reads() -> None:
    """XLK goes from 12 positions to 3: rejected twice (2 days, then 4 days between reads),
    accepted on the third, so the fund is not PARTIAL forever."""
    writer, base = world()
    run(writer, base)
    assert len(holdings(writer, "XLK")) == 12
    outcomes = []
    for offset, as_of in ((8, "08-Oct-2026"), (10, "10-Oct-2026"), (14, "14-Oct-2026")):
        day = DAY + timedelta(days=offset)
        record = reread(writer, sources_with({"xlk.xlsx": cut_on(as_of)}), day)
        outcomes.append(record.items["XLK"])
    assert outcomes[0].startswith("FAILED: 3 positions, was 12") and "soft" in outcomes[0]
    assert outcomes[1].startswith("FAILED: 3 positions, was 12")
    assert outcomes[2].startswith("OK: 3 lines") and "confirmed" in outcomes[2]
    assert len(holdings(writer, "XLK", DAY + timedelta(days=14))) == 3


def test_a_monthly_file_that_keeps_its_date_is_accepted_on_the_third_run_day() -> None:
    writer, base = world()
    run(writer, base)
    same_date = {"xlk.xlsx": cut_on("01-Oct-2026")}  # not older than the stored read
    results = [
        reread(writer, sources_with(same_date), DAY + timedelta(days=offset)).items["XLK"]
        for offset in (8, 10, 14)
    ]
    assert results[0].startswith("FAILED: 3 positions") and results[1].startswith("FAILED")
    assert results[2].startswith("OK: 3 lines")


def test_a_hard_rejection_in_between_resets_the_confirmation() -> None:
    writer, base = world()
    run(writer, base)
    older = {"xlk.xlsx": xlk_file(lambda rows: dated(cut(rows), "24-Sep-2026"))}
    steps = [(8, "08-Oct-2026"), (10, "10-Oct-2026"), (14, None), (22, "22-Oct-2026")]
    outcomes = []
    for offset, as_of in steps:
        files = older if as_of is None else {"xlk.xlsx": cut_on(as_of)}
        record = reread(writer, sources_with(files), DAY + timedelta(days=offset))
        outcomes.append(record.items["XLK"])
    assert "older than" in outcomes[2] and "hard" in outcomes[2]
    assert outcomes[3].startswith("FAILED: 3 positions")  # starts over: not accepted


def test_a_rejected_fund_waits_longer_each_time_it_is_rejected() -> None:
    writer, base = world()
    run(writer, base)
    files = {"xlk.xlsx": cut_on("08-Oct-2026")}
    seen = {}
    for offset in range(8, 16):
        record = reread(writer, sources_with(files), DAY + timedelta(days=offset))
        seen[offset] = "XLK" in record.items
    assert [o for o, tried in seen.items() if tried] == [8, 10, 14]  # waits 2, then 4 days


def test_a_failed_read_is_held_back_and_backs_off_like_a_rejection() -> None:
    def rename(rows: Rows) -> Rows:
        return [tuple("Wt" if v == "Weight" else v for v in r) for r in rows]

    writer, base = world()
    run(writer, base)
    files = {"xlk.xlsx": xlk_file(rename)}
    tried = []
    for offset in range(8, 18):
        record = reread(writer, sources_with(files), DAY + timedelta(days=offset))
        if "XLK" in record.items:
            tried.append(offset)
            assert record.items["XLK"].startswith("FETCH_ERROR")
            assert record.stats["fund_events"]["XLK"]["kind"] == "error"
    assert tried == [8, 9, 11, 15]  # 1, 2, 4 days between failed reads


def test_an_older_file_is_never_accepted_however_often_it_repeats() -> None:
    writer, base = world()
    run(writer, base)
    for offset in (8, 10, 14, 22):
        files = {"xlk.xlsx": xlk_file(lambda rows: dated(rows, "24-Sep-2026"))}
        record = reread(writer, sources_with(files), DAY + timedelta(days=offset))
        assert record.items["XLK"].startswith("FAILED: as of 2026-09-24, older")
        assert "hard" in record.items["XLK"]
    assert set(holdings(writer, "XLK", DAY + timedelta(days=22))["as_of"]) == {date(2026, 10, 1)}


def test_force_accepts_what_it_reads_without_the_checks() -> None:
    writer, base = world()
    run(writer, base)
    forced = reread(
        writer, sources_with({"xlk.xlsx": cut_on("08-Oct-2026")}), LATER, force=True, only=("XLK",)
    )
    assert forced.items["XLK"].startswith("OK: 3 lines") and forced.status is RunStatus.COMPLETE
    assert len(holdings(writer, "XLK", LATER)) == 3


def test_a_changed_state_street_date_line_fails_loudly_and_keeps_the_rows() -> None:
    def no_date(rows: Rows) -> Rows:
        return [
            tuple("Holdings changed" if v == "Holdings:" else v for v in r)
            for r in dated(rows, "-")
        ]

    writer, base = world()
    run(writer, base)
    record = reread(writer, sources_with({"xlk.xlsx": xlk_file(no_date)}), LATER)
    assert (
        record.items["XLK"].startswith("FETCH_ERROR") and "date it is as of" in record.items["XLK"]
    )
    assert record.status is RunStatus.PARTIAL and len(holdings(writer, "XLK", LATER)) == 12


def test_a_blank_column_before_weight_does_not_hide_the_whole_table() -> None:
    """openpyxl rows keep the empty cell, so the position of Weight in the header and in each
    row must agree (dropping the empty header cell shifted every later column by one)."""

    def gap(rows: Rows) -> Rows:
        header = next(i for i, r in enumerate(rows) if r[0] == "Name")
        out = []
        for i, row in enumerate(rows):
            if i < header or i > len(rows) - 2:
                out.append(row)
            else:
                out.append((*row[:4], None, *row[4:]))  # an empty column before Weight
        return out

    writer, _ = world()
    record = reread(writer, sources_with({"xlk.xlsx": xlk_file(gap)}), DAY)
    assert record.items["XLK"].startswith("OK: 12 lines")
    assert holdings(writer, "XLK")["weight"].iloc[0] == pytest.approx(0.15470648)


# --- the file's own weights, the S&P 500 floor, CUSIP ids --------------------------------------


def lines(*weights: float) -> pd.DataFrame:
    return holdings_frame(
        {"holding_name": f"L{i}", "weight": w, "asset_class": "Equity", "us_listed": False}
        for i, w in enumerate(weights)
    )


def test_an_ishares_file_cut_short_fails_on_its_own_published_weights() -> None:
    """Market-value weights always add up to 100%, so a truncated file passes the sum check. The
    published column (sum 0.91 for 300 of 500 lines) does not."""
    whole = lines(0.5, 0.5)
    assert sanity_problem(whole, DAY, None, False, True, published=0.999) is None
    cut_short = sanity_problem(whole, DAY, None, False, True, published=0.91)
    assert cut_short is not None and "cut short" in cut_short.text and not cut_short.soft
    assert sanity_problem(whole, DAY, None, True, True, published=0.91) is None  # geared funds
    assert sanity_problem(whole, DAY, None, False, True, published=None) is None  # bond funds


def test_a_recycled_ticker_does_not_move_a_stored_cusip_to_another_company() -> None:
    """The map keeps the instrument written with the line: 'OLD' is today another company."""
    resolver = SymbolResolver(ids={"OLD": "EQ:NEW"}, symbols={"EQ:NEW": "OLD"})
    frame = holdings_frame(
        [{"holding_name": "Old Co", "weight": 1.0, "asset_class": "Equity", "us_listed": False}]
    ).assign(identifier="037833100", filed=None, holding_symbol=None, sector=None, shares=None)
    rows = fund_frame("EQ:F", "F", DAY, frame, 100, resolver, {"037833100": ("OLD", "EQ:OLD")})
    assert list(rows["holding_id"]) == ["EQ:OLD"] and list(rows["holding_symbol"]) == ["OLD"]


def test_previous_is_compared_on_positions_only_for_daily_files() -> None:
    few = lines(0.5, 0.5)
    quarterly = sanity_problem(few, DAY, Previous(DAY, 300), False, False, check_count=False)
    assert quarterly is None  # a new quarterly report may be a different size
    daily = sanity_problem(few, DAY, Previous(DAY, 300), False, False)
    assert daily is not None and daily.soft


def stored_by_state_street(writer: Any) -> None:
    """VTI's latest rows, read long ago from State Street's file (so it is due again)."""
    long_ago = DAY - timedelta(days=120)
    rows = holdings_rows(
        "EQ:VTI", date(2026, 10, 1), [("NVDA", "NVIDIA", 0.5), ("AAPL", "Apple", 0.5)]
    )
    stamped_rows = stamped(rows, long_ago, "r0", source="ssga_holdings")
    writer.write_table("holdings/etf", long_ago, "r0", stamped_rows)


def test_an_issuer_whose_fund_list_is_down_keeps_its_funds_off_the_next_issuer() -> None:
    """With State Street's list down tonight, a fund it published is covered by N-PORT, whose
    months-old report is hard-rejected as older than the stored rows, after a header crawl."""
    writer, _ = world()
    stored_by_state_street(writer)
    down = HoldingsSources([ssga(down=True), ishares(), nport()], 7, 100, "optionable", False)
    record = run(writer, down, LATER)
    assert "VTI" not in record.items  # not handed to N-PORT
    assert record.stats["skipped_directory_down"] == 1
    assert record.stats["directory_down"] == ["ssga_holdings"]
    assert record.status is RunStatus.PARTIAL
    assert set(holdings(writer, "VTI", LATER)["source"]) == {"ssga_holdings"}
    control, _ = world()
    stored_by_state_street(control)
    healthy = run(control, sources_with({}), LATER)  # list up: N-PORT is its issuer, as before
    assert healthy.stats["skipped_directory_down"] == 0
    assert healthy.items["VTI"].startswith("FAILED") and "older" in healthy.items["VTI"]


def test_a_foreign_domiciled_company_links_through_its_cins_in_n_port() -> None:
    """Linde prints G54950103 on State Street's line and on an N-PORT line without a ticker."""
    resolver = SymbolResolver(ids={"LIN": "EQ:LIN"}, symbols={"EQ:LIN": "LIN"})
    frame = holdings_frame(
        [{"holding_name": "Linde plc", "weight": 1.0, "asset_class": "Equity", "us_listed": False}]
    ).assign(identifier="G54950103", filed=None, holding_symbol=None, sector=None, shares=None)
    rows = fund_frame("EQ:F", "F", DAY, frame, 100, resolver, {"G54950103": ("LIN", "EQ:LIN")})
    assert list(rows["holding_id"]) == ["EQ:LIN"] and list(rows["holding_symbol"]) == ["LIN"]
