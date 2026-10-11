"""The golden set of the drafting prompt (docs/drafting/describe-it-plan.md, "Learning from
iteration"): read the cases under ``tests/fixtures/drafting/golden/`` and score a parsed draft
against a case's expectation, structurally (fields, operators, values within a tolerance, nothing
extra). Pure: reads files it is given a root for, calls no model, writes nothing.

Layout (``root`` = ``tests/fixtures/drafting/golden``):

- ``cases/<id>.json``: ``{id, sentence, split: "train" | "held_out", expect: {parts: [...],
  scope_fields: [...]}}``. A part is ``{span, bucket: "A" | "B" | "C" | "ask", fields, op, value,
  tolerance}``: an ``A`` part wants one criterion on one of ``fields`` (alternatives) with an
  ``op`` (one, or a list of acceptable ones) and a ``value`` within ``tolerance`` (a fraction of
  the expected value; absolute when that is 0); a ``B`` / ``C`` / ``ask`` part wants none, so any
  criterion that matches no ``A`` part is extra. ``scope_fields`` are tolerated scaffolding
  (status, security type).
- ``answers/<model-slug>/<id>.json``: the model's raw answer text for that case, replayed in CI.

To add a case: write ``cases/<id>.json``, record the model's raw answer into
``answers/<slug>/<id>.json`` (the owner CLI will do both later), run the replay test; a
``held_out`` sentence must appear in neither the prompt examples nor the phrasebook (fitness test
``tests/architecture/drafting``)."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SPLITS = ("train", "held_out")


@dataclass(frozen=True)
class GoldenCase:
    """One golden case: a sentence and what a correct draft of it contains."""

    id: str
    sentence: str
    split: str
    parts: tuple[Mapping[str, Any], ...]
    scope_fields: frozenset[str]


@dataclass(frozen=True)
class GoldenScore:
    """How a draft measures against a case: spans of parts with no matching criterion
    (``missing``), parts whose criterion has the wrong op or value (``wrong``), and fields kept
    or dropped that no part asked for (``extra``)."""

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
        cases.append(
            GoldenCase(
                raw["id"],
                raw["sentence"],
                raw["split"],
                tuple(expect["parts"]),
                frozenset(expect.get("scope_fields", ())),
            )
        )
    return tuple(cases)


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
) -> GoldenScore:
    """Score the kept criteria (``criteria_of``'s table) and the fields it dropped as invented."""
    missing: list[str] = []
    wrong: list[str] = []
    used: set[str] = set()
    for part in case.parts:
        if part["bucket"] != "A":
            continue
        found = [
            cid for cid, crit in kept.items() if cid not in used and crit["field"] in part["fields"]
        ]
        if not found:
            missing.append(part["span"])
            continue
        hit = next((cid for cid in found if _fits(part, kept[cid])), None)
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
    return GoldenScore(tuple(missing), tuple(wrong), tuple(extra) + tuple(dropped_fields))


def _fits(part: Mapping[str, Any], crit: Mapping[str, Any]) -> bool:
    ops = part["op"] if isinstance(part["op"], list) else [part["op"]]
    if crit["op"] not in ops:
        return False
    return _close(crit.get("value"), part["value"], float(part.get("tolerance", 0)))


def _close(got: Any, want: Any, tolerance: float) -> bool:
    if isinstance(want, list) or isinstance(got, list):
        return isinstance(got, list) and isinstance(want, list) and set(got) == set(want)
    if isinstance(want, bool) or isinstance(got, bool) or isinstance(want, str):
        return bool(got == want)
    if not isinstance(got, (int, float)):
        return False
    return bool(abs(got - want) <= (tolerance * abs(want) if want else tolerance))
