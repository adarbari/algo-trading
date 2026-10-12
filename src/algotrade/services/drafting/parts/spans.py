"""Where a part's words are in the sentence (ADR 0041, amended 2026-10-11). The model quotes the
words of each part; the server finds them in the sentence, in order, each part searched after the
previous one: exact (whole words), then ignoring case, then token by token allowing one edit per
token (a typo: ``liquidd``; never in a short token or one with a digit). The served ``words`` is
the sentence's own slice, so a copy the model got wrong is never shown. What no part covers and
holds more than a connector is a ``not_understood`` gap. Offsets are code points here; ``utf16``
converts them to what the browser counts."""

import re
from dataclasses import dataclass

MIN_FUZZY = 4  # a token shorter than this, or with a digit, must match exactly
CONNECTORS = frozenset(  # glue: words that mean nothing alone ("or" and "not" are never glue)
    {
        "and",
        "with",
        "plus",
        "also",
        "then",
        "that",
        "which",
        "where",
        "whose",
        "who",
        "the",
        "a",
        "an",
        "&",
    }
)
_TOKEN = re.compile("[\\w$%&'\u2019][\\w$%&'\u2019.\\-/]*")


@dataclass(frozen=True)
class Span:
    start: int
    end: int


def tokens(text: str) -> list[tuple[int, int, str]]:
    """The words of ``text`` as (start, end, lower-cased word), punctuation left out."""
    out: list[tuple[int, int, str]] = []
    for m in _TOKEN.finditer(text):
        word = m.group().rstrip(".-/")
        if word:
            out.append((m.start(), m.start() + len(word), word.casefold()))
    return out


def utf16(text: str, index: int) -> int:
    """``index`` (code points into ``text``) as UTF-16 code units."""
    return len(text[:index].encode("utf-16-le")) // 2


def locate(sentence: str, words: str, after: int = 0) -> Span | None:
    """The first place at or after ``after`` where ``words`` is in ``sentence``: exact, ignoring
    case, then token by token with one edit allowed per token; ``None`` when it is nowhere."""
    wanted = " ".join(words.split())
    if not wanted:
        return None
    for flags in (0, re.IGNORECASE):
        found = _regex(wanted, flags).search(sentence, after)
        if found is not None:
            return Span(found.start(), found.end())
    return _fuzzy(sentence, wanted, after)


def _regex(wanted: str, flags: int) -> re.Pattern[str]:
    head = r"(?<!\w)" if wanted[0].isalnum() else ""
    tail = r"(?!\w)" if wanted[-1].isalnum() else ""
    return re.compile(head + re.escape(wanted) + tail, flags)


def _fuzzy(sentence: str, wanted: str, after: int) -> Span | None:
    have = [t for t in tokens(sentence) if t[0] >= after]
    want = [t[2] for t in tokens(wanted)]
    if not want:
        return None
    for i in range(len(have) - len(want) + 1):
        window = have[i : i + len(want)]
        if all(_close(w[2], t) for w, t in zip(window, want, strict=True)):
            return Span(window[0][0], window[-1][1])
    return None


def _close(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < MIN_FUZZY or any(c.isdigit() for c in a + b):
        return False
    return _one_edit(a, b)


def _one_edit(a: str, b: str) -> bool:
    """Whether ``a`` and ``b`` differ by one insertion, deletion, substitution or swap of two
    neighbouring characters."""
    if abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    if i == len(a) == len(b):
        return True
    if len(a) == len(b):
        return a[i + 1 :] == b[i + 1 :] or (
            a[i] == b[i + 1] and a[i + 1] == b[i] and a[i + 2 :] == b[i + 2 :]
        )
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return short[i:] == long_[i + 1 :]


def gaps(sentence: str, covered: list[Span]) -> list[Span]:
    """The stretches of ``sentence`` no span of ``covered`` (in order) touches that hold a word
    other than a connector, trimmed of the connectors and punctuation at their edges."""
    out: list[Span] = []
    cursor = 0
    for span in [*covered, Span(len(sentence), len(sentence))]:
        found = [t for t in tokens(sentence[cursor : span.start]) if t[2] not in CONNECTORS]
        if found:
            out.append(Span(cursor + found[0][0], cursor + found[-1][1]))
        cursor = max(cursor, span.end)
    return out
