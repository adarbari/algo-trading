"""The ``option_pnl`` outcome of an edge document (ADR 0053 amendment, EB H13): each chain
structure types and is labelled ``chain``; a put needs its delta, a straddle takes none; the tenor
rule is required; no benchmark, no implied-vol field; an edge and its variants are all option_pnl
or none is (another grain); a document that never names a tenor hashes as it did before."""

from dataclasses import asdict
from typing import Any

import pytest

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.identity import identity_dict
from algotrade.config.edges.positions.chain import CHAIN_STRUCTURES, grain_structure
from algotrade.core.model.errors import ConfigurationError
from tests.unit.config.edges.test_document import WHERE, document

CHAIN = {
    "kind": "option_pnl", "horizon_sessions": [5, 21], "benchmark": "none",
    "start_offset_sessions": 1, "structure": "atm_straddle_long", "tenor_days": 30,
}  # fmt: skip


def chain(**changes: Any) -> dict[str, Any]:
    body = {k: v for k, v in {**CHAIN, **changes}.items() if v is not None}
    return document(schedule="every_session", outcome=body)


@pytest.mark.parametrize("structure", [s for s in CHAIN_STRUCTURES if s != "put_short"])
def test_each_chain_structure_types_and_is_labelled_chain(structure: str) -> None:
    o = parse_edge(chain(structure=structure, cost_bps=5), "drift", WHERE).outcome
    assert (o.structure, o.tenor_days, o.strike_delta, o.iv_field) == (structure, 30, None, None)
    assert o.basis == "chain" and not o.is_return and o.cost_bps == 5


def test_a_short_put_names_its_delta_and_the_grain_stores_the_long_put_of_that_delta() -> None:
    o = parse_edge(chain(structure="put_short", strike_delta=0.25), "drift", WHERE).outcome
    assert o.strike_delta == 0.25 and grain_structure(o.structure or "", o.strike_delta) == (
        "put_delta_25"
    )
    assert grain_structure("delta_hedged_atm_short", None) == "atm_straddle"


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"structure": "put_short"}, "strike_delta: a put_short names the put's delta"),
        ({"structure": "put_short", "strike_delta": 0.9}, "strike_delta: a put_short names"),
        ({"strike_delta": 0.25}, "only a put_short has a strike"),
        ({"structure": "put"}, "structure"),  # an expires_otm structure
        ({"structure": None}, "structure: required"),
        ({"tenor_days": None}, "tenor_days: required"),
        ({"tenor_days": 0}, "tenor_days: required"),
        ({"benchmark": "SPY"}, "has no benchmark"),
        ({"iv_field": "rollup.iv30@v1.iv30"}, "iv_field: an option_pnl reads quoted prices"),
        ({"otm_pct": 0.05}, "otm_pct: an option_pnl reads quoted prices"),
    ],
)
def test_an_option_pnl_outcome_fails_closed(changes: dict[str, Any], match: str) -> None:
    with pytest.raises(ConfigurationError, match=match):
        parse_edge(chain(**changes), "drift", WHERE)


def test_only_an_option_pnl_outcome_names_a_tenor() -> None:
    doc = document(outcome={
        "kind": "excess_return", "horizon_sessions": [5], "benchmark": "SPY",
        "start_offset_sessions": 1, "tenor_days": 30,
    })  # fmt: skip
    with pytest.raises(ConfigurationError, match="only an option_pnl outcome has one"):
        parse_edge(doc, "drift", WHERE)


def test_an_edge_and_its_variants_read_one_grain() -> None:
    doc = chain()
    doc["variants"] = [{
        "id": "excess", "outcome": {"kind": "excess_return", "benchmark": "SPY"},
    }]  # fmt: skip
    with pytest.raises(ConfigurationError, match="all option_pnl or none is"):
        parse_edge(doc, "drift", WHERE)
    doc["variants"] = [{"id": "short", "outcome": {"structure": "atm_straddle_short"}}]
    edge = parse_edge(doc, "drift", WHERE)
    assert edge.variants[0].outcome.structure == "atm_straddle_short"
    assert edge.variants[0].outcome.tenor_days == 30  # the variant keeps the edge's tenor


def test_a_document_that_never_names_a_tenor_hashes_as_before() -> None:
    plain = parse_edge(document(), "drift", WHERE)
    assert "tenor_days" in asdict(plain.outcome)  # the field exists ...
    assert "tenor_days" not in identity_dict(asdict(plain.outcome))  # ... the identity omits it
    chained = parse_edge(chain(), "drift", WHERE)
    assert identity_dict(asdict(chained.outcome))["tenor_days"] == 30
