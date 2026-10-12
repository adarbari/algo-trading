"""``rank``: the score is the sum over distinct users of exp(-age/60) from each user's latest
request, times the feasibility weight; one count per (user, key, day); ties break on the raw
count, then recency, then the name; the backlog's keys and aliases decide what is one feature and
an unknown slug is unmapped (ADR 0066 amendment)."""

import math
from datetime import date, timedelta

from algotrade.config.site.drafting.backlog import FeatureBacklogSettings
from algotrade.services.feedback.ranking import UNMAPPED, RequestRow, rank

TODAY = date(2026, 10, 11)
BACKLOG = FeatureBacklogSettings.from_document(
    {
        "item": [
            {
                "key": "fcf_yield",
                "description": "FCF over price",
                "feasibility": "NEEDS_SOURCE",
                "aliases": ["free_cash_flow_yield"],
            },
            {
                "key": "support_history",
                "description": "Support band",
                "feasibility": "ROLLUP_FROM_STORED",
            },
            {
                "key": "old_idea",
                "description": "Dropped",
                "feasibility": "UNCLEAR",
                "status": "WONT_DO",
            },
        ]
    }
)


def ago(days: int) -> date:
    return TODAY - timedelta(days=days)


def row(user: str, ref: str, days: int, feasibility: str = "UNCLEAR") -> RequestRow:
    return RequestRow(user, ref, ago(days), feasibility)


def test_the_score_decays_with_the_age_of_the_latest_request_and_weighs_feasibility() -> None:
    ranked = rank([row("a", "support_history", 60)], BACKLOG, TODAY)
    assert ranked[0].score == math.exp(-1) * 1.0
    needs = rank([row("a", "fcf_yield", 0)], BACKLOG, TODAY)
    assert needs[0].score == 0.5  # NEEDS_SOURCE, taken from the backlog, not the row
    unclear = rank([row("a", "old_idea", 0)], BACKLOG, TODAY)
    assert unclear[0].score == 0.25


def test_a_user_counts_once_from_their_latest_request() -> None:
    rows = [row("a", "support_history", 120), row("a", "support_history", 10)]
    top = rank(rows, BACKLOG, TODAY)[0]
    assert top.users == 1 and top.requests == 2
    assert top.score == math.exp(-10 / 60)
    assert top.last_seen == ago(10)


def test_distinct_users_add_up() -> None:
    rows = [row("a", "support_history", 0), row("b", "support_history", 30)]
    top = rank(rows, BACKLOG, TODAY)[0]
    assert top.users == 2 and top.score == 1 + math.exp(-30 / 60)


def test_one_count_per_user_key_and_day_even_through_an_alias() -> None:
    rows = [
        row("a", "fcf_yield", 3),
        row("a", "fcf_yield", 3),
        row("a", "free_cash_flow_yield", 3),  # the alias: the same feature, the same day
        row("a", "fcf_yield", 4),
    ]
    top = rank(rows, BACKLOG, TODAY)[0]
    assert (top.ref, top.users, top.requests) == ("fcf_yield", 1, 2)


def test_a_slug_the_backlog_now_maps_counts_under_the_key() -> None:
    rows = [row("a", "free_cash_flow_yield", 1), row("b", "fcf_yield", 1)]
    ranked = rank(rows, BACKLOG, TODAY)
    assert [(r.ref, r.users, r.unmapped) for r in ranked] == [("fcf_yield", 2, False)]


def test_an_unknown_slug_is_unmapped_and_keeps_the_feasibility_of_its_latest_row() -> None:
    rows = [row("a", "gamma_squeeze", 9, "NEEDS_SOURCE"), row("a", "gamma_squeeze", 2, "UNCLEAR")]
    top = rank(rows, BACKLOG, TODAY)[0]
    assert top.unmapped and top.status == UNMAPPED and top.feasibility == "UNCLEAR"
    assert top.description == ""
    odd = rank([row("a", "x", 0, "WHATEVER")], BACKLOG, TODAY)[0]
    assert odd.feasibility == "UNCLEAR"


def test_status_and_promotion_come_from_the_backlog() -> None:
    ranked = {
        r.ref: r for r in rank([row("a", "old_idea", 0), row("a", "fcf_yield", 0)], BACKLOG, TODAY)
    }
    assert ranked["old_idea"].status == "WONT_DO" and ranked["fcf_yield"].status == "OPEN"
    assert not ranked["old_idea"].unmapped


def test_ties_break_on_the_raw_count_then_recency_then_the_name() -> None:
    # two users each: the same score for both keys (same ages, same weight), more asks wins
    same = [
        row("a", "support_history", 5), row("b", "support_history", 5),
        row("a", "support_history", 40),  # a second day of a: a larger raw count, same score
    ]  # fmt: skip
    other = [
        row("c", "support_history_2", 5, "ROLLUP_FROM_STORED"),
        row("d", "support_history_2", 5, "ROLLUP_FROM_STORED"),
    ]
    ranked = rank(same + other, BACKLOG, TODAY)
    assert [r.ref for r in ranked] == ["support_history", "support_history_2"]
    assert ranked[0].score == ranked[1].score and ranked[0].requests == 3 > ranked[1].requests
    # equal everything but recency of the whole ask, then the name
    a = rank([row("a", "zz", 0, "NEEDS_SOURCE"), row("b", "aa", 0, "NEEDS_SOURCE")], BACKLOG, TODAY)
    assert [r.ref for r in a] == ["aa", "zz"]


def test_no_rows_no_ranking_and_a_future_date_counts_as_today() -> None:
    assert rank([], BACKLOG, TODAY) == ()
    future = rank([RequestRow("a", "support_history", ago(-3))], BACKLOG, TODAY)[0]
    assert future.score == 1.0
