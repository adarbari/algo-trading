"""``earnings_moves@v1``: how far a name moved on each of its last twelve earnings reports, and
whether the options market paid too much for them (the Earnings week page, V8 of
``docs/ui/evening-desk-plan.md``).

The window is ``earnings_reaction@v2``'s own (``counted_moves``: a report E counts at session S
once ``known_from <= S`` and its window E-1 .. E+1 has closed, ``E+1 <= S``; one report per
quarter; the raw move, not the excess over SPY), read here for twelve reports instead of eight.

    move_1 .. move_12         the signed close(E+1) / close(E-1) - 1 of the 12 newest counted
                              reports, ``move_1`` the newest; 0.05 is +5%, a fall is negative
    move_date_1 .. _12        the report date E of each of them
    moves_counted_12          how many of the last 12 reports had both window bars (0 to 12)
    abs_move_mean_12          the mean absolute move of those
    options_overpaid_m        how many of those reports have a stored ``implied_move@v1`` row at
                              the session before the report (E-1) with ``move_basis`` EARNINGS,
                              an ``implied_move`` and a ``move_expiry`` that covers E
                              (``implied_move.expiry_covers``: after E, or on E for a pre-open
                              report)
    options_overpaid_n        how many of those m had ``implied_move`` above the absolute move

The implied move of a past report is read from this store's own partition of E-1 through the
``rollups/instrument/implied_move@v1`` input (``session_date == E-1``, never a later session's
partition and never recomputed from a chain). Chains are stored only since 2026-10-02 and the
history purchase is not done, so ``options_overpaid_m`` and ``_n`` are null (UNKNOWN) for every
name until the first nightly after a report whose E-1 session has a stored chain; they are never
zero for "not measured". A name with a partition at E-1 but no earnings-basis straddle is not
counted in m.

One row per instrument traded on the session; ``moves_counted_12`` is null for a name with no
report row at all and 0 for one whose reports are all still open. The windows (12 reports,
``LOOKBACK`` sessions:
twelve quarters and the window around the oldest; 800 sessions reach 12 reports, where
earnings_reaction's 330 hold about 5) are part of the definition: changing one is a
new version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.corporate.earnings_reaction import (
    SYMBOLS,
    counted_moves,
    read_reactions,
)
from algotrade.features.rollups.positioning.implied_move import expiry_covers
from algotrade.features.rollups.price.price_stats import BARS

NAME = "earnings_moves"
VERSION = 1
REPORTS = 12  # the reports the moves cover
# sessions back: twelve quarters (about 756 sessions) and the window around the oldest. Cost [I]
# (estimated, not measured): the implied_move read is bounded by the stored chains (about 20
# partitions since 2026-10-02); the 800-session bars read, 1.5x earnings_reaction's 540, dominates.
LOOKBACK = 800
IMPLIED = "rollups/instrument/implied_move@v1"
EARNINGS_BASIS = "EARNINGS"

_REPORT = f"{earnings.EVENTS}.ts"
_NO_MOVES = (
    "no report known by the session has a closed window with both bars (moves_counted_12 is 0)"
)
_FEWER = "fewer than {n} reports with a closed window and both bars are known by the session"
_NO_STRADDLE = (
    "no counted report of the name has a stored implied_move@v1 partition at the session before "
    "it with an earnings-basis straddle (chains are stored only since 2026-10-02)"
)


def _moves() -> tuple[Feature, ...]:
    out = []
    for n in range(1, REPORTS + 1):
        out.append(
            Feature(
                f"move_{n}",
                "float32",
                "decimal",
                f"Signed move (close before the report to close after it, E-1 to E+1, raw) of the "
                f"{'newest' if n == 1 else f'{n}th newest'} report with a closed window; 0.05 is "
                "+5%, a fall is negative",
                _FEWER.format(n=n),
                valid_range=(-1, None),
                inputs=("bars/1d.close", _REPORT),
            )
        )
    for n in range(1, REPORTS + 1):
        out.append(
            Feature(
                f"move_date_{n}",
                "date",
                "date",
                f"The report date E of move_{n}",
                _FEWER.format(n=n),
                inputs=("bars/1d.close", _REPORT),
            )
        )
    return tuple(out)


FEATURES = (
    *_moves(),
    Feature(
        "moves_counted_12", "int", "count",
        f"How many of the last {REPORTS} reports with a closed window had both bars of the "
        "window: the number of moves behind move_1 .. move_12 (0: none)",
        "the name has no earnings report row at all (UNKNOWN: no calendar coverage); 0 when "
        "reports exist but none has a closed window with both bars",
        valid_range=(0, REPORTS), inputs=("bars/1d.close", _REPORT),
    ),
    Feature(
        "abs_move_mean_12", "float32", "decimal",
        f"Mean absolute move (E-1 to E+1, raw) of the last {REPORTS} reports with a closed "
        "window; 0.05 is 5%",
        _NO_MOVES, valid_range=(0, None), inputs=("bars/1d.close", _REPORT),
    ),
    Feature(
        "options_overpaid_n", "int", "count",
        "How many of the counted reports with a stored earnings straddle at the session before "
        "them had an implied move above the absolute move that followed (options_overpaid_m is "
        "how many were measured)",
        _NO_STRADDLE, valid_range=(0, REPORTS), inputs=("implied_move.implied_move@v1", _REPORT),
    ),
    Feature(
        "options_overpaid_m", "int", "count",
        "How many of the counted reports have the implied move stored at the session before "
        "them (implied_move@v1 with move_basis EARNINGS and an expiry covering the report): "
        "the denominator of options_overpaid_n",
        _NO_STRADDLE, valid_range=(0, REPORTS),
        inputs=("implied_move.implied_move@v1", "implied_move.move_basis@v1",
                "implied_move.move_expiry@v1", _REPORT),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _straddles(stored: pd.DataFrame | None) -> dict[tuple[str, date], tuple[float, date]]:
    """``{(instrument, session): (implied_move, move_expiry)}`` of the stored earnings-basis
    straddles with a value."""
    if stored is None or stored.empty or "move_basis" not in stored.columns:
        return {}
    rows = stored[(stored["move_basis"] == EARNINGS_BASIS) & stored["implied_move"].notna()]
    rows = rows[rows["move_expiry"].notna()]
    days = pd.to_datetime(rows["session_date"]).dt.date
    expiries = pd.to_datetime(rows["move_expiry"]).dt.date
    return {
        (str(i), d): (float(v), x)
        for i, d, v, x in zip(
            rows["instrument_id"], days, rows["implied_move"], expiries, strict=True
        )
    }


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    read = read_reactions(inputs, session, LOOKBACK)
    straddles = _straddles(inputs.get(IMPLIED))
    out = []
    for traded in read.ids[~np.isnan(read.px[-1])]:  # every instrument traded on the session
        iid = str(traded)
        counted = counted_moves(read, iid, REPORTS)
        row: dict[str, object] = {"instrument_id": iid}
        if iid in read.all_reports:  # no report row at all is UNKNOWN, not a count of 0
            row["moves_counted_12"] = len(counted)
        for n, (report, _, move) in enumerate(counted, start=1):
            row[f"move_{n}"] = move
            row[f"move_date_{n}"] = report
        if counted:
            row["abs_move_mean_12"] = float(np.mean([abs(m) for _, _, m in counted]))
        measured = [
            (straddles[(iid, before)][0], abs(move))
            for report, before, move in counted
            if (iid, before) in straddles
            and expiry_covers(
                np.datetime64(straddles[(iid, before)][1]),
                np.datetime64(report),
                (iid, report) in read.pre,
            )
        ]
        if measured:
            row["options_overpaid_m"] = len(measured)
            row["options_overpaid_n"] = sum(implied > actual for implied, actual in measured)
        out.append(row)
    frame = pd.DataFrame(out, columns=["instrument_id", *COLUMNS])
    for count in ("moves_counted_12", "options_overpaid_n", "options_overpaid_m"):
        frame[count] = frame[count].astype("Int64")
    return frame.sort_values("instrument_id", kind="stable").reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The signed move of the name's last twelve earnings reports and how often the options "
    "market's implied move before them was above the move that followed",
    (
        Input(earnings.EVENTS),
        Input(BARS, lookback=LOOKBACK),
        Input(SYMBOLS, required=False),
        Input(IMPLIED, lookback=LOOKBACK, required=False),
    ),
    FEATURES,
    compute,
    applies_to="operating_company",
)
