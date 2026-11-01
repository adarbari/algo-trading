"""The option outcomes of an edge document beyond ``expires_otm``: the horizon check of
``option_model_pnl`` (``tenor_sessions``, ``check_tenor``: its implied-vol field's tenor) and the
``option_pnl`` outcome of an edge document (ADR 0053 amendment, EB H13; ADR 0088): the P&L of a
position template (``position``, ``config/site/positions/templates.toml``) from the stored chains
(``outcomes/option/structure_pnl@v2``), basis ``chain``, beside ``option_model_pnl`` (a modelled
P&L, basis ``model``).

    position      the template of the legs held (required; the old ``structure`` enum is gone)
    tenor_days    the tenor rule: the contracts expire on the first allowed date at least this many
                  calendar days after the entry session and not before the window's end
    strike_delta  replaces the delta of the template's short delta legs (``position/key.py``)
    horizon_sessions, benchmark ``"none"``, ``start_offset_sessions``, ``cost_bps``, ``side`` as
                  for any outcome; it reads no implied-vol field and sets no ``otm_pct``

The grain is forward-only: chains are stored from 2026-10-02, after every frozen split, so no
pre-frozen basis exists and every row is out of sample (ADR 0065 amendment).
"""

import re
from typing import NoReturn

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

STRUCTURES = ("put", "call", "strangle")  # an expires_otm outcome's short option(s)
# An option_model_pnl outcome's position: one at-the-money straddle held to the horizon's close,
# long or short, or delta-hedged, long or short (ADR 0053 amendment 2026-10-17).
MODEL_STRUCTURES = (
    "atm_straddle_long", "atm_straddle_short", "delta_hedged_atm", "delta_hedged_atm_short",
)  # fmt: skip
CHAIN_KIND = "option_pnl"
CHAIN_BASIS = "chain"  # what a P&L of quoted prices is labelled (results and UI)
MAX_TENOR_DAYS = 400


def check_chain(o: Table) -> NoReturn:
    """An ``option_pnl`` outcome names a ``position`` template (ADR 0088, E4): the legs, not an
    older ``structure``, say what is held. Always raises, naming the file and key."""
    if "structure" in o.names():
        raise ConfigurationError(
            f"{o.where} structure: an option_pnl names a position template (position = ...), "
            f"the structure enum is gone (ADR 0088)"
        )
    raise ConfigurationError(f"{o.where} position: required for an option_pnl outcome")


def check_positioned(
    o: Table, delta: float | None, pct: float | None, iv_field: str | None
) -> tuple[None, float | None, None, None]:
    """``(None, strike_delta, None, None)`` of an ``option_pnl`` outcome that names a ``position``
    template (ADR 0088): the legs, not a ``structure``, say what is held; ``strike_delta`` (0.05 to
    0.5) overrides the template's delta legs."""
    if "position" not in o.names() or "structure" in o.names():
        check_chain(o)
    if pct is not None or iv_field is not None:
        key = "otm_pct" if pct is not None else "iv_field"
        raise ConfigurationError(f"{o.where} {key}: an option_pnl reads quoted prices, it has none")
    if delta is not None and not 0.05 <= round(delta, 2) <= 0.5:
        raise ConfigurationError(f"{o.where} strike_delta: 0.05 to 0.5, got {delta}")
    return None, None if delta is None else round(delta, 2), None, None


def chain_tenor(o: Table, kind: str) -> int | None:
    """The ``tenor_days`` of an ``option_pnl`` outcome (required, 1 to ``MAX_TENOR_DAYS``); None
    for any other kind, which may not name one."""
    if kind != CHAIN_KIND:
        if "tenor_days" in o.names():
            raise ConfigurationError(f"{o.where} tenor_days: only an option_pnl outcome has one")
        return None
    days = o.integer("tenor_days", 0)
    if not 1 <= days <= MAX_TENOR_DAYS:
        raise ConfigurationError(
            f"{o.where} tenor_days: required, calendar days from 1 to {MAX_TENOR_DAYS}, got {days}"
        )
    return days


def check_kinds(where: str, kinds: set[str]) -> None:
    """Refuse an edge whose outcome and variants mix ``option_pnl`` (another grain) with others."""
    if chain_kind_mixed(kinds):
        raise ConfigurationError(
            f"{where} variants: an edge's outcome and its variants are all option_pnl or none is "
            f"(another grain)"
        )


def chain_kind_mixed(kinds: set[str]) -> bool:
    return CHAIN_KIND in kinds and len(kinds) > 1


def structures_of(kind: str, otm: tuple[str, ...], model: tuple[str, ...]) -> tuple[str, ...]:
    """The structure values an outcome of ``kind`` may name (``otm``: expires_otm's, ``model``:
    option_model_pnl's; an option_pnl names a position, no structure)."""
    return {"expires_otm": otm, CHAIN_KIND: ()}.get(kind, model)


# The implied vol is one tenor (``iv30``: 30 calendar days, about 21 sessions) and prices every
# horizon of the outcome, so a horizon far from it prices the wrong option: an option_model_pnl
# horizon must lie within ``[tenor / 2, tenor * 2]`` sessions of the field's tenor, read from its
# name (a field with no ``iv<days>`` in its name has no known tenor and is refused).
TRADING_DAYS_PER_YEAR, CALENDAR_DAYS_PER_YEAR = 252, 365
_IV_TENOR = re.compile(r"(?<![a-z0-9])iv(\d+)(?![0-9])")


def tenor_sessions(iv_field: str) -> int | None:
    """The tenor of an implied-vol field in sessions (``iv30`` is 30 calendar days: 21), from its
    name; None when the name carries none."""
    found = _IV_TENOR.search(iv_field.lower())
    if found is None:
        return None
    return round(int(found.group(1)) * TRADING_DAYS_PER_YEAR / CALENDAR_DAYS_PER_YEAR)


def check_tenor(o: Table, horizons: tuple[int, ...], iv_field: str | None) -> None:
    """Refuse an ``option_model_pnl`` horizon the field's one tenor cannot price (module top)."""
    if iv_field is None:
        return  # required, and reported, by ``_expires_otm``
    tenor = tenor_sessions(iv_field)
    if tenor is None:
        raise ConfigurationError(
            f"{o.where} iv_field: {iv_field!r} names no tenor (iv<days>), so an option_model_pnl "
            f"cannot tell which horizons its vol prices"
        )
    low, high = tenor // 2, tenor * 2
    bad = [h for h in horizons if not low <= h <= high]
    if bad:
        raise ConfigurationError(
            f"{o.where} horizon_sessions: {bad} are outside {low}..{high} sessions, what the "
            f"{tenor}-session tenor of {iv_field!r} prices; use a field of the horizon's tenor"
        )


def option_fields(o: Table, kind: str) -> tuple[str | None, float | None, float | None, str | None]:
    """``(structure, strike_delta, otm_pct, iv_field)``: a structure only for the option kinds."""
    delta, pct = o.number("strike_delta", None), o.number("otm_pct", None)
    iv_field = " ".join(o.text("iv_field", "").split()) or None
    structures = structures_of(kind, STRUCTURES, MODEL_STRUCTURES)
    if kind == CHAIN_KIND:
        return check_positioned(o, delta, pct, iv_field)
    structure = o.choice("structure", "", structures) if "structure" in o.names() else None
    if kind not in ("expires_otm", "option_model_pnl", CHAIN_KIND):
        for key, value in (("structure", structure), ("strike_delta", delta), ("otm_pct", pct)):
            if value is not None:
                raise ConfigurationError(f"{o.where} {key}: only an expires_otm outcome has one")
        return None, None, None, iv_field
    if structure is None:
        raise ConfigurationError(f"{o.where} structure: required")
    if kind == "option_model_pnl":
        for key, value in (("strike_delta", delta), ("otm_pct", pct)):
            if value is not None:
                raise ConfigurationError(
                    f"{o.where} {key}: an option_model_pnl is at the money, it has no strike"
                )
    elif (delta is None) == (pct is None):
        raise ConfigurationError(
            f"{o.where}: an expires_otm outcome names exactly one of strike_delta and otm_pct"
        )
    for key, value in (("strike_delta", delta), ("otm_pct", pct)):
        if value is not None and not 0 < value < 1:
            raise ConfigurationError(f"{o.where} {key}: expected a fraction in (0, 1), got {value}")
    if iv_field is None:
        raise ConfigurationError(f"{o.where} iv_field: required for an {kind} outcome")
    return structure, delta, pct, iv_field
