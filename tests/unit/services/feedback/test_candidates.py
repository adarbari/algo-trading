"""``candidates``: the sampling hygiene over fake finalised chains (ADR 0066): near-duplicates
removed, a per-user monthly cap, stratification by feature group, the coverage summary and the
holdings flags."""

import json
from datetime import UTC, datetime
from typing import Any

from algotrade.services.feedback.candidates import (
    candidate_cards,
    coverage,
    feature_group,
    grams,
    holding_flags,
    overlap,
    render,
)

RSI = "rollup.momentum@v1.rsi_14"
PE = "feature.pe_ratio"


def snap(field: str, op: str = "gt", value: object = 1) -> dict[str, Any]:
    return {"criteria": {"c1": {"field": field, "op": op, "value": value}}}


def chain(
    n: int, sentence: str, field: str = RSI, user: str = "u", day: int = 1, month: int = 10
) -> list[dict[str, Any]]:
    """A requested then finalised session ``n``."""
    ts = datetime(2026, month, day, 12, tzinfo=UTC)
    return [
        {"event_id": f"r{n}", "draft_session_id": f"s{n}", "user": user, "doc_id": f"d{n}",
         "event": "draft_requested", "ts": ts, "seq": 1, "sentence": sentence,
         "payload": json.dumps({"current_criteria": {"criteria": {}}})},
        {"event_id": f"f{n}", "draft_session_id": f"s{n}", "user": user, "doc_id": f"d{n}",
         "event": "screen_finalised", "ts": ts.replace(hour=13), "seq": None, "sentence": None,
         "payload": json.dumps({"saved_criteria": snap(field)})},
    ]  # fmt: skip


def test_feature_groups_and_overlap() -> None:
    assert feature_group(RSI) == "rollup.momentum@v1"
    assert feature_group(PE) == "feature" and feature_group("instrument.sector") == "instrument"
    assert overlap("Cheap on sales!", "cheap on sales") == 1.0
    assert overlap("cheap on sales", "cheap on sales, high margin") == 3 / 5
    assert overlap("", "x") == 0.0


def test_near_duplicate_sentences_keep_one_candidate() -> None:
    rows = chain(1, "stocks with rsi below 30") + chain(2, "Stocks with RSI below 30.", day=2)
    rows += chain(3, "cheap on sales with margins", field=PE)
    cards = candidate_cards(rows)
    assert len(cards) == 2
    assert {c["chain_id"] for c in cards} == {"f2", "f3"}  # the newer of the pair is kept


def test_a_user_has_at_most_n_candidates_a_month() -> None:
    rows = [r for n in range(1, 5) for r in chain(n, f"idea {n} alpha{n} beta{n}", day=n)]
    rows += chain(9, "other idea gamma delta", user="v", day=9)
    cards = candidate_cards(rows, per_user_month=2)
    assert sorted(c["user"] for c in cards) == ["u", "u", "v"]
    assert [c["chain_id"] for c in candidate_cards(rows, user="v")] == ["f9"]


def test_stratified_round_robin_by_feature_group() -> None:
    rows = [r for n in range(1, 4) for r in chain(n, f"momentum one{n} two{n}", day=n)]
    rows += chain(7, "valuation words here", field=PE, day=1)
    cards = candidate_cards(rows, limit=2)
    assert {c["groups"][0] for c in cards} == {"rollup.momentum@v1", "feature"}


def test_only_finalised_chains_with_readable_criteria_are_candidates() -> None:
    saved_only = [chain(1, "only saved")[0]]
    truncated = chain(2, "cut short")
    truncated[1]["payload"] = json.dumps({"saved_criteria": {"truncated": True}})
    assert candidate_cards(saved_only + truncated) == []


def test_coverage_counts_groups_and_operators_and_render_names_the_chain() -> None:
    cards = candidate_cards(chain(1, "rsi low") + chain(2, "cheap sales", field=PE))
    assert coverage(cards) == {
        "groups": {"feature": 1, "rollup.momentum@v1": 1},
        "intents": {"gt": 2},
    }
    text = "\n".join(render(cards, coverage(cards)))
    assert "chain f1" in text and "2 candidate(s)" in text


def test_holdings_flags_catch_share_counts_cashtags_and_tickers_not_jargon() -> None:
    assert holding_flags("rsi below 30 on etf names, pe under 20") == []
    assert "200 shares" in holding_flags("I hold 200 shares of it")
    assert "$AAPL" in holding_flags("like $AAPL")
    assert "NVDA" in holding_flags("something like NVDA 120 but cheaper")
    assert "NVDA 120" in holding_flags("something like NVDA 120 but cheaper")


def test_a_card_is_filed_under_the_rarest_of_its_groups() -> None:
    both = {"criteria": {"a": {"field": RSI, "op": "gt", "value": 1},
                         "b": {"field": PE, "op": "lt", "value": 2}}}  # fmt: skip
    rows = chain(1, "uno dos tres", day=1) + chain(2, "cuatro cinco seis", day=2)
    rows += chain(3, "siete ocho nueve", day=3)
    rows[-1]["payload"] = json.dumps({"saved_criteria": both})  # touches momentum and feature
    cards = candidate_cards(rows, limit=2)
    # momentum is in 3 cards, feature in 1: the two-group card is filed under feature, so the
    # round robin takes it first, then one momentum card
    assert cards[0]["chain_id"] == "f3" and len(cards) == 2


def test_a_truncated_read_drops_the_chain_at_its_edge() -> None:
    rows = chain(1, "oldest chain words", day=1) + chain(2, "newer chain words", day=5)
    assert {c["chain_id"] for c in candidate_cards(rows, truncated=True)} == {"f2"}
    assert len(candidate_cards(rows)) == 2


def test_render_shows_the_criteria_in_force_at_each_sentence_and_grams_are_word_runs() -> None:
    cards = candidate_cards(chain(1, "rsi low"))
    assert "in force:" in "\n".join(render(cards, coverage(cards)))
    assert grams("a b c d e f", 5) == {("a", "b", "c", "d", "e"), ("b", "c", "d", "e", "f")}
