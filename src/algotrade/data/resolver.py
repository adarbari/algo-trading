"""``SymbolResolver``: vendor ticker -> ``instrument_id`` from one reference snapshot (ADR 0018).

Every job or service that holds a ticker (a vendor payload, a CLI flag, a config list) turns
it into an id here, so the id scheme lives in one place. Build one with
``algotrade.data.reference.resolver(reader, session)``.

- Active rows win over delisted ones (a reused ticker belongs to the listing trading today).
- A symbol the snapshot does not know falls back to its symbol id (``EQ:<SYMBOL>``); callers
  count those through ``resolve``.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from algotrade.core.instruments import equity_id


def _clean(symbol: object) -> str:
    return str(symbol).strip().upper()


@dataclass(frozen=True)
class SymbolResolver:
    snapshot: date | None = None  # the reference snapshot used; None = no reference yet
    ids: Mapping[str, str] = field(default_factory=dict)  # symbol -> instrument_id
    symbols: Mapping[str, str] = field(default_factory=dict)  # instrument_id -> symbol

    @classmethod
    def from_reference(
        cls, reference: pd.DataFrame | None, snapshot: date | None = None
    ) -> "SymbolResolver":
        if reference is None or reference.empty:
            return cls(snapshot)
        frame = reference[["instrument_id", "symbol"]].astype(str)
        active = (
            reference["status"].astype(str).str.upper().eq("ACTIVE")
            if "status" in reference.columns
            else pd.Series(True, index=reference.index)
        )
        # Inactive rows first, so active rows overwrite them for a shared (reused) ticker.
        ordered = frame.assign(_active=active.to_numpy()).sort_values("_active", kind="stable")
        ids = {
            _clean(s): i for i, s in zip(ordered["instrument_id"], ordered["symbol"], strict=True)
        }
        symbols = dict(zip(ordered["instrument_id"], ordered["symbol"], strict=True))
        return cls(snapshot, ids, symbols)

    def knows(self, symbol: str) -> bool:
        return _clean(symbol) in self.ids

    def id_for(self, symbol: str) -> str:
        clean = _clean(symbol)
        return self.ids.get(clean) or equity_id(clean)

    def ids_for(self, symbols: Iterable[str]) -> dict[str, str]:
        return {s: self.id_for(s) for s in symbols}

    def symbol_for(self, instrument: str) -> str | None:
        return self.symbols.get(instrument)

    def resolve(self, frame: pd.DataFrame, column: str = "symbol") -> tuple[pd.DataFrame, int]:
        """-> (copy with ``instrument_id`` from ``column`` as the first column, symbols that
        fell back to a symbol id because the snapshot does not know them)."""
        out = frame.drop(columns="instrument_id", errors="ignore")
        symbols = out[column].map(_clean)
        out.insert(0, "instrument_id", [self.id_for(s) for s in symbols])
        unknown = int((~symbols.isin(list(self.ids))).sum()) if len(symbols) else 0
        return out, unknown
