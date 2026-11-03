"""``event_reaction@v1``: how far each class of event has moved a name, in normal days (ADR 0050,
docs/event-sensitivity-plan.md 4.1 and 4.2), and how often it moves in a big way with nothing on the
calendar.

Input: ``bars/1d`` split-adjusted, ``HISTORY`` sessions back (the plan says "all stored history":
three years is the window of this version, a longer one is a new version);
``events/earnings`` read as
``earnings_reaction@v2`` reads it (``read_reactions``: the calendar rows known by the session, one
report per quarter: the same counted reports, not a second window); ``events/macro_release`` (the
latest version of each release known by the session, ``known_from <= S``; a ``moved`` date dropped).
The 8-K results rows join the earnings reports with the per-quarter precedence of earnings v2.

An event's reaction session, the move, the normal day and the multiple are ``moves``' (log return
of the reaction session over the stdev of the 20 returns before it); an earnings report counts when
its time is known (``pre``: its own session, ``post``: the next), an unknown time is left out of the
multiples and still explains a big move on its two sessions. Only reaction sessions on or before the
session count.

Columns, each null (UNKNOWN) and never zero when fewer than 250 sessions of the name's own bars
stand behind them (``reaction_status`` SHORT_HISTORY):

    macro_<key>_*, monthly_expiry_*, quarter_end_*, earnings_*  events counted (``_n``), the median
        multiple and the worst simple return that fell (``_down_worst``) of the class's events
    normal_day_20d, big_move_5pct_today, big_move_2x_today        the session's own normal day, and
        whether its move is beyond 5 % / beyond 2 normal days of the session before
    big_moves_252d, big_down_moves_252d, unattributed_big_moves_252d, unattributed_share_252d
        big moves in the last 252 sessions, the ones that fell, the ones on a session with no
        earnings, macro or market-structure event (the jump-risk base rate), and their share
    share_of_top_moves_*        of the 20 largest absolute moves in the window, the share on an
        earnings, macro or market-structure session (that order: a session in two classes
        counts under
        the first), else unscheduled. A peer's report (EV3) and a split day are not separate classes
        here: peers are not excluded until ``peer_sensitivity@v1``; a split is applied to the bars.

One row per instrument traded on the session (dense). An earnings column of a name that cannot
report
is NOT_APPLICABLE (``applies_to``), the rest apply to every instrument; a leveraged fund's own row
holds its own bars (the reference's events are read by the read model).
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.corporate.earnings_reaction import (
    SYMBOLS,
    Reactions,
    read_reactions,
)
from algotrade.features.rollups.event_study import moves
from algotrade.features.rollups.price.price_stats import BARS, CLOSE

NAME = "event_reaction"
VERSION = 1
MACRO_RELEASE = "events/macro_release"
OK, SHORT_HISTORY = "OK", "SHORT_HISTORY"
HISTORY = 756  # sessions of bars: three years
PRE_TIME, POST_TIME = "09:00", "17:00"  # a report before the open / after the close
_REL = f"{MACRO_RELEASE}.release_date"
_EARN = f"{earnings.EVENTS}.ts"
_SHORT = f"fewer than {moves.MIN_SESSIONS} sessions of the name's own bars"
_EVENTS = "no event of the class has a reaction session on the grid with a complete normal day"


def class_features(
    prefix: str, label: str, inputs: tuple[str, ...], applies: str = "any"
) -> list[Feature]:
    gap = f"{_EVENTS}, or {_SHORT}"
    return [
        Feature(
            f"{prefix}_n",
            "int",
            "count",
            f"How many {label} events in the window have a reaction session "
            f"with a complete normal day",
            _SHORT,
            valid_range=(0, None),
            inputs=inputs,
            applies_to=applies,  # type: ignore[arg-type]
        ),
        Feature(
            f"{prefix}_multiple_median",
            "float32",
            "ratio",
            f"Median reaction to {label} events in normal days (|log return| of the reaction "
            "session over the stdev of the 20 returns before it)",
            gap,
            valid_range=(0, None),
            inputs=inputs,
            applies_to=applies,  # type: ignore[arg-type]
        ),
        Feature(
            f"{prefix}_down_worst",
            "float32",
            "decimal",
            f"The worst fall (simple return, negative) on a {label} reaction session in the window",
            f"{gap}, or none of them fell",
            valid_range=(-1, 0),
            inputs=inputs,
            applies_to=applies,  # type: ignore[arg-type]
        ),
    ]


def _features() -> tuple[Feature, ...]:
    out = [
        Feature(
            "reaction_status",
            "str",
            "category",
            f"OK: the name has {moves.MIN_SESSIONS} sessions of bars or more; SHORT_HISTORY: fewer "
            "(every other column is null)",
            "never",
            "label",
            categories=(OK, SHORT_HISTORY),
            inputs=(CLOSE,),
        ),
        Feature(
            "normal_day_20d",
            "float32",
            "decimal",
            "The name's normal day: the standard deviation of its last 20 daily log returns "
            "(hv20 over the square root of 252)",
            f"a session among the last 21 has no bar, or {_SHORT}",
            valid_range=(0, None),
            inputs=(CLOSE,),
        ),
    ]
    for flag, text in (
        ("big_move_5pct_today", "beyond 5% (simple return)"),
        ("big_move_2x_today", f"beyond {moves.BIG_MULTIPLE:g} normal days of the session before"),
    ):
        out.append(
            Feature(
                flag,
                "float32",
                "flag",
                f"1 when the session's close-to-close move is {text}, else 0",
                f"the session or the one before has no bar, or {_SHORT}",
                valid_range=(0, 1),
                inputs=(CLOSE,),
            )
        )
    for name, text, rng in (
        (
            "big_moves_252d",
            "sessions in the last 252 with a big move (beyond 5% or 2 normal days)",
            (0, 252),
        ),
        ("big_down_moves_252d", "of the big moves in the last 252 sessions, the falls", (0, 252)),
        (
            "unattributed_big_moves_252d",
            "big moves in the last 252 sessions on a session with no earnings, macro or "
            "market-structure "
            "event: the jump-risk base rate per year",
            (0, 252),
        ),
    ):
        out.append(
            Feature(
                name,
                "int",
                "count",
                f"How many {text}",
                _SHORT,
                valid_range=rng,
                inputs=(CLOSE, _EARN, _REL),
            )
        )
    out.append(
        Feature(
            "unattributed_share_252d",
            "float32",
            "decimal",
            "Of the big moves in the last 252 sessions, the share on a session with no "
            "calendared event",
            f"no big move in the last 252 sessions, or {_SHORT}",
            valid_range=(0, 1),
            inputs=(CLOSE, _EARN, _REL),
        )
    )
    for key in moves.MACRO_KEYS:
        out += class_features(f"macro_{key.lower()}", f"{key} release", (CLOSE, _REL))
    out += class_features("monthly_expiry", "monthly option expiry", (CLOSE,))
    out += class_features("quarter_end", "quarter-end", (CLOSE,))
    out += class_features("earnings", "earnings report", (CLOSE, _EARN), "operating_company")
    for cls in (moves.EARNINGS, moves.MACRO, moves.STRUCTURE_CLASS, moves.UNSCHEDULED):
        out.append(
            Feature(
                f"share_of_top_moves_{cls}",
                "float32",
                "decimal",
                f"Of the name's {moves.TOP_MOVES} largest absolute daily moves in the window, "
                "the share "
                f"on a {cls} session (earnings, then macro, then market structure decide a session "
                "in two classes)",
                f"fewer than {moves.TOP_MOVES} moves in the window, or {_SHORT}",
                valid_range=(0, 1),
                inputs=(CLOSE, _EARN, _REL),
            )
        )
    return tuple(out)


FEATURES = _features()
COLUMNS = column_types(FEATURES)


def earnings_positions(
    read: Reactions, column_of: dict[str, int]
) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Per column: the reaction positions of its counted reports (``pre``, ``post``), and the
    sessions an unknown-time report may have moved (its own and the next), which explain a big
    move without entering a multiple."""
    known: dict[int, list[int]] = {}
    unknown: dict[int, list[int]] = {}
    for iid, reports in read.all_reports.items():
        col = column_of.get(iid)
        if col is None:
            continue
        for report in reports:
            if (iid, report) in read.pre:
                pos = moves.reaction_position(read.grid, report, PRE_TIME)
                bucket = known
            elif (iid, report) in read.post:
                pos = moves.reaction_position(read.grid, report, POST_TIME)
                bucket = known
            else:
                pos = moves.reaction_position(read.grid, report, PRE_TIME)
                bucket = unknown
            if pos is None:
                continue
            bucket.setdefault(col, []).append(pos)
            if bucket is unknown and pos + 1 < len(read.grid):
                unknown[col].append(pos + 1)
    return known, unknown


def class_matrix(
    shape: tuple[int, int],
    macro: list[int],
    structure: list[int],
    earn: dict[int, list[int]],
    unknown: dict[int, list[int]],
) -> np.ndarray:
    """The class code of every (session, name) cell: 0 unscheduled, 1 structure, 2 macro, 3 earnings
    (each overwrites the one before: the order that decides a session in two classes)."""
    cls = np.zeros(shape, dtype=np.int8)
    cls[structure] = 1
    cls[macro] = 2
    for source in (unknown, earn):
        for col, positions in source.items():
            cls[positions, col] = 3
    return cls


def top_shares(returns: np.ndarray, cls: np.ndarray) -> np.ndarray:
    """``(4, names)``: the share of each class among the ``TOP_MOVES`` largest absolute moves of a
    name (NaN when it has fewer than that)."""
    size = moves.TOP_MOVES
    mag = np.where(np.isfinite(returns), np.abs(returns), -1.0)
    top = np.argpartition(-mag, size - 1, axis=0)[:size]
    picked = np.take_along_axis(mag, top, axis=0)
    classes = np.take_along_axis(cls, top, axis=0)
    out = np.stack([(classes == k).mean(axis=0) for k in (3, 2, 1, 0)])
    out[:, (picked < 0).any(axis=0)] = np.nan
    return out


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    read = read_reactions(inputs, session, HISTORY)
    grid, px = read.grid, read.px
    traded = ~np.isnan(px[-1])
    returns = moves.log_returns(px)
    mult = moves.multiples(returns)
    releases = moves.release_days(inputs.get(MACRO_RELEASE), session)
    macro_pos = moves.macro_positions(grid, releases)
    structure_pos = moves.structure_positions(grid)
    earn, unknown = earnings_positions(read, read.column_of)
    macro_all = sorted({p for ps in macro_pos.values() for p in ps})
    structure_all = sorted({p for ps in structure_pos.values() for p in ps})
    cls = class_matrix(px.shape, macro_all, structure_all, earn, unknown)

    cols: dict[str, np.ndarray] = {}
    width = px.shape[1]

    def add_class(prefix: str, n: np.ndarray, med: np.ndarray, down: np.ndarray) -> None:
        cols[f"{prefix}_n"], cols[f"{prefix}_multiple_median"], cols[f"{prefix}_down_worst"] = (
            n,
            med,
            down,
        )

    for key in moves.MACRO_KEYS:
        add_class(f"macro_{key.lower()}", *moves.class_stats(mult, returns, macro_pos[key]))
    for name in moves.STRUCTURE:
        add_class(name, *moves.class_stats(mult, returns, structure_pos[name]))
    n, med, down = np.zeros(width, dtype=np.int64), np.full(width, np.nan), np.full(width, np.nan)
    for col, positions in earn.items():
        n[col], med[col], down[col] = (
            a[0] for a in moves.class_stats(mult[:, [col]], returns[:, [col]], positions)
        )
    add_class("earnings", n, med, down)

    is_big = moves.big(returns, mult)
    year = slice(-moves.YEAR, None)
    big_n = is_big[year].sum(axis=0)
    unattributed = (is_big & (cls == 0))[year].sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        share = np.where(big_n > 0, unattributed / big_n, np.nan)
    cols.update(
        normal_day_20d=moves.normal_day(returns),
        big_move_5pct_today=np.where(
            np.isnan(returns[-1]),
            np.nan,
            (np.abs(np.expm1(returns[-1])) > moves.BIG_PCT).astype(float),
        ),
        big_move_2x_today=np.where(
            np.isnan(mult[-1]), np.nan, (mult[-1] > moves.BIG_MULTIPLE).astype(float)
        ),
        big_moves_252d=big_n.astype(np.int64),
        big_down_moves_252d=(is_big & (returns < 0))[year].sum(axis=0),
        unattributed_big_moves_252d=unattributed,
        unattributed_share_252d=share,
    )
    shares = top_shares(returns, cls)
    for k, name in enumerate(
        (moves.EARNINGS, moves.MACRO, moves.STRUCTURE_CLASS, moves.UNSCHEDULED)
    ):
        cols[f"share_of_top_moves_{name}"] = shares[k]

    long_enough = np.isfinite(px).sum(axis=0) >= moves.MIN_SESSIONS
    frame = pd.DataFrame({"instrument_id": read.ids})
    frame["reaction_status"] = np.where(long_enough, OK, SHORT_HISTORY)
    for name in COLUMNS:
        if name == "reaction_status":
            continue
        values = np.asarray(cols[name], dtype=float)
        values[~long_enough] = np.nan
        frame[name] = values
    frame = frame[traded].reset_index(drop=True)
    for name, dtype in COLUMNS.items():
        if dtype == "int":
            frame[name] = frame[name].astype("Int64")
    out: pd.DataFrame = (
        frame[["instrument_id", *COLUMNS]]
        .sort_values("instrument_id", kind="stable")
        .reset_index(drop=True)
    )
    return out


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How far each class of event (macro releases, option expiries and quarter ends, own earnings) "
    "has moved the name in normal days, the big-move flags and the unexplained jump-risk base rate",
    (
        Input(earnings.EVENTS),
        Input(BARS, lookback=HISTORY),
        Input(SYMBOLS, required=False),
        Input(MACRO_RELEASE, lookback=0, required=False),
    ),
    FEATURES,
    compute,
)
