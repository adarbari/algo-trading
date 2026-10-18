"""The identity of an edge or outcome for hashing (ADR 0053 amendments): its ``asdict`` without the
keys a document that never used them would not have had before they existed."""

from typing import Any


def identity_dict(value: Any) -> Any:
    """``value`` (an ``asdict`` of an edge or outcome) without the side keys of a long outcome, an
    unset ``hold_rank`` and an unset ``pair_field``: a document that never named a side, a band or
    a pair field hashes as it did before them, so no stored leg or run is recomputed by their
    arrival (ADR 0053 amendments)."""
    if isinstance(value, dict):
        long = value.get("side") == "long" and value.get("borrow_bps_annual") is None
        return {
            k: identity_dict(v)
            for k, v in value.items()
            if not (long and k in ("side", "borrow_bps_annual"))
            and not (k in ("hold_rank", "pair_field") and v is None)
        }
    if isinstance(value, (list, tuple)):
        return [identity_dict(v) for v in value]
    return value
