"""Where a part's words are in the sentence (ADR 0041, amended 2026-10-11). The model quotes the
words of each part; the server finds them in the sentence, in order, each part searched after the
previous one: exact (whole words), then ignoring case, then token by token allowing one edit per
token (a typo: ``liquidd``; never in a short token or one with a digit). The served ``words`` is
the sentence's own slice, so a copy the model got wrong is never shown. What no part covers and
holds more than glue and connectors is a ``not_understood`` gap; the connector that joins a part
to the one before it is read from what lies between them (``connectors``, never a chip). Offsets
are code points here; ``utf16`` converts them to what the browser counts."""

import re
from dataclasses import dataclass

from algotrade.services.drafting.parts.connectors import AND, OR, merged, read

MIN_FUZZY = 4  # a token shorter than this, or with a digit, must match exactly
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


@dataclass(frozen=True)
class Join:
    """A connector read from the sentence: its logic and the sentence's own words for it."""

    logic: str
    words: str


@dataclass(frozen=True)
class Stretch:
    """What lies before one covered span (or the sentence's end): ``gap``, the words that hold
    more than glue and connectors, trimmed at both edges, with ``gap_join``, the connector before
    them; and ``next_join``, the connector after them (or all there is, when there is no gap),
    which joins the span that follows."""

    gap: Span | None
    gap_join: Join | None
    next_join: Join | None


def stretches(sentence: str, covered: list[Span]) -> list[Stretch]:
    """One ``Stretch`` for each span of ``covered`` (in order) and one for the end of the
    sentence: glue and connectors are never a gap, only the words between them are."""
    out: list[Stretch] = []
    cursor = 0
    for n, span in enumerate([*covered, Span(len(sentence), len(sentence))]):
        where = "lead" if n == 0 else "between" if n < len(covered) else "tail"
        out.append(_stretch(sentence, cursor, span.start, where))
        cursor = max(cursor, span.end)
    first = out[0]  # an and-type connector before everything has nothing to join: dropped
    out[0] = Stretch(first.gap, _lead(first.gap_join), first.next_join if first.gap else None)
    return out


def _lead(join: Join | None) -> Join | None:
    return None if join is not None and join.logic in (AND, OR) else join


def _stretch(sentence: str, start: int, end: int, where: str = "between") -> Stretch:
    """A word of content, or a connector that is not and-type (a negation, an or), is kept: it
    would change what the trader asked for, so it is never silent (it is a not-understood gap
    unless the model kept it inside a part). Only and-type connectors and glue are read as a
    join, and so is an or or a negation that lies alone between two parts (``where`` is
    ``between``): the next part's join, which ``contract/groups`` turns into a group (ADR 0071);
    a negation before the first part or any after the last has nothing to join and stays a gap
    (a leading "either" is dropped like a leading and-type connector)."""
    toks = [(s + start, e + start, w) for s, e, w in tokens(sentence[start:end])]
    kinds = read([t[2] for t in toks])
    quiet = {AND, OR} if where == "lead" else {AND}  # joins that never make a gap here
    kept = [
        i
        for i, k in enumerate(kinds)
        if k[0] == "content" or (k[0] == "join" and k[1] not in quiet)
    ]
    pure = all(kinds[i][0] == "join" for i in kept)  # only a negation or an or, no content
    if not kept or (where == "between" and pure):
        return Stretch(None, None, _join(sentence, toks, kinds, range(len(toks))))
    first, last = kept[0], kept[-1]
    return Stretch(
        Span(toks[first][0], toks[last][1]),
        _join(sentence, toks, kinds, range(last + 1 if pure else first)),
        _join(sentence, toks, kinds, range(last + 1, len(toks))),
    )


def _join(
    sentence: str,
    toks: list[tuple[int, int, str]],
    kinds: list[tuple[str, str | None]],
    where: range,
) -> Join | None:
    held = [i for i in where if kinds[i][0] == "join"]
    if not held:
        return None
    logics = [logic for i in held if (logic := kinds[i][1])]
    return Join(merged(logics), sentence[toks[held[0]][0] : toks[held[-1]][1]])
