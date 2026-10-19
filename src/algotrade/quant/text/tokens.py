"""The pinned tokeniser of a filing text: NFKC, casefolded, runs of ``a-z`` of two or more
letters, digits dropped, no stemming, the stop words below removed.

Every choice is fixed so two runs, and two sessions, count the same words: the stop list is
written here, never read from a library whose version could change it, and a word is counted
the same whatever the corpus (no document frequency).
"""

import re
import unicodedata
from collections import Counter

_WORD = re.compile(r"[a-z]{2,}")
STOPWORDS = frozenset(
    (
        "a", "about", "above", "after", "again", "all", "also", "am", "an", "and", "any",
        "are", "as", "at", "be", "because", "been", "before", "being", "below", "between",
        "both", "but", "by", "can", "could", "did", "do", "does", "doing", "down", "during",
        "each", "few", "for", "from", "further", "had", "has", "have", "having", "he",
        "her", "here", "hers", "him", "his", "how", "i", "if", "in", "into", "is", "it",
        "its", "itself", "may", "me", "might", "more", "most", "must", "my", "no", "nor",
        "not", "of", "off", "on", "once", "only", "or", "other", "our", "ours", "out",
        "over", "own", "same", "shall", "she", "should", "so", "some", "such", "than",
        "that", "the", "their", "theirs", "them", "then", "there", "these", "they", "this",
        "those", "through", "to", "too", "under", "until", "up", "us", "very", "was", "we",
        "were", "what", "when", "where", "which", "while", "who", "whom", "why", "will",
        "with", "would", "you", "your", "yours",
    )
)  # fmt: skip


def tokenize(text: str) -> list[str]:
    """The words of ``text`` in order, stop words removed (module doc)."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return [w for w in _WORD.findall(folded) if w not in STOPWORDS]


def term_counts(text: str) -> Counter[str]:
    """Each word's raw count in ``text`` (``tokenize``)."""
    return Counter(tokenize(text))
