"""Where a sentence splits into clauses the phrasebook can resolve one by one (ADR 0041, amended
2026-10-17). A clause boundary is a run of and-type connectors (``connectors.JOINS``: and, but,
yet, while, although...), nothing else: an ``or`` needs a formula and a negation must stay with
the condition it changes, so a run holding either (``but not``, ``and not``) is no boundary. A run
is also no boundary when a structured wording claims one of its words (the longest wording wins,
so "cheap and liquid" as one entry stays whole), inside a numeric range ("between 40 and 60") or
between two numbers; ``then`` (a sequence, which goes to the model) never splits. Fail closed: a
run is a boundary only when the word just before it and the word just after it are both claimed by
a structured wording (a connector that reads another way, "all but", then never splits a
sentence). ``split`` works on the tokens ``resolve`` already made (lower-cased ``[a-z0-9]+``
matches and which of them wordings claimed) and returns token ranges. Pure."""

import re
from collections.abc import Sequence

from algotrade.services.drafting.parts.connectors import AND, read

SEQUENCE = frozenset({"then"})  # ordered in time, not both at once: the model reads it


def split(found: Sequence[re.Match[str]], taken: Sequence[bool]) -> list[tuple[int, int]]:
    """The token ranges ``[start, end)`` of the clauses of a sentence (``found``: its tokens;
    ``taken``: whether a structured wording claims each); one range, the whole sentence, when
    nothing splits it. Connectors at a boundary belong to no clause."""
    words = [m.group() for m in found]
    kinds = read(words)
    ranges: list[tuple[int, int]] = []
    start = 0
    between_open = False
    i = 0
    while i < len(words):
        if kinds[i][0] != "join":
            between_open = between_open or words[i] == "between"
            i += 1
            continue
        end = i
        while end < len(words) and kinds[end][0] == "join":
            end += 1
        run = range(i, end)
        keeps = (
            between_open
            or _between_numbers(words, i, end)
            or any(taken[k] or kinds[k][1] != AND or words[k] in SEQUENCE for k in run)
            or not (i > 0 and end < len(words) and taken[i - 1] and taken[end])  # fail closed
        )
        if not keeps:
            if i > start:
                ranges.append((start, i))
            start = end
        between_open = False
        i = end
    if start < len(words):
        ranges.append((start, len(words)))
    return ranges


def _between_numbers(words: Sequence[str], start: int, end: int) -> bool:
    return start > 0 and end < len(words) and words[start - 1].isdigit() and words[end].isdigit()
