"""``explain``: the regime in plain words from the text model (ADR 0041, amended 2026-10-06).
The model's answer is a JSON object ``{"text", "links"}`` (the provider is asked for a JSON
object; text that is not one is taken as the text). It is cleaned and checked before anyone
reads it: a URL that is not one of the allowed links is dropped (the allowed ones become
``citations``, with the card's title; none stays in the text), markdown marks are removed, and
every number in the text must be one of the facts' numbers, to the precision the text shows
(``7`` matches ``6.8``; ``6.8`` does not match ``7``). A number the facts do not contain makes
the answer unchecked: ``checked`` is False, the text and citations are withheld and ``note``
says why, so the page shows the plain description instead. A model that cannot answer raises
``ModelUnavailableError``, as drafting does."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.core.model.errors import ModelUnavailableError
from algotrade.services.explaining.prompt import (
    Facts,
    Link,
    regime_facts,
    system_prompt,
    user_prompt,
)
from algotrade.services.read.regime.indicators import RegimeIndicator
from algotrade.services.read.regime.regime import MarketRegime
from algotrade.services.text_model.model import TextModel

_NUMBER = re.compile(r"(?<![A-Za-z\d.])\d[\d,]*(?:\.\d+)?")
_URL = re.compile(r"https?://[^\s\"'<>)\]]+")
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_MARKS = re.compile(r"\*\*|__|`|^#+\s*|^\s*[-*]\s+", re.MULTILINE)
_SLACK = 1e-9


@dataclass(frozen=True)
class Citation:
    """An allowed link the answer used."""

    title: str
    url: str


@dataclass(frozen=True)
class Explanation:
    """What the page shows. ``checked`` is False when a number could not be verified: then
    ``text`` is empty and ``note`` says why (the page keeps its templated text)."""

    text: str
    citations: tuple[Citation, ...]
    checked: bool
    note: str | None


def numbers_in(text: str) -> list[tuple[float, int, str]]:
    """Every number in ``text``: ``(value, decimals shown, as written)``, so ``"6.80"`` is
    ``(6.8, 2, "6.80")``."""
    found: list[tuple[float, int, str]] = []
    for match in _NUMBER.findall(text):
        written = match.rstrip(",")
        digits = written.replace(",", "")
        found.append((float(digits), len(digits.partition(".")[2]), written))
    return found


def unverified(text: str, facts: Facts) -> list[str]:
    """The numbers of ``text`` that no fact contains (each as written), in order."""
    known = [value for value, _, _ in numbers_in(facts.text)]
    return [
        written
        for value, places, written in numbers_in(text)
        if not any(abs(value - k) <= 0.5 * 10**-places + _SLACK for k in known)
    ]


def parse(raw: str) -> tuple[str, list[str]]:
    """The model's ``(text, links)``: the JSON object's fields, or the raw text with no links."""
    stripped = _FENCE.sub("", raw.strip())
    try:
        parsed: Any = json.loads(stripped)
    except ValueError:
        return stripped, []
    if not isinstance(parsed, Mapping) or not isinstance(parsed.get("text"), str):
        return stripped, []
    links = parsed.get("links")
    return parsed["text"], [u for u in links if isinstance(u, str)] if isinstance(
        links, list
    ) else []


def verify(raw: str, facts: Facts) -> Explanation:
    """``raw`` (a model answer) cleaned and checked against ``facts``."""
    text, listed = parse(raw)
    allowed = {link.url.rstrip("/"): link for link in facts.links}
    mentioned = [m.rstrip(".,;:") for m in _URL.findall(text)]
    cited: dict[str, Link] = {}
    for url in [*listed, *mentioned]:
        link = allowed.get(url.rstrip("/"))
        if link is not None:
            cited.setdefault(link.url, link)
    clean = _MARKS.sub("", _URL.sub("", text))
    clean = " ".join(clean.split())
    if not clean:
        raise ModelUnavailableError("the model's answer is empty")
    bad = unverified(clean, facts)
    if bad:
        note = (
            f"The explanation quoted {', '.join(bad)}, which the facts do not contain, so it "
            "is not shown."
        )
        return Explanation("", (), False, note)
    return Explanation(clean, tuple(Citation(c.title, c.url) for c in cited.values()), True, None)


def ask(model: TextModel, facts: Facts, question: str) -> str:
    """The model's raw answer to ``question`` over ``facts``."""
    return model.complete(system_prompt(facts), user_prompt(question))


def explain(
    model: TextModel,
    regime: MarketRegime,
    question: str,
    card: RegimeIndicator | None = None,
) -> Explanation:
    """``question`` answered over ``regime``'s facts (``card``: the card the question is about,
    in full). ``ModelUnavailableError`` when the model cannot answer."""
    facts = regime_facts(regime, card)
    return verify(ask(model, facts, question), facts)
