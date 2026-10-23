"""``yahoo_schedule`` (ADR 0080 amendment 2026-10-23c): the rolling baseline asks every name once
a cycle with a flat nightly load, event pulls come first inside the ceiling, a fingerprint ignores
what moves without news, and the cool-off after a 429 doubles up to a cap."""

from datetime import date, timedelta

import pandas as pd

from algotrade_ingestion.tasks.analyst import yahoo_schedule as ys
from algotrade_sources.vendors.yahoo.analyst import parse_estimates, parse_recommendation

ANCHOR = date(2026, 10, 23)
RULES = ys.Rules(14, 45, ANCHOR, ceiling=400, baseline_cap=360, events=True)


def ids(n: int, prefix: str = "EQ:SYN") -> list[str]:
    return [f"{prefix}{i:05d}" for i in range(n)]


def simulate(
    names: list[str],
    days: int,
    rules: ys.Rules,
    standby: bool = False,
    skip: frozenset[int] = frozenset(),
) -> tuple[dict[str, list[int]], list[int]]:
    """Every name last answered on the anchor day; run ``days`` nights, feeding each night's asks
    back as the next night's history. -> (name -> days it was asked, asks a night)."""
    last: dict[str, date] = dict.fromkeys(names, ANCHOR)
    asked: dict[str, list[int]] = {n: [] for n in names}
    per_night: list[int] = []
    for offset in range(1, days + 1):
        if offset in skip:
            per_night.append(0)
            continue
        day = ANCHOR + timedelta(days=offset)
        pool = [ys.Candidate(n, n, standby, last[n]) for n in names]
        tonight = ys.plan(day, pool, rules)
        for symbol in tonight.take:
            last[symbol] = day
            asked[symbol].append(offset)
        per_night.append(len(tonight.take))
    return asked, per_night


def test_every_name_is_asked_once_a_cycle_and_the_nightly_load_is_flat() -> None:
    """Owner requirement: thousands of names all answered on the backfill day."""
    names = ids(4200)
    asked, per_night = simulate(names, 28, RULES)
    for offsets in asked.values():
        assert len(offsets) == 2  # once in days 1..14, once in 15..28
        assert 1 <= offsets[0] <= 14 and 15 <= offsets[1] <= 28
        assert offsets[1] - offsets[0] == 14
    mean = len(names) / 14
    assert all(abs(n - mean) <= 0.15 * mean for n in per_night)  # 300 +- 45
    assert max(per_night) <= RULES.ceiling


def test_the_standby_cycle_is_flat_too() -> None:
    names = ids(4500)
    rules = ys.Rules(14, 45, ANCHOR, 400, 360, True)
    asked, per_night = simulate(names, 90, rules, standby=True)
    for offsets in asked.values():
        assert len(offsets) == 2 and offsets[1] - offsets[0] == 45
    mean = len(names) / 45  # 100 a night
    assert all(abs(n - mean) <= 0.4 * mean for n in per_night)


def test_a_missed_night_is_caught_up_the_next_night() -> None:
    names = ids(3000)
    asked, per_night = simulate(names, 28, RULES, skip=frozenset({5}))
    for symbol, offsets in asked.items():
        assert len(offsets) == 2, symbol  # still once a cycle, never skipped
        assert offsets[0] <= 14
    assert per_night[4] == 0 and per_night[5] > per_night[0]  # the next night carries the extra
    assert max(per_night) <= RULES.ceiling


def test_a_new_name_keeps_its_slot_and_is_asked_at_once_when_never_asked() -> None:
    assert ys.slot("EQ:NEW", 14) == ys.slot("EQ:NEW", 14) and 0 <= ys.slot("EQ:NEW", 14) < 14
    day = ANCHOR + timedelta(days=3)
    got = ys.plan(day, [ys.Candidate("NEW", "EQ:NEW")], RULES)
    assert got.take == ["NEW"] and got.why["NEW"] == ys.BASELINE  # never asked: the stalest
    slot_day = next(
        ANCHOR + timedelta(days=d)
        for d in range(1, 15)
        if ys.on_slot("EQ:NEW", ANCHOR + timedelta(days=d), ANCHOR, 14)
    )
    again = ys.plan(slot_day, [ys.Candidate("NEW", "EQ:NEW", last_asked=ANCHOR)], RULES)
    assert again.take == ["NEW"]  # on its own day, whatever its history


def test_the_slot_hash_is_stable_across_processes() -> None:
    """sha256, never Python's per-process ``hash``: a fixed id has a fixed slot."""
    assert [ys.slot(f"EQ:{c}", 14) for c in "ABC"] == [ys.slot(f"EQ:{c}", 14) for c in "ABC"]
    assert ys.slot("EQ:BBG000B9XRY4", 14) == 6


def events(*args: object, **kw: object) -> ys.Plan:
    """``plan`` with the baseline's names left out of ``why``: only what an event asked for."""
    got = ys.plan(*args, **kw)  # type: ignore[arg-type]
    return ys.Plan(got.take, {k: v for k, v in got.why.items() if v != ys.BASELINE})


def report(
    symbol: str, last: date | None = None, nxt: date | None = None, **kw: object
) -> ys.Candidate:
    return ys.Candidate(symbol, f"EQ:{symbol}", last_report=last, next_report=nxt, **kw)  # type: ignore[arg-type]


def test_the_day_after_a_report_is_pulled_and_again_only_if_nothing_new() -> None:
    r = date(2026, 11, 3)
    asked = r - timedelta(days=5)  # the last pull, before the report
    day1 = r + timedelta(days=1)
    first = events(day1, [report("A", r, last_asked=asked)], RULES)
    assert first.take == ["A"] and first.why["A"] == ys.POST
    # pulled on day 1 and it showed new data (fingerprint changed that session): done
    assert (
        events(r + timedelta(days=4), [report("A", r, last_asked=day1, changed=day1)], RULES).why
        == {}
    )
    # pulled on day 1 and nothing new: a repeat three days later
    repeat = events(r + timedelta(days=4), [report("A", r, last_asked=day1, changed=asked)], RULES)
    assert repeat.why == {"A": ys.POST}
    # not a third time
    last = r + timedelta(days=4)
    assert "A" not in events(last + timedelta(days=1), [report("A", r, last_asked=last)], RULES).why
    # a pull before the report is not the day-after pull; two days after it is still caught up
    assert events(r, [report("A", r, last_asked=asked)], RULES).why == {}
    assert events(r + timedelta(days=3), [report("A", r, last_asked=asked)], RULES).why == {
        "A": ys.POST
    }
    assert events(r + timedelta(days=9), [report("A", r, last_asked=asked)], RULES).why == {}


def test_one_pre_report_pull_in_the_last_week() -> None:
    n = date(2026, 11, 10)
    old = n - timedelta(days=12)
    assert events(n - timedelta(days=4), [report("A", None, n, last_asked=old)], RULES).why == {}
    near = events(n - timedelta(days=3), [report("A", None, n, last_asked=old)], RULES)
    assert near.why == {"A": ys.PRE}
    done = report("A", None, n, last_asked=n - timedelta(days=5))  # already pulled in the window
    assert events(n - timedelta(days=2), [done], RULES).why == {}


def test_yahoos_date_is_the_fallback_and_a_past_date_is_unknown() -> None:
    n = date(2026, 11, 10)
    c = ys.Candidate("A", "EQ:A", last_asked=n - timedelta(days=14), yahoo_next=n)
    assert events(n - timedelta(days=2), [c], RULES).why == {"A": ys.PRE}
    stale = ys.Candidate(
        "A", "EQ:A", last_asked=n - timedelta(days=1), yahoo_next=n - timedelta(days=2)
    )
    assert ys.expected_report(stale, n) is None  # past, no report seen: baseline only
    ours = ys.Candidate(
        "A", "EQ:A", next_report=n + timedelta(days=2), yahoo_next=n + timedelta(days=9)
    )
    assert ys.expected_report(ours, n) == n + timedelta(days=2)  # ours first


def test_event_pulls_go_first_by_market_cap_and_the_baseline_yields_at_the_ceiling() -> None:
    r = date(2026, 11, 3)
    day = r + timedelta(days=1)
    reporters = [report(f"R{i}", r, last_asked=r - timedelta(days=9)) for i in range(5)]
    others = [
        ys.Candidate(f"B{i}", f"EQ:B{i}", last_asked=day - timedelta(days=15)) for i in range(5)
    ]
    rank = ["R3", "B0", "R1", "R4", "R0", "R2", "B1"]
    rules = ys.Rules(14, 45, ANCHOR, ceiling=7, baseline_cap=360, events=True)
    got = ys.plan(day, [*others, *reporters], rules, rank)
    assert got.take[:5] == ["R3", "R1", "R4", "R0", "R2"]  # events, largest cap first
    assert len(got.take) == 7 and all(got.why[s] == ys.BASELINE for s in got.take[5:])
    tight = ys.plan(day, [*others, *reporters], ys.Rules(14, 45, ANCHOR, 3, 360, True), rank)
    assert tight.take == ["R3", "R1", "R4"] and set(tight.why.values()) == {ys.POST}
    assert got.due_events == 5 and got.due_baseline == 5


def test_a_name_near_the_reader_staleness_goes_before_the_events() -> None:
    r = date(2026, 11, 3)
    day = r + timedelta(days=1)
    old = ys.Candidate("OLD", "EQ:OLD", last_asked=day - timedelta(days=ys.HARD_DAYS))
    news = report("NEWS", r, last_asked=r - timedelta(days=9))
    got = ys.plan(day, [news, old], ys.Rules(14, 45, ANCHOR, 1, 360, True), ["NEWS", "OLD"])
    assert got.take == ["OLD"] and got.why == {"OLD": ys.HARD}


def test_event_pulls_off_leaves_only_the_baseline() -> None:
    r = date(2026, 11, 3)
    off = ys.Rules(14, 45, ANCHOR, 400, 360, events=False)
    c = report("A", r, last_asked=r - timedelta(days=2))
    assert events(r + timedelta(days=1), [c], off).why == {}


def test_the_baseline_alone_serves_a_name_with_no_date() -> None:
    day = ANCHOR + timedelta(days=20)
    c = ys.Candidate("A", "EQ:A", last_asked=day - timedelta(days=14))
    assert ys.plan(day, [c], RULES).why == {"A": ys.BASELINE}


def test_the_baseline_cap_and_ceiling_are_never_exceeded() -> None:
    day = ANCHOR + timedelta(days=30)
    pool = [ys.Candidate(f"N{i}", f"EQ:N{i}") for i in range(1000)]  # never asked: all due
    assert len(ys.plan(day, pool, ys.Rules(14, 45, ANCHOR, 400, 360, True)).take) == 360
    assert len(ys.plan(day, pool, ys.Rules(14, 45, ANCHOR, 50, 360, True)).take) == 50


def test_stalest_first_then_largest_cap() -> None:
    day = ANCHOR + timedelta(days=30)
    pool = [
        ys.Candidate("FRESH", "EQ:F", last_asked=day - timedelta(days=15)),
        ys.Candidate("STALE", "EQ:S", last_asked=day - timedelta(days=17)),
        ys.Candidate("BIG", "EQ:B"),
        ys.Candidate("SMALL", "EQ:M"),
    ]
    got = ys.plan(day, pool, RULES, ["SMALL", "BIG", "STALE", "FRESH"])
    assert got.take == ["SMALL", "BIG", "STALE", "FRESH"]  # never asked first, by cap


def answer(estimate: float = 1.5, target: float = 20.0) -> dict[str, pd.DataFrame]:
    return {
        "price_target": pd.DataFrame(
            [{"symbol": "A", "target_high": 30.0, "target_low": 10.0, "target_consensus": target}]
        ),
        "estimates_annual": pd.DataFrame(
            [
                {
                    "symbol": "A",
                    "fiscal_date": pd.Timestamp("2026-12-31", tz="UTC"),
                    "eps_avg": estimate,
                    "num_analysts_eps": 7,
                }
            ]
        ),
        "recommendation": pd.DataFrame(
            [
                {
                    "symbol": "A",
                    "period": pd.Timestamp("2026-10-01"),
                    "strong_buy": 1,
                    "buy": 2,
                    "hold": 3,
                    "sell": 0,
                    "strong_sell": 0,
                }
            ]
        ),
    }


def test_the_fingerprint_is_stable_and_changes_with_the_numbers() -> None:
    assert ys.fingerprint(answer()) == ys.fingerprint(answer())  # a repeat is not new
    assert ys.fingerprint(answer()) != ys.fingerprint(answer(estimate=1.6))
    assert ys.fingerprint(answer()) != ys.fingerprint(answer(target=21.0))
    rolled = answer()
    rolled["recommendation"] = rolled["recommendation"].assign(period=pd.Timestamp("2026-11-01"))
    assert ys.fingerprint(rolled) == ys.fingerprint(answer())  # the month's roll is no news
    assert len(ys.fingerprint({})) == 8


def test_the_fingerprint_hashes_only_the_newest_month_of_the_recommendation() -> None:
    one = answer()
    several = answer()
    older = one["recommendation"].assign(period=pd.Timestamp("2026-07-01"), strong_buy=9)
    several["recommendation"] = pd.concat([one["recommendation"], older], ignore_index=True)
    assert ys.fingerprint(several) == ys.fingerprint(one)  # added months are no news
    moved = answer()
    moved["recommendation"] = one["recommendation"].assign(buy=3)
    assert ys.fingerprint(moved) != ys.fingerprint(one)  # the newest month's counts are


def test_the_epstrend_fields_and_bucket_roll_of_a_payload_are_ignored() -> None:
    def found(seven: float, month: str) -> dict:  # type: ignore[type-arg]
        trend = {
            "period": "0y",
            "endDate": "2026-12-31",
            "earningsEstimate": {"avg": 1.5, "numberOfAnalysts": 7, "earningsCurrency": "USD"},
            "revenueEstimate": {"avg": 100.0, "numberOfAnalysts": 5, "revenueCurrency": "USD"},
            "epsTrend": {"7daysAgo": seven, "30daysAgo": seven + 1},
        }
        return {
            "earningsTrend": {"trend": [trend]},
            "recommendationTrend": {"trend": [{"period": month, "buy": 2, "hold": 1}]},
        }

    def fp(f: dict, day: date) -> str:  # type: ignore[type-arg]
        return ys.fingerprint(
            {
                "estimates_annual": parse_estimates("A", f),
                "recommendation": parse_recommendation("A", f, day),
            }
        )

    assert fp(found(1.0, "0m"), date(2026, 10, 5)) == fp(found(1.4, "0m"), date(2026, 11, 5))


def test_the_status_carries_the_answer_and_keeps_its_label() -> None:
    calendar = pd.DataFrame(
        [{"symbol": "A", "next_report": date(2026, 11, 3), "last_action": date(2026, 10, 20)}]
    )
    status = ys.with_answer("OK", "ab12cd34", calendar)
    assert status == "OK: fp=ab12cd34 next=2026-11-03 act=2026-10-20"
    assert status.split(":", 1)[0] == "OK"
    assert ys.answer_of(status) == ys.Answer("ab12cd34", date(2026, 11, 3), date(2026, 10, 20))
    bare = ys.with_answer(
        "OK", "ab12cd34", pd.DataFrame([{"symbol": "A", "next_report": None, "last_action": None}])
    )
    assert bare == "OK: fp=ab12cd34" and ys.answer_of("OK") == ys.Answer()


def test_the_cooloff_doubles_per_night_in_a_row_up_to_a_cap() -> None:
    assert [ys.cooloff_nights(k) for k in (1, 2, 3, 8, 9, 20)] == [2, 4, 8, 256, 256, 256]
    assert ys.cooling(date(2026, 10, 30), date(2026, 10, 29))
    assert not ys.cooling(date(2026, 10, 30), date(2026, 10, 30)) and not ys.cooling(
        None, date(2026, 10, 1)
    )
