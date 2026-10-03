"""The selection logic of the original liquidity_screen.py ``analyse()``, kept verbatim in
spirit (network and CSV handling removed) so the port can be checked against it."""

from datetime import date
from typing import Any

DTE_TARGET, DTE_MIN, DTE_MAX, DTE_FALLBACK = 35, 21, 60, 14
DELTA_TARGET, ZONE_LO, ZONE_HI = 0.30, 0.15, 0.40
PICK_LO, PICK_HI = 0.20, 0.40
TIERS = [
    ("A", 0.05, 0.03, 2000, 20000, 0.25),
    ("B", 0.10, 0.05, 500, 5000, 0.15),
    ("C", 0.20, 0.10, 100, 1000, 0.05),
]


def tier(side: dict[str, Any] | None, chain_oi: int) -> str:
    if not side or side["bid"] is None:
        return "D"
    for t, sp, sa, zoi, coi, mb in TIERS:
        if (
            ((side["spread_pct"] <= sp) or (side["spread_abs"] <= sa))
            and side["zone_oi"] >= zoi
            and chain_oi >= coi
            and side["bid"] >= mb
        ):
            return t
    return "D"


def analyse(rows: list[dict[str, Any]], today: date) -> dict[str, Any]:
    chain_oi = int(sum(r["oi"] for r in rows))
    exps = sorted({r["exp"] for r in rows})
    dte = {e: (e - today).days for e in exps}

    def monthly(e: date) -> bool:
        return 15 <= e.day <= 21 and (e.weekday() == 4 or (e.weekday() == 3 and e.day <= 20))

    cand = (
        [e for e in exps if DTE_MIN <= dte[e] <= DTE_MAX and monthly(e)]
        or [e for e in exps if DTE_MIN <= dte[e] <= DTE_MAX]
        or [e for e in exps if dte[e] >= DTE_FALLBACK]
    )
    if not cand:
        return {"put_tier": "D", "call_tier": "D", "target_expiry": None}
    te = min(cand, key=lambda e: abs(dte[e] - DTE_TARGET))
    out: dict[str, Any] = {"target_expiry": te}
    for cp, name in (("P", "put"), ("C", "call")):
        leg = [r for r in rows if r["exp"] == te and r["cp"] == cp and r["delta"]]
        quoted = [r for r in leg if r["bid"] > 0 and r["ask"] > r["bid"]]
        band = [r for r in quoted if PICK_LO <= abs(r["delta"]) <= PICK_HI]
        s = (
            min(band, key=lambda r: ((r["ask"] - r["bid"]) / ((r["ask"] + r["bid"]) / 2), -r["oi"]))
            if band
            else min(quoted, key=lambda r: abs(abs(r["delta"]) - DELTA_TARGET))
            if quoted
            else None
        )
        side = None
        if s:
            zone = [r for r in leg if ZONE_LO <= abs(r["delta"]) <= ZONE_HI]
            mid = (s["bid"] + s["ask"]) / 2
            side = {
                "strike": s["k"],
                "bid": s["bid"],
                "spread_abs": round(s["ask"] - s["bid"], 2),
                "spread_pct": round((s["ask"] - s["bid"]) / mid, 4),
                "zone_oi": int(sum(r["oi"] for r in zone)),
            }
        out[f"{name}_tier"] = tier(side, chain_oi)
        out[f"{name}_strike"] = side["strike"] if side else None
    return out
