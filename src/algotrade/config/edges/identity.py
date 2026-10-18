"""The identity of an edge document for hashing: ``identity_dict`` drops the keys an outcome
that never named them would not have had, so a hash is stable across the arrival of a key."""

from typing import Any

from algotrade.config.edges.document import LONG


def identity_dict(value: Any) -> Any:
    """``value`` (an ``asdict`` of an edge or outcome) without the side keys of a long outcome
    and an unset ``hold_rank`` or ``tenor_days``: a document that never named one hashes as it
    did before, so no stored leg or run is recomputed by their arrival (ADR 0053 amendments)."""
    if isinstance(value, dict):
        long = value.get("side") == LONG and value.get("borrow_bps_annual") is None
        return {
            k: identity_dict(v)
            for k, v in value.items()
            if not (long and k in ("side", "borrow_bps_annual"))
            and not (k in ("tenor_days", "hold_rank") and v is None)
        }
    if isinstance(value, (list, tuple)):
        return [identity_dict(v) for v in value]
    return value
