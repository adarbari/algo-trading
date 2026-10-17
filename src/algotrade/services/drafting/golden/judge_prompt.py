"""The golden judge's prompt (ADR 0041, amended 2026-10-17): the rubric a judge model scores a
draft by, the JSON schema of its answer, the compact rendering of a draft it is shown, and the
strict parse of its verdict. Pure: no model call here (``judge.py`` asks)."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.core.model.errors import InvalidAnswerError
from algotrade.services.drafting.screens import ScreenDraft

JUDGE_PROMPT_VERSION = "1"
DIMENSIONS = ("segmentation", "coverage", "logic", "fidelity")
MAX_DETAIL = 160
MAX_ISSUES = 12
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

JUDGE_SYSTEM = """You are a strict reviewer of a draft stock-screen. A trader typed one sentence; a
system turned it into a draft: explained parts (the words each condition comes from), criteria
(field, operator, value, mode), an optional tie_break, formulas, missing features, unresolved
terms and notes. Score the DRAFT against the SENTENCE on four dimensions, each 0 (wrong), 1
(partly right) or 2 (right):

- segmentation: each part is one coherent condition; no standalone connector or glue chip
  (but, are, show me); no condition split across non-contiguous parts; connectors are not
  stuffed into a part's words.
- coverage: every condition of the sentence is a criterion, a formula, a missing feature or an
  unresolved term; nothing silently lost; nothing invented beyond scaffolding (status, instrument
  type).
- logic: but / yet / although / while mean AND; except / excluding / unless / avoid / without mean
  AND NOT with the right direction; or means OR (a boolean formula, never two ANDed criteria);
  rank / sort becomes a tie_break with the right direction.
- fidelity: fields, units and thresholds fit the words (percent vs fraction, 3-month is about 60
  sessions); vague words are handled honestly (unresolved, or a note), never a made-up hard gate.

For every shortfall add an issue: its dimension, a short kebab-case pattern slug naming the kind of
mistake (e.g. connector-chip, split-condition, or-as-and, lost-condition, unit-mismatch), and a
detail of at most 160 characters. A perfect draft has no issues. Answer with the JSON object only:
{"segmentation": 0-2, "coverage": 0-2, "logic": 0-2, "fidelity": 0-2,
 "issues": [{"dimension": "...", "pattern": "...", "detail": "..."}]}"""

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [*DIMENSIONS, "issues"],
    "properties": {
        **{d: {"type": "integer", "minimum": 0, "maximum": 2} for d in DIMENSIONS},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension", "pattern", "detail"],
                "properties": {
                    "dimension": {"type": "string", "enum": list(DIMENSIONS)},
                    "pattern": {"type": "string"},
                    "detail": {"type": "string"},
                },
            },
        },
    },
}


@dataclass(frozen=True)
class Issue:
    """One shortfall the judge named: its ``dimension``, a kebab ``pattern`` and a ``detail``."""

    dimension: str
    pattern: str
    detail: str


@dataclass(frozen=True)
class Verdict:
    """The judge's scores (0-2 each) and issues for one draft."""

    scores: Mapping[str, int]
    issues: tuple[Issue, ...]

    @property
    def perfect(self) -> bool:
        return all(self.scores[d] == 2 for d in DIMENSIONS)


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def render_draft(draft: ScreenDraft) -> str:
    """The draft as the judge sees it, one line per element. Part attributes the draft may not
    have yet (``join``) are read with ``getattr``; nothing here is a user's private data."""
    lines: list[str] = []
    for part in draft.parts or ():
        bits = {
            "id": part.id,
            "words": part.words,
            "kind": part.kind,
            "origin": part.origin,
            "reading": part.reading,
            "join": getattr(part, "join", None),
            "items": [*part.criteria, *part.formulas, *part.missing, *part.unresolved],
        }
        lines.append("part " + _compact({k: v for k, v in bits.items() if v not in (None, [])}))
    if draft.parts is None:
        lines.append("parts: none")
    for cid, crit in draft.document.get("criteria", {}).items():
        keep = {k: crit[k] for k in ("field", "op", "value", "mode") if k in crit}
        lines.append(f"criterion {cid} " + _compact(keep))
    rank = draft.document.get("rank") or {}
    if rank.get("tie_break"):
        order = "ascending" if rank.get("tie_break_order") == "asc" else "descending"
        lines.append(f"tie_break {rank['tie_break']} {order}")
    lines += [f"formula {f.name} = {f.expr}" for f in draft.formulas]
    lines += [f"missing {m.key or m.new_key_slug}: {m.span!r}" for m in draft.missing]
    lines += [f"unresolved {u.term!r}: {u.span!r}" for u in draft.unresolved]
    lines += [f"dropped {d.field} ({d.kind})" for d in draft.dropped]
    lines += [f"note {n}" for n in draft.notes]
    return "\n".join(lines)


def judge_user_prompt(sentence: str, draft: ScreenDraft) -> str:
    """The question: the sentence, then the rendered draft."""
    return f"SENTENCE: {sentence}\n\nDRAFT:\n{render_draft(draft)}"


def parse_verdict(text: str) -> Verdict:
    """The verdict in ``text``, strictly: a JSON object with the four integer scores 0-2 and
    well-formed issues. ``InvalidAnswerError`` (the message is fed back to the model for the one
    repair) for anything else."""
    body = text.strip()
    if body.startswith("```"):
        body = re.sub(r"^```[a-z]*\s*|\s*```$", "", body)
    try:
        raw = json.loads(body)
    except ValueError as exc:
        raise InvalidAnswerError(f"the answer is not JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise InvalidAnswerError("the answer must be a JSON object")
    scores: dict[str, int] = {}
    for dim in DIMENSIONS:
        value = raw.get(dim)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2:
            raise InvalidAnswerError(f'"{dim}" must be an integer 0, 1 or 2')
        scores[dim] = value
    issues_raw = raw.get("issues", [])
    if not isinstance(issues_raw, list) or len(issues_raw) > MAX_ISSUES:
        raise InvalidAnswerError(f'"issues" must be a list of at most {MAX_ISSUES}')
    issues: list[Issue] = []
    for item in issues_raw:
        if not isinstance(item, dict):
            raise InvalidAnswerError("each issue must be an object")
        kind, pattern, detail = item.get("dimension"), item.get("pattern"), item.get("detail")
        if kind not in DIMENSIONS:
            raise InvalidAnswerError(f"an issue's dimension must be one of {list(DIMENSIONS)}")
        if not isinstance(pattern, str) or not SLUG.match(pattern):
            raise InvalidAnswerError("an issue's pattern must be a short kebab-case slug")
        if not isinstance(detail, str) or len(detail) > MAX_DETAIL:
            raise InvalidAnswerError(
                f"an issue's detail must be text of at most {MAX_DETAIL} chars"
            )
        issues.append(Issue(kind, pattern, detail))
    return Verdict(scores, tuple(issues))
