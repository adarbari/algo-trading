"""The ``option_pnl`` outcome of an edge document (ADR 0053 amendment, EB H13; ADR 0088, E4): it
names a position template (the old structure enum is gone) and is labelled ``chain``; the tenor
rule is required; no benchmark, no implied-vol field, no ``otm_pct``; an edge and its variants are
all option_pnl or none is (another grain); a document that never names a tenor hashes as it did
before."""

from dataclasses import asdict
from typing import Any

import pytest

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.identity import identity_dict
from algotrade.core.model.errors import ConfigurationError
from tests.unit.config.edges.test_document import WHERE, document

CHAIN = {
    "kind": "option_pnl", "horizon_sessions": [5, 21], "benchmark": "none",
    "start_offset_sessions": 1, "position": "short_put", "tenor_days": 30,
}  # fmt: skip


def chain(**changes: Any) -> dict[str, Any]:
    body = {k: v for k, v in {**CHAIN, **changes}.items() if v is not None}
    return document(schedule="every_session", outcome=body)


def test_a_positioned_option_pnl_types_and_is_labelled_chain() -> None:
    o = parse_edge(chain(cost_bps=5, strike_delta=0.25), "drift", WHERE).outcome
    assert (o.structure, o.tenor_days, o.strike_delta, o.iv_field) == (None, 30, 0.25, None)
    assert o.position is not None and o.position.template == "short_put"
    assert o.basis == "chain" and not o.is_return and o.cost_bps == 5


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"structure": "atm_straddle_long"}, "names a position template"),
        ({"structure": "put_short", "strike_delta": 0.25}, "names a position template"),
        ({"position": None}, "position: required for an option_pnl"),
        ({"strike_delta": 0.9}, "strike_delta"),
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
    doc["variants"] = [{"id": "spread", "outcome": {"position": "put_spread"}}]
    edge = parse_edge(doc, "drift", WHERE)
    assert edge.variants[0].outcome.position.template == "put_spread"  # type: ignore[union-attr]
    assert edge.variants[0].outcome.tenor_days == 30  # the variant keeps the edge's tenor


def test_a_document_that_never_names_a_tenor_hashes_as_before() -> None:
    plain = parse_edge(document(), "drift", WHERE)
    assert "tenor_days" in asdict(plain.outcome)  # the field exists ...
    assert "tenor_days" not in identity_dict(asdict(plain.outcome))  # ... the identity omits it
    chained = parse_edge(chain(), "drift", WHERE)
    assert identity_dict(asdict(chained.outcome))["tenor_days"] == 30
