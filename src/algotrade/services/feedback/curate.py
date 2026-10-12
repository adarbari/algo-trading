"""``algotrade-api golden curate``: turn the owner's hand-written ``curation.json`` into golden
cases under ``tests/fixtures/drafting/golden/cases/`` (docs/drafting/describe-it-plan.md,
"Learning from iteration"; ADR 0066).

    [{"source_event": "<chain id printed by `golden candidates`>",
      "sentences": ["<the owner's PARAPHRASE of sentence 1>", "...2", ...],
      "criteria": {"criteria": {...}, "rank": ...},   # optional: default the stored final criteria
      "split": "train" | "held_out",                  # optional: default by a hash of source_event
      "id": "<case id>"}]                             # optional: default golden-<hash of source>

The repo is public and the sentences are real traders': NEVER a stored sentence. The owner writes
one paraphrase per real sentence of the chain, in order, and ``plan_cases`` REFUSES a paraphrase
that equals ANY loaded real sentence (not only its own chain's) once case and punctuation are
ignored, shares >= 0.8 of its words with one, or shares a 5-word run with one (the verbatim guard,
the rule of the leak fitness test). The owner approves the criteria: they must validate as a rule
screen over the catalogue (the caller's ``validate``) and name no holding (an instrument id, or a
field about a ticker, symbol or position). A paraphrase, criterion id, rank or value that LOOKS
like a holding (``candidates.holding_flags``, a ticker-like value) only WARNS, loudly, naming the
tokens, and is still written (owner decision 2026-10-11). A case is every sentence in order, the
criteria in force at each (the stored ``current_criteria``, held to the same checks) and the final
criteria, with ``source_event`` (the session's final event id), ``source_events`` (the id of every
event of the chain, in time order: what the retention job must spare), ``chain_id`` (the session)
and an expectation derived from the final criteria for the structural scorer
(``services/drafting/golden.py``). No answers are recorded here: the case is written with
``"recorded": false`` and its ``curated`` date, and ``golden run --record`` records one and clears
the flag (a fitness test fails a case unrecorded for 14 days). A case file is never overwritten.
All problems of a file are reported together and nothing is written unless there are none."""

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.feedback.candidates import (
    JARGON,
    SCOPE_PREFIXES,
    brief,
    criteria_table,
    grams,
    holding_flags,
    normalised,
    overlap,
)

VERBATIM = 0.8  # word overlap with a stored sentence at or above which a paraphrase is refused
HELD_OUT_PERCENT = 20
SPLITS = ("train", "held_out")
SCREENER_ID = "golden-curate"
_FIGI = re.compile(r"^(EQ:|BBG[0-9A-Z]{9}$)")
_TICKER = re.compile(r"^[A-Z]{1,5}$")
_HOLDING_FIELD = re.compile(r"ticker|symbol|instrument_id|holding|position", re.IGNORECASE)

type Validate = Callable[[dict[str, Any]], None]  # raises ConfigurationError for a bad document


@dataclass(frozen=True)
class PlannedCase:
    """One case file to write: its ``path``, its JSON ``body`` and the ``warnings`` to show."""

    path: Path
    body: dict[str, Any]
    warnings: tuple[str, ...] = field(default=())


def split_of(source_event: str) -> str:
    """``held_out`` for about ``HELD_OUT_PERCENT`` % of the events, by a hash of the id (stable)."""
    bucket = int(hashlib.sha256(source_event.encode()).hexdigest(), 16) % 100
    return "held_out" if bucket < HELD_OUT_PERCENT else "train"


def case_id(source_event: str) -> str:
    """The default case id: opaque, from a hash of the event (never the sentence)."""
    return "golden-" + hashlib.sha256(source_event.encode()).hexdigest()[:10]


def verbatim_of(paraphrase: str, real: Sequence[str]) -> str | None:
    """The stored sentence ``paraphrase`` copies (the same words, >= ``VERBATIM`` overlap with it,
    or a shared 5-word run), else ``None``. The one place the public-repo rule is enforced."""
    own = grams(paraphrase)
    for stored in real:
        if (
            normalised(paraphrase) == normalised(stored)
            or overlap(paraphrase, stored) >= VERBATIM
            or own & grams(stored)
        ):
            return stored
    return None


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return []


def holding_problems(snapshot: Any) -> list[str]:
    """What in a criteria snapshot names a position: an instrument id value, or a field about a
    ticker, symbol or holding."""
    problems = []
    for cid, crit in criteria_table(snapshot).items():
        if not isinstance(crit, Mapping):
            continue
        if _HOLDING_FIELD.search(str(crit.get("field", ""))):
            problems.append(f"criterion {cid}: field {crit.get('field')} names a position")
        if any(_FIGI.match(s) for s in _strings(crit.get("value"))):
            problems.append(f"criterion {cid}: its value is an instrument id")
    return problems


def expectation(final: Mapping[str, Any]) -> dict[str, Any]:
    """The scorer's expectation from the approved final criteria: one ``A`` part per criterion
    (its field, op and value, exact), the scope fields tolerated."""
    parts = []
    for cid, crit in criteria_table(final).items():
        name = str(crit["field"])
        if name.startswith(SCOPE_PREFIXES):
            continue
        parts.append({
            "span": f"{cid}: {name} {crit['op']} {crit.get('value')}",
            "bucket": "A",
            "fields": [name],
            "op": crit["op"],
            "value": crit.get("value"),
            "tolerance": 0.0,
        })  # fmt: skip
    return {"parts": parts, "scope_fields": list(SCOPE_PREFIXES)}


def holding_warnings(paraphrases: Sequence[str], *snapshots: Any) -> list[str]:
    """Tokens that look like a position, to WARN about (never to refuse): ``holding_flags`` of the
    paraphrases and of the criterion ids and rank strings, and ticker-like (upper-case) values."""
    out = [f"paraphrase {n}: {t}" for n, p in enumerate(paraphrases, 1) for t in holding_flags(p)]
    for snap in snapshots:
        texts = [str(cid) for cid in criteria_table(snap)]
        texts += _strings(snap.get("rank")) if isinstance(snap, Mapping) else []
        out += [f"criteria: {t}" for text in texts for t in holding_flags(text)]
        for crit in criteria_table(snap).values():
            values = _strings(crit.get("value")) if isinstance(crit, Mapping) else []
            out += [f"criteria value: {v}" for v in values if _TICKER.match(v) and v not in JARGON]
    return sorted(set(out))


def _document(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": SCREENER_ID,
        "kind": "screener",
        "impl": "rules",
        "criteria": dict(criteria_table(snapshot)),
    }
    if snapshot.get("rank"):
        document["rank"] = snapshot["rank"]
    return document


def _final(
    entry: Mapping[str, Any], stored: Mapping[str, Any], validate: Validate
) -> tuple[Any, list[str]]:
    final = entry.get("criteria", stored["final_criteria"])
    table = criteria_table(final)
    if not table:
        return None, ["criteria: no criteria table"]
    problems = holding_problems(final)
    try:
        validate(_document(final))
    except ConfigurationError as exc:
        problems.append(f"criteria: not a valid rule screen over the catalogue: {exc}")
    return final, problems


@dataclass
class Setting:
    """What a curation is checked against: the stored candidates by ``source_event``, the
    catalogue ``validate``, the cases folder, every loaded real sentence (``real``), today."""

    stored: Mapping[str, Mapping[str, Any]]
    validate: Validate
    cases_dir: Path
    real: Sequence[str]
    today: date
    taken: set[str] = field(default_factory=set)


def _plan_one(index: int, entry: Any, ctx: Setting) -> tuple[PlannedCase | None, list[str]]:
    name = f"entry {index}"
    if not isinstance(entry, Mapping) or not isinstance(entry.get("source_event"), str):
        return None, [f"{name}: needs a source_event"]
    stored = ctx.stored.get(entry["source_event"])
    if stored is None:
        return None, [f"{name}: source_event {entry['source_event']} is not a candidate in range"]
    chain_real = [s["sentence"] or "" for s in stored["sentences"]]
    paras = entry.get("sentences")
    if not isinstance(paras, list) or not all(isinstance(p, str) and p.strip() for p in paras):
        return None, [f"{name}: sentences must be a list of non-empty paraphrases"]
    problems = []
    if len(paras) != len(chain_real):
        problems.append(f"{name}: {len(chain_real)} sentence(s) in the chain, {len(paras)} given")
    for n, para in enumerate(paras, 1):
        if verbatim_of(para, [*chain_real, *ctx.real]) is not None:
            problems.append(f"{name}: sentence {n} copies a real sentence; paraphrase it")
    split = entry.get("split", split_of(entry["source_event"]))
    if split not in SPLITS:
        problems.append(f"{name}: split must be one of {SPLITS}")
    final, bad = _final(entry, stored, ctx.validate)
    problems += [f"{name}: {p}" for p in bad]
    in_force = [s["current_criteria"] for s in stored["sentences"]]
    problems += [f"{name}: in force at sentence {n}: {p}"
                 for n, c in enumerate(in_force, 1) for p in holding_problems(c)]  # fmt: skip
    cid = str(entry.get("id") or case_id(entry["source_event"]))
    path = ctx.cases_dir / f"{cid}.json"
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", cid):
        problems.append(f"{name}: id {cid!r} must be lower-case letters, digits and dashes")
    elif path.exists() or cid in ctx.taken:
        problems.append(f"{name}: case {cid} already exists; never overwritten")
    if problems:
        return None, problems
    ctx.taken.add(cid)
    body = {
        "id": cid,
        "sentence": paras[-1],
        "sentences": paras,
        "criteria_in_force": in_force,
        "final_criteria": final,
        "source_event": entry["source_event"],
        "source_events": stored["source_events"],
        "chain_id": stored["chain_id"],
        "split": split,
        "curated": ctx.today.isoformat(),
        "recorded": False,
        "expect": expectation(final),
    }
    warned = holding_warnings(paras, final, *in_force)
    return PlannedCase(path, body, tuple(warned)), []


def plan_cases(
    entries: Any,
    stored: Sequence[Mapping[str, Any]],
    validate: Validate,
    cases_dir: Path,
    real: Sequence[str],
    today: date,
) -> list[PlannedCase]:
    """The case files ``entries`` (the parsed ``curation.json``) ask for, checked against the
    ``stored`` candidates (``chains.golden_candidates``), every loaded real sentence ``real`` (the
    verbatim guard) and the catalogue (``validate``); ``ConfigurationError`` listing every
    problem, else nothing is refused and nothing written."""
    if not isinstance(entries, list) or not entries:
        raise ConfigurationError("curation.json must be a non-empty list of entries")
    ctx = Setting({c["source_event"]: c for c in stored}, validate, cases_dir, real, today)
    planned: list[PlannedCase] = []
    problems: list[str] = []
    for index, entry in enumerate(entries, 1):
        case, bad = _plan_one(index, entry, ctx)
        problems += bad
        if case is not None:
            planned.append(case)
    if problems:
        raise ConfigurationError("curation refused:\n  " + "\n  ".join(problems))
    return planned


def describe(planned: Sequence[PlannedCase]) -> list[str]:
    """What ``write_cases`` would write: per file its split, the criteria in force at each
    sentence and the final ones, then any WARNING (a token that looks like a holding)."""
    lines: list[str] = []
    for p in planned:
        body = p.body
        lines.append(f"{p.path}: {body['split']}, {len(body['sentences'])} sentence(s)")
        lines += [
            f"  in force at {n}: {brief(c)}" for n, c in enumerate(body["criteria_in_force"], 1)
        ]
        lines.append(f"  final criteria: {brief(body['final_criteria'])}")
        lines += [f"  WARNING looks like a holding, still written: {w}" for w in p.warnings]
    return lines


def write_cases(planned: Sequence[PlannedCase]) -> list[Path]:
    """Write each case file (exclusive create: an existing file is an error, never replaced)."""
    for p in planned:
        p.path.parent.mkdir(parents=True, exist_ok=True)
        with p.path.open("x") as handle:
            handle.write(json.dumps(p.body, indent=2) + "\n")
    return [p.path for p in planned]
