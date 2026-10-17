"""The one vocabulary for the words between conditions (ADR 0041, amended 2026-10-17). ``JOINS``
are the phrases that say how a condition relates to the one before it (and, or, and not; only the
and-type ones are left out of a part's words, a negation or an or stays inside the condition);
``GLUE`` are closed-class words that mean nothing alone (auxiliaries, pronouns, fillers like
"show me"). The prompt renders the join phrases from here, so the model's "leave the connector
out of the words" and the server's reading of what it left out cannot drift; ``spans`` turns
what no part covers into a ``join`` of the next part, never into a not-understood chip. Pure."""

AND = "and"
OR = "or"
AND_NOT = "and_not"
JOIN_KINDS = (AND, OR, AND_NOT)

_JOIN_PHRASES: dict[str, tuple[str, ...]] = {
    AND: (
        "and", "but", "yet", "while", "although", "though", "whereas", "plus", "also",
        "as long as", "so long as", "only if", "provided", "provided that", "with", "then",
    ),
    OR: ("or", "either", "otherwise"),
    AND_NOT: (
        "except", "except for", "excluding", "exclude", "unless", "without", "but not", "not",
        "avoid", "other than", "rather than", "minus", "no", "all but", "anything but",
        "everything but", "nothing but",
    ),
}  # fmt: skip
JOINS: dict[str, str] = {p: logic for logic, ps in _JOIN_PHRASES.items() for p in ps}

GLUE = frozenset(
    {
        # the old connectors that are not joins
        "that", "which", "where", "whose", "who", "the", "a", "an", "&",
        # auxiliaries
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
        "did",
        # pronouns and determiners
        "they", "them", "those", "these", "it", "its", "their", "there", "this",
        # fillers
        "show me", "find", "give me", "list", "get", "i", "i'm", "im", "looking for", "i want",
        "want", "basically", "just", "please", "some", "any", "ones",
    }
)  # fmt: skip
GLUE_WORDS = frozenset(w for w in GLUE if " " not in w)  # the one-word glue, for a word check


def join_text(*logics: str) -> str:
    """The join phrases of ``logics`` (default: the and-type ones, the only connectors the model
    leaves out of a part's words) as the prompt lists them, in the order declared here."""
    return ", ".join(p for p, logic in JOINS.items() if logic in (logics or (AND,)))


def _phrase_words() -> dict[tuple[str, ...], str | None]:
    out: dict[tuple[str, ...], str | None] = {tuple(p.split()): None for p in GLUE}
    out.update({tuple(p.split()): logic for p, logic in JOINS.items()})
    return out


_PHRASES = _phrase_words()
_LONGEST = max(len(p) for p in _PHRASES)


def read(words: list[str]) -> list[tuple[str, str | None]]:
    """What each lower-cased word of a stretch is: ``("join", logic)``, ``("glue", None)`` or
    ``("content", None)``; a phrase marks all its words, the longest phrase at a place wins."""
    words = [w.replace("\u2019", "'") for w in words]  # a phone's curly apostrophe
    out: list[tuple[str, str | None]] = []
    i = 0
    while i < len(words):
        for size in range(min(_LONGEST, len(words) - i), 0, -1):
            key = tuple(words[i : i + size])
            if key in _PHRASES:
                logic = _PHRASES[key]
                out += [("join", logic) if logic else ("glue", None)] * size
                i += size
                break
        else:
            out.append(("content", None))
            i += 1
    return out


def merged(logics: list[str]) -> str:
    """One logic for the connectors of a stretch (``and also``): a negation wins over an or, an
    or over an and."""
    for kind in (AND_NOT, OR):
        if kind in logics:
            return kind
    return AND
