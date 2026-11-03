"""``headlines``: the prompt shows numbered headlines, an answer is checked (taxonomy, a headline
that was shown, confidence), and a row's evidence is the cited headline."""

from datetime import date

import pandas as pd

from algotrade.services.attributing import headlines, taxonomy

S = date(2026, 10, 5)
SHOWN = [
    headlines.Headline("AAA cuts guidance", "Wire", pd.Timestamp("2026-10-05T12:00:00Z"), "u1"),
    headlines.Headline("Analyst downgrade", "Daily", pd.Timestamp("2026-10-05T09:00:00Z"), "u2"),
]


def _answer(cause: str = "guidance", headline: object = 1, confidence: object = 0.7) -> str:
    return f'{{"cause": "{cause}", "headline": {headline}, "confidence": {confidence}}}'


def test_the_prompt_numbers_the_headlines_and_lists_the_causes() -> None:
    text = headlines.prompt("AAA", S, SHOWN)
    assert "1. AAA cuts guidance (Wire, 2026-10-05 12:00 UTC)" in text and "2. Analyst" in text
    assert all(cause in text for cause in taxonomy.CAUSES)


def test_a_valid_answer_names_the_cause_the_headline_and_a_capped_confidence() -> None:
    cause, confidence, headline = headlines.parse_answer(f"ok {_answer(confidence=0.95)}", SHOWN)  # type: ignore[misc]
    assert (cause, headline.url) == ("guidance", "u1")
    assert confidence == headlines.MAX_CONFIDENCE  # a model never reaches a filing's 0.9


def test_an_answer_that_cannot_be_checked_gives_no_row_and_says_why() -> None:
    assert "JSON" in str(headlines.parse_answer("no idea", SHOWN))
    assert "taxonomy" in str(headlines.parse_answer(_answer("alien"), SHOWN))
    assert "not one of the 2 shown" in str(headlines.parse_answer(_answer(headline=7), SHOWN))
    assert "confidence" in str(headlines.parse_answer(_answer(confidence=1.5), SHOWN))
    assert "no headline" in str(headlines.parse_answer(_answer("other", 0, 0), SHOWN))
    assert "no headline" in str(headlines.parse_answer(_answer("guidance", 0), SHOWN))


def test_the_row_cites_the_headline_and_is_known_from_the_day_the_model_ran() -> None:
    row = headlines.attribution_row(
        "EQ:A", S, date(2026, 10, 9), ("guidance", 0.7, SHOWN[0]), "p:m"
    )
    assert (row["evidence"], row["evidence_ref"]) == ("AAA cuts guidance", "u1")
    assert row["known_from"] == date(2026, 10, 9) and row["ts"] == pd.Timestamp(S, tz="UTC")
    assert (row["model"], row["prompt_version"]) == ("p:m", headlines.PROMPT_VERSION)


def test_only_the_newest_headlines_are_shown() -> None:
    frame = pd.DataFrame(
        {
            "title": [f"t{i}" for i in range(12)],
            "publisher": "p",
            "published_utc": pd.date_range("2026-10-05", periods=12, freq="h", tz="UTC"),
            "article_url": "u",
        }
    )
    shown = headlines.headlines_of(frame)
    assert len(shown) == headlines.MAX_HEADLINES and shown[0].title == "t11"
    assert headlines.headlines_of(None) == []
