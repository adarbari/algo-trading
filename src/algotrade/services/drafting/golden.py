"""The golden set of the drafting prompt (docs/drafting/describe-it-plan.md, "Learning from
iteration"): read the cases under ``tests/fixtures/drafting/golden/`` and score a parsed draft
against a case's expectation, structurally (fields, operators, values within a tolerance, nothing
extra). Pure: reads files it is given a root for, calls no model, writes nothing.

Layout (``root`` = ``tests/fixtures/drafting/golden``):

- ``cases/<id>.json`` (a curated case also has ``sentences`` and ``source_event``: ``services/
  feedback/curate.py``): ``{id, sentence, split: "train" | "held_out", expect: {parts: [...],
  scope_fields: [...]}}``. A part is ``{span, bucket: "A" | "B" | "C" | "ask", fields, op, value,
  tolerance}``: an ``A`` part wants one criterion on one of ``fields`` (alternatives) with an
  ``op`` (one, or a list of acceptable ones; ``equivalent_ops``, default none, only the
  boundary partner of ``op`` (``gt`` / ``gte``, ``lt`` / ``lte``), met at the exact value) and a
  ``value`` within ``tolerance`` (a fraction of the expected value; absolute when that is 0); a
  ``B`` / ``C`` / ``ask`` part wants no criterion of its own, so any criterion that matches no
  ``A`` part is extra. The A / B / C contract
  (ADR 0041, amended 2026-10-11) adds expectations a part may carry: a ``B`` part with ``expr``
  wants a kept formula with that fingerprint (``features.expressions.fingerprint``, so a
  rewriting of it passes; any other kept formula is extra) and, with ``op`` / ``value``, that
  criterion on it, a ``C`` part with ``key`` wants a
  missing item of that curated backlog key (a new slug never matches; a missing item no part
  names is extra unless a ``C`` part has no key), an ``ask`` part with ``term`` wants that term
  unresolved (any other unresolved term is extra). A part without these keys expects nothing of
  the new buckets, and a score given no
  ``formulas`` / ``missing`` / ``unresolved`` leaves them unchecked (an answer of the old shape).
  ``scope_fields`` are tolerated scaffolding (status, security type). Only ``criteria`` are
  scored: the draft's ``suggestions`` (soft / score checks offered, never applied) never pass or
  fail a case, they are counted and reported (``golden_run``). ``EQUIVALENT_READINGS`` names the
  readings that say the same thing (an ETF as ``is_etf`` or as ``security_type in [ETF]``).
  ``"contract": true`` in ``expect`` marks a case written for the contract: CI replays its
  answer through the whole ``draft_screen``; its ``suggestions`` (``{offered, dropped, notes}``:
  fields offered, fields dropped, words a note must contain) are asserted by the replay, not
  by ``score``.
- ``answers/<model-slug>/<id>.json``: the model's raw answer text for that case, replayed in CI.

To add a case: write ``cases/<id>.json``, record the model's raw answer into
``answers/<slug>/<id>.json`` (the owner CLI will do both later), run the replay test; a
``held_out`` sentence must appear in neither the prompt examples nor the phrasebook (fitness test
``tests/architecture/drafting``)."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.expressions.fingerprint import fingerprint

SPLITS = ("train", "held_out")
BOUNDARY_PARTNER = {
    "gt": "gte",
    "gte": "gt",
    "lt": "lte",
    "lte": "lt",
}  # what ``equivalent_ops`` may name

# Readings (field, op, value) that select the same instruments, so a part expecting one is met
# by any of them: the scorer must not fail a draft for choosing between synonyms.
EQUIVALENT_READINGS: tuple[frozenset[tuple[str, str, Any]], ...] = (
    frozenset({("instrument.is_etf", "eq", True), ("instrument.security_type", "in", ("ETF",))}),
)


@dataclass(frozen=True)
class GoldenCase:
    """One golden case: a sentence and what a correct draft of it contains."""

    id: str
    sentence: str
    split: str
    parts: tuple[Mapping[str, Any], ...]
    scope_fields: frozenset[str]
    sentences: tuple[str, ...] = ()  # a curated case: every description of one session, in order
    current: Mapping[str, Any] | None = None  # the criteria in force at the last description
    recorded: bool = True  # False: curated, no answer recorded yet (``golden run --record``)
    curated: str | None = None  # the date a curated case was written (ISO)
    contract: bool = False  # the whole draft is replayed (formulas checked, gaps resolved)
    suggested: Mapping[str, Any] = field(
        default_factory=dict
    )  # replay: offered / dropped fields, notes


@dataclass(frozen=True)
class GoldenScore:
    """How a draft measures against a case: spans of parts with no matching criterion
    (``missing``), parts whose criterion has the wrong op or value (``wrong``), and fields (and
    formulas) kept or dropped that no part asked for (``extra``)."""

    missing: tuple[str, ...]
    wrong: tuple[str, ...]
    extra: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (self.missing or self.wrong or self.extra)


def load_cases(root: Path) -> tuple[GoldenCase, ...]:
    """Every case under ``root/cases``, by id."""
    cases = []
    for path in sorted((root / "cases").glob("*.json")):
        raw = json.loads(path.read_text())
        if raw["split"] not in SPLITS:
            raise ValueError(f"{path.name}: split must be one of {SPLITS}")
        expect = raw["expect"]
        _check_equivalent_ops(path.name, expect["parts"])
        cases.append(
            GoldenCase(
                raw["id"],
                raw["sentence"],
                raw["split"],
                tuple(expect["parts"]),
                frozenset(expect.get("scope_fields", ())),
                tuple(raw.get("sentences", ())) or (raw["sentence"],),
                _in_force(raw),
                raw.get("recorded", True),
                raw.get("curated"),
                bool(expect.get("contract", False)),
                expect.get("suggestions", {}),
            )
        )
    return tuple(cases)


def _check_equivalent_ops(name: str, parts: Sequence[Mapping[str, Any]]) -> None:
    """``equivalent_ops`` may only name the boundary partner of the part's ``op`` (``gt`` /
    ``gte``, ``lt`` / ``lte``): a different direction is a different screen."""
    for part in parts:
        ops = part["op"] if isinstance(part.get("op"), list) else [part.get("op")]
        for extra in part.get("equivalent_ops", ()):
            if not any(BOUNDARY_PARTNER.get(str(op)) == extra for op in ops):
                raise ValueError(
                    f"{name}: equivalent_ops {extra!r} is not the boundary partner of {ops}"
                )


def _in_force(raw: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The criteria in force at the last description of a curated case, when it had any."""
    forces = raw.get("criteria_in_force") or []
    last = forces[-1] if forces else None
    return last if isinstance(last, Mapping) and last.get("criteria") else None


def mark_recorded(root: Path, case_id: str) -> None:
    """Clear ``"recorded": false`` from a case file once an answer is recorded for it."""
    path = root / "cases" / f"{case_id}.json"
    if not path.exists():
        return
    raw = json.loads(path.read_text())
    if raw.get("recorded", True) is False:
        del raw["recorded"]
        path.write_text(json.dumps(raw, indent=2) + "\n")


def recorded_answers(root: Path, case_id: str) -> dict[str, str]:
    """The recorded raw answers for a case, by model slug."""
    return {
        path.parent.name: path.read_text()
        for path in sorted((root / "answers").glob(f"*/{case_id}.json"))
    }


def score(
    case: GoldenCase,
    kept: Mapping[str, Mapping[str, Any]],
    dropped_fields: Sequence[str] = (),
    formulas: Sequence[tuple[str, Mapping[str, Any] | None]] | None = None,
    missing_keys: Sequence[str] | None = None,
    terms: Sequence[str] | None = None,
) -> GoldenScore:
    """Score the kept criteria (``criteria_of``'s table) and the fields it dropped as invented.
    ``formulas``: the kept formulas' ``(expr, criterion)``; ``missing_keys``: each missing
    item's curated key (``new:<slug>`` for a new one); ``terms``: the unresolved terms (``None``:
    that bucket is not scored)."""
    missing: list[str] = []
    wrong: list[str] = []
    used: set[str] = set()
    for part in case.parts:
        if part["bucket"] != "A":
            continue
        found = [
            cid
            for cid, crit in kept.items()
            if cid not in used and any(f["field"] in part["fields"] for f in _forms(crit))
        ]
        if not found:
            missing.append(part["span"])
            continue
        hit = next((cid for cid in found if any(_fits(part, f) for f in _forms(kept[cid]))), None)
        if hit is None:
            wrong.append(part["span"])
            used.add(found[0])
        else:
            used.add(hit)
    extra = [
        crit["field"]
        for cid, crit in kept.items()
        if cid not in used and crit["field"] not in case.scope_fields
    ]
    extra += _bucket_scores(case, formulas, missing_keys, terms, missing, wrong)
    return GoldenScore(tuple(missing), tuple(wrong), tuple(extra) + tuple(dropped_fields))


def _bucket_scores(
    case: GoldenCase,
    formulas: Sequence[tuple[str, Mapping[str, Any] | None]] | None,
    missing_keys: Sequence[str] | None,
    terms: Sequence[str] | None,
    missing: list[str],
    wrong: list[str],
) -> list[str]:
    """Score the B, C and unresolved buckets: spans not found go to ``missing``, a formula whose
    criterion is not the expected one to ``wrong``; what was kept and nothing asked for is
    returned (a missing item is tolerated when a ``C`` part names no key)."""
    extra: list[str] = []
    if formulas is not None:
        got = [(_print(e), e, crit) for e, crit in formulas]
        for part in (p for p in case.parts if p["bucket"] == "B" and "expr" in p):
            found = next((g for g in got if g[0] == _print(part["expr"])), None)
            if found is None:
                missing.append(str(part["span"]))
                continue
            got.remove(found)  # a second part with the same formula needs its own
            if "op" in part and (found[2] is None or not _fits(part, found[2])):
                wrong.append(str(part["span"]))
        extra += [f"formula {e}" for _, e, _ in got]
    if missing_keys is not None:
        wanted = {p["key"] for p in case.parts if "key" in p}
        missing += [
            str(p["span"]) for p in case.parts if "key" in p and p["key"] not in missing_keys
        ]
        open_ended = any(p["bucket"] == "C" and "key" not in p for p in case.parts)
        if not open_ended:
            extra += [f"missing {k}" for k in missing_keys if k not in wanted]
    if terms is not None:
        said = {t.lower() for t in terms}
        wanted_terms = {p["term"].lower() for p in case.parts if "term" in p}
        missing += [
            str(p["span"]) for p in case.parts if "term" in p and p["term"].lower() not in said
        ]
        extra += [f"unresolved {t}" for t in terms if t.lower() not in wanted_terms]
    return extra


def _print(expr: str) -> str:
    """The fingerprint of ``expr`` (a formula that does not parse is its own text)."""
    try:
        definition = FeatureDefinition("golden", "golden", expr, "float", "ratio", "x", "x")
        return fingerprint(definition).hash
    except ConfigurationError:  # an invalid formula never matches an expected one
        return f"invalid:{expr}"


def _forms(crit: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """``crit`` and the criteria that read the same (``EQUIVALENT_READINGS``)."""
    value = crit.get("value")
    reading = (crit["field"], crit["op"], tuple(value) if isinstance(value, list) else value)
    forms: list[Mapping[str, Any]] = [crit]
    for group in EQUIVALENT_READINGS:
        if reading in group:
            for field_name, op, same in group - {reading}:
                forms.append(
                    {
                        "field": field_name,
                        "op": op,
                        "value": list(same) if isinstance(same, tuple) else same,
                    }
                )
    return forms


def _fits(part: Mapping[str, Any], crit: Mapping[str, Any]) -> bool:
    ops = part["op"] if isinstance(part["op"], list) else [part["op"]]
    tolerance = float(part.get("tolerance", 0))
    if crit["op"] in part.get("equivalent_ops", ()):  # the boundary partner: the exact value
        return _close(crit.get("value"), part["value"], 0.0)
    if crit["op"] not in ops:
        return False
    return _close(crit.get("value"), part["value"], tolerance)


def _close(got: Any, want: Any, tolerance: float) -> bool:
    if isinstance(want, list) or isinstance(got, list):
        return isinstance(got, list) and isinstance(want, list) and set(got) == set(want)
    if isinstance(want, bool) or isinstance(got, bool) or isinstance(want, str):
        return bool(got == want)
    if not isinstance(got, (int, float)):
        return False
    return bool(abs(got - want) <= (tolerance * abs(want) if want else tolerance))
