"""Every kind of option trial splits by price source or is declared unsplit (ADR 0088 decision 11):
the open verdict reads Cboe rows only and a slice reading bought-history rows is a separate
owner-only run. ``trial_kind`` maps every (base, wheel, ladder) combination of an edge document to
a trial kind, so a new base fails here until it is mapped and given a builder; each builder's edge
is sliced as its kind says (the end-to-end run over a store is
``tests/unit/services/evaluation/time_series/test_sleeve_split.py``, the sleeve's)."""

from collections.abc import Callable
from datetime import date
from itertools import product
from typing import Any

import pytest

from algotrade.config.edges import document
from algotrade.config.edges.document import Edge, parse_edge
from algotrade.config.edges.named import LADDER
from algotrade.config.edges.positions.key import with_legs
from algotrade.config.edges.positions.templates import load_templates
from algotrade.services.evaluation.cross_section.run.sources import (
    ALL,
    CBOE,
    OPTION_HISTORY,
    source_slices,
)
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.test_document import document as base_document
from tests.unit.config.edges.test_named import SLEEVE, TIMED, WHEEL

TEMPLATES = load_templates(FileConfigStore(REPO_ROOT / "config", local=False))
START, END = date(2025, 1, 6), date(2026, 11, 2)
SPLIT, UNSPLIT = (CBOE, OPTION_HISTORY), (ALL,)

# kind -> the sources its evaluation runs as
TRIAL_KINDS: dict[str, tuple[str, ...]] = {
    "cross_section_share": UNSPLIT,
    "cross_section_option": SPLIT,
    "share_setup_option_baseline": SPLIT,
    "time_series": UNSPLIT,
    "sleeve": SPLIT,
    "ladder": SPLIT,
    "wheel": SPLIT,
}
FLAGS = list(product((False, True), (False, True)))  # (wheel, ladder)
CROSS_BASES = ("event", "universe", "benchmark")  # an option or share setup, told apart by reads
# (base, wheel, ladder) -> kind; None: a combination the document refuses
KIND_OF: dict[tuple[str, bool, bool], str | None] = {
    **{
        (b, w, ld): "cross_section_share" if not (w or ld) else None
        for b in CROSS_BASES
        for w, ld in FLAGS
    },
    **{("out_of_window", w, ld): "time_series" if not (w or ld) else None for w, ld in FLAGS},
    ("delta_equivalent", False, False): "sleeve",
    ("delta_equivalent", False, True): "ladder",
    ("delta_equivalent", True, False): "wheel",
    ("delta_equivalent", True, True): None,
}  # fmt: skip


def trial_kind(edge: Edge) -> str:
    """The kind of ``edge``'s trials; raises on a combination no kind is declared for."""
    key = (edge.base, edge.outcome.wheel is not None, edge.schedule == LADDER)
    kind = KIND_OF.get(key, "unmapped")
    if kind is None or kind == "unmapped":
        raise AssertionError(f"no trial kind declared for (base, wheel, ladder) = {key}")
    if kind == "cross_section_share":
        if edge.outcome.kind == "option_pnl":
            return "cross_section_option"
        if edge.position_baselines:
            return "share_setup_option_baseline"
    return kind


def build(doc: dict[str, Any]) -> Edge:
    return with_legs(parse_edge(doc, "drift", "x.toml"), TEMPLATES)


OPTION_OUTCOME = {
    "kind": "option_pnl", "horizon_sessions": [5], "benchmark": "none", "tenor_days": 30,
    "position": "short_put", "strike_delta": 0.25, "start_offset_sessions": 1,
}  # fmt: skip

BUILDERS: dict[str, Callable[[], Edge]] = {
    "cross_section_share": lambda: build(base_document()),
    "cross_section_option": lambda: build(
        base_document(outcome=OPTION_OUTCOME, schedule="every_session")
    ),
    "share_setup_option_baseline": lambda: build(base_document(baselines=["position:short_put"])),
    "time_series": lambda: build(base_document(**TIMED)),
    "sleeve": lambda: build(base_document(**SLEEVE)),
    "ladder": lambda: build(base_document(**{**SLEEVE, "schedule": LADDER})),
    "wheel": lambda: build(base_document(**{**SLEEVE, **WHEEL})),
}


def test_every_base_wheel_ladder_combination_is_mapped_to_a_trial_kind() -> None:
    for base, wheel, ladder in product(document.BASES, (False, True), (False, True)):
        assert (base, wheel, ladder) in KIND_OF, f"unmapped: {(base, wheel, ladder)}"


def test_the_builders_cover_exactly_the_trial_kinds() -> None:
    assert set(BUILDERS) == set(TRIAL_KINDS)


@pytest.mark.parametrize("kind", sorted(TRIAL_KINDS))
def test_each_kind_slices_as_declared(kind: str) -> None:
    edge = BUILDERS[kind]()
    assert trial_kind(edge) == kind
    found = source_slices(edge, TEMPLATES, START, END)
    assert tuple(s.source for s in found) == TRIAL_KINDS[kind]
    if kind in ("cross_section_share", "time_series"):
        assert (found[0].start, found[0].end) == (START, END)  # one unsplit run
    else:  # the open slice never starts before the cutover, the history slice ends before it
        from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION as CUT  # noqa: PLC0415

        open_, history = found
        assert open_.start >= CUT and history.end < CUT and open_.job_suffix == ""
        assert history.job_suffix == OPTION_HISTORY


def test_an_unmapped_combination_raises() -> None:
    odd = build(base_document(**SLEEVE))
    from dataclasses import replace  # noqa: PLC0415

    with pytest.raises(AssertionError, match="no trial kind declared"):
        trial_kind(replace(odd, base="invented"))
