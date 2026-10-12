"""Scoring the explained parts of a draft against a golden case, and over many calls (ADR 0041,
amended 2026-10-11). Structural, never the text of a reading (the model words it freely): each
expected part is found by its ``words`` (and ``origin``) and must have the expected ``kind``
(and, when the case says so, the ``reading_source``); a served part nobody expected that was not
understood is extra. The measures, reported by the live golden run: the share of items the
model placed itself, the share of its parts located in the sentence, the parts not understood
(a deliberately vague case expects some) and the share of its readings that kept their numbers."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from algotrade.services.drafting.parts.model import Part, PartsStats


@dataclass(frozen=True)
class PartsScore:
    """``missing``: expected parts not served; ``wrong``: served with another kind or reading
    source; ``extra``: parts not understood that nothing expected."""

    missing: tuple[str, ...]
    wrong: tuple[str, ...]
    extra: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (self.missing or self.wrong or self.extra)


def score_parts(expected: Mapping[str, Any], served: Sequence[Part] | None) -> PartsScore:
    """``served`` (a draft's parts) against ``expected`` (a case's ``explained``)."""
    wanted: Sequence[Mapping[str, Any]] = expected.get("parts", ())
    parts = list(served or ())
    missing: list[str] = []
    wrong: list[str] = []
    used: set[int] = set()
    for want in wanted:
        n = next(
            (
                i
                for i, p in enumerate(parts)
                if i not in used and p.words == want["words"] and p.origin == want["origin"]
            ),
            None,
        )
        if n is None:
            missing.append(str(want["words"]) or str(want["origin"]))
            continue
        used.add(n)
        if parts[n].kind != want["kind"] or (
            "reading" in want and parts[n].reading_source != want["reading"]
        ):
            wrong.append(str(want["words"]) or str(want["origin"]))
    extra = [p.words for i, p in enumerate(parts) if i not in used and p.kind == "not_understood"]
    return PartsScore(tuple(missing), tuple(wrong), tuple(extra))


def share_ok(expected: Mapping[str, Any], stats: PartsStats | None) -> bool:
    """Whether the model placed at least the case's ``model_share`` of the items itself."""
    floor = expected.get("model_share")
    if floor is None:
        return True
    if stats is None or not stats.items:
        return False
    return stats.by_model / stats.items >= float(floor)


def aggregate(stats: Iterable[PartsStats | None]) -> dict[str, float | int | None]:
    """The four measures over the calls that produced parts (``None``: no call did)."""
    got = [s for s in stats if s is not None]
    items, spans = sum(s.items for s in got), sum(s.spans for s in got)
    readings = sum(s.readings for s in got)

    def ratio(part: int, whole: int) -> float | None:
        return part / whole if whole else None

    return {
        "with_parts": len(got),
        "model_share": ratio(sum(s.by_model for s in got), items),
        "located_share": ratio(sum(s.located for s in got), spans),
        "not_understood": sum(s.not_understood for s in got),
        "readings_kept": ratio(sum(s.readings_kept for s in got), readings),
    }
