"""Attribute a big move from its headlines through the text model (ADR 0050 decision 5, EV4b).

The prompt carries the instrument, the session and at most ``MAX_HEADLINES`` headlines (title,
publisher and time only), and asks for one JSON object: the cause class (``taxonomy.CAUSES``), a
confidence and the number of the headline that says it. The answer is **checked**, never trusted: a
cause outside the taxonomy, a headline number that is not one of those shown, a confidence outside
0..1 or text that is not that JSON gives no row (an unexplained move stays unattributed, with the
reason in the run's counts). The evidence of a row is the cited headline verbatim and its URL, so
every stored cause points at words a reader can open. Pure but for the model it is handed.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.services.attributing import taxonomy

PROMPT_VERSION = "attributing/v1"
MAX_HEADLINES = 8  # headlines in a prompt (newest first)
MAX_CONFIDENCE = 0.8  # a model's words never reach a filing's 0.9
SYSTEM = (
    "You classify why a stock moved sharply on one trading day, from the news headlines published "
    "since the previous close. Answer with one JSON object and nothing else: "
    '{"cause": <one of the causes>, "headline": <the number of the headline that says it>, '
    '"confidence": <0 to 1>}. If no headline explains a move, answer {"cause": "other", '
    '"headline": 0, "confidence": 0}. Never use outside knowledge: only the headlines shown.'
)


@dataclass(frozen=True)
class Headline:
    title: str
    publisher: str
    published_utc: pd.Timestamp
    url: str


def headlines_of(frame: pd.DataFrame | None) -> list[Headline]:
    """The newest ``MAX_HEADLINES`` rows of a ``parse_news`` frame."""
    if frame is None or frame.empty:
        return []
    top = frame.sort_values("published_utc", ascending=False, kind="stable").head(MAX_HEADLINES)
    return [
        Headline(
            str(row["title"]),
            str(row["publisher"]),
            pd.Timestamp(str(row["published_utc"])),
            str(row["article_url"]),
        )
        for _, row in top.iterrows()
    ]


def prompt(symbol: str, session: date, shown: Sequence[Headline]) -> str:
    """The user message: the ``symbol``'s move on ``session`` and its numbered headlines."""
    lines = [
        f"{i}. {h.title} ({h.publisher}, {h.published_utc.strftime('%Y-%m-%d %H:%M')} UTC)"
        for i, h in enumerate(shown, start=1)
    ]
    return (
        f"Stock {symbol} moved sharply on {session.isoformat()}.\n"
        f"Causes: {', '.join(taxonomy.CAUSES)}.\nHeadlines, newest first:\n" + "\n".join(lines)
    )


def parse_answer(text: str, shown: Sequence[Headline]) -> tuple[str, float, Headline] | str:
    """``(cause, confidence, headline)`` of a valid answer, else the reason it is not one."""
    try:
        body = text[text.index("{") : text.rindex("}") + 1]
        answer = json.loads(body)
        cause, number, confidence = (
            answer["cause"],
            int(answer["headline"]),
            float(answer["confidence"]),
        )
    except (ValueError, KeyError, TypeError):
        return "not the JSON asked for"
    if cause not in taxonomy.CAUSES:
        return f"cause {cause!r} is not in the taxonomy"
    if not 0.0 <= confidence <= 1.0:
        return "confidence outside 0..1"
    if cause == taxonomy.OTHER or number == 0:
        return "no headline explains the move"
    if not 1 <= number <= len(shown):
        return f"headline {number} is not one of the {len(shown)} shown"
    return cause, min(confidence, MAX_CONFIDENCE), shown[number - 1]


def attribution_row(
    instrument_id: str,
    session: date,
    known_from: date,
    answer: tuple[str, float, Headline],
    model: str,
) -> dict[str, object]:
    """The row of a checked ``answer``: ``known_from`` is the day the model ran, never the
    reaction session (the headlines were read then, not at the time); ``model`` the provider and
    model that answered, with ``PROMPT_VERSION``."""
    cause, confidence, h = answer
    return {
        "instrument_id": instrument_id,
        "ts": pd.Timestamp(session, tz="UTC"),
        "known_from": known_from,
        "cause_class": cause,
        "cause_text": f"headline: {h.title}",
        "confidence": confidence,
        "evidence": h.title,
        "evidence_ref": h.url,
        "model": model,
        "prompt_version": PROMPT_VERSION,
    }
