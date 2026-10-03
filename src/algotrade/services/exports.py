"""CSV exports in the column layout of the original ``combine_liquidity.py``.

Keeps existing downstream workflows (e.g. the daily VRP scanner) working unchanged:
``optionable_universe_with_liquidity_<ver>.csv`` and ``short_premium_candidates_<ver>.csv``.
"""

import csv
from collections.abc import Mapping
from pathlib import Path

from algotrade.core.feature_view import FeatureValue
from algotrade.core.instruments import symbol_of
from algotrade.services.screening import ScreenOutcome
from algotrade.services.views import to_value
from algotrade.strategies.screeners.base import Decision

LEGACY_COLUMNS = (
    "ticker",
    "company_name",
    "asset_class",
    "security_type",
    "exchange",
    "process_further",
    "short_put_ok",
    "short_call_ok",
    "put_tier",
    "call_tier",
    "put_spread_pct_of_mid",
    "put_spread_usd",
    "put_strike",
    "put_delta",
    "put_bid",
    "put_ask",
    "put_strike_oi",
    "put_zone_oi",
    "call_spread_pct_of_mid",
    "call_spread_usd",
    "call_strike",
    "call_delta",
    "call_bid",
    "call_ask",
    "call_strike_oi",
    "call_zone_oi",
    "chain_oi",
    "target_expiry",
    "target_dte",
    "underlying_price",
    "iv30",
    "liq_status",
    "chain_asof",
    "source_crosscheck",
    "notes",
    "universe_version",
)
_UNIVERSE_FIELDS = (
    "company_name",
    "asset_class",
    "security_type",
    "exchange",
    "source_crosscheck",
    "notes",
    "universe_version",
)
_PASS_THROUGH = (
    "put_tier",
    "call_tier",
    "chain_oi",
    "target_expiry",
    "target_dte",
    "underlying_price",
    "iv30",
    "chain_asof",
)


_COUNT_SUFFIXES = ("_oi", "_dte")


def _text(value: FeatureValue, key: str = "") -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).upper()
    if isinstance(value, float) and key.endswith(_COUNT_SUFFIXES) and value.is_integer():
        return str(int(value))
    return str(value)


def _side(values: Mapping[str, FeatureValue], side: str) -> dict[str, str]:
    pct = values.get(f"{side}_spread_pct")
    out = {
        f"{side}_spread_pct_of_mid": f"{float(pct) * 100:.2f}" if pct is not None else "",
        f"{side}_spread_usd": _text(values.get(f"{side}_spread_abs")),
    }
    for key in ("strike", "delta", "bid", "ask", "strike_oi", "zone_oi"):
        out[f"{side}_{key}"] = _text(values.get(f"{side}_{key}"), key)
    return out


def legacy_rows(outcome: ScreenOutcome) -> list[dict[str, str]]:
    meta = outcome.universe.frame.set_index("instrument_id")
    rows = []
    for r in outcome.run.rows:
        u = meta.loc[r.instrument_id]
        row = {"ticker": symbol_of(r.instrument_id)}
        row.update(
            {
                k: "" if k not in u or u[k] is None else _text(to_value(u[k]))
                for k in _UNIVERSE_FIELDS
            }
        )
        row["process_further"] = _text(r.decision is Decision.QUALIFIED)
        row["short_put_ok"] = _text(bool(r.values.get("short_put_ok")))
        row["short_call_ok"] = _text(bool(r.values.get("short_call_ok")))
        row.update({k: _text(r.values.get(k), k) for k in _PASS_THROUGH})
        row["liq_status"] = _text(r.values.get("liq_status")) or "NOT_SCREENED"
        row.update(_side(r.values, "put"))
        row.update(_side(r.values, "call"))
        rows.append(row)
    rows.sort(key=lambda x: (x["asset_class"] != "STOCK", x["ticker"]))
    return rows


def write_legacy_exports(outcome: ScreenOutcome, out_dir: Path, version: str) -> tuple[Path, Path]:
    rows = legacy_rows(outcome)
    out_dir.mkdir(parents=True, exist_ok=True)
    full = out_dir / f"optionable_universe_with_liquidity_{version}.csv"
    candidates = out_dir / f"short_premium_candidates_{version}.csv"
    for path, subset in (
        (full, rows),
        (candidates, [r for r in rows if r["process_further"] == "TRUE"]),
    ):
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=LEGACY_COLUMNS)
            writer.writeheader()
            writer.writerows(subset)
    return full, candidates


# Export name (as listed in a config's ``exports``) -> writer(outcome, directory, version).
EXPORTS = {"legacy_liquidity_csv": write_legacy_exports}
